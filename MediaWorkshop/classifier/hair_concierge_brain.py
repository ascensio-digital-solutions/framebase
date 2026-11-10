"""Unified bridge between Framebase MediaWorkshop (`ascensio-media-os`) and
The Hair Concierge Brain (`the-hair-concierge-2026` + `AgentsStudio`).

Connects:
1. Vertex AI RAG Engine Corpora in `the-hair-concierge-2026` (`us-west1`):
   - `HAIR_SYSTEM_RAG_CORPUS`: `projects/the-hair-concierge-2026/locations/us-west1/ragCorpora/4611686018427387904`
     (Hair System Bible v2, Product Facts v1, Approved Claims v1, Media Workshop Taxonomy v1)
   - `MARKETING_BRAND_RAG_CORPUS`: `projects/the-hair-concierge-2026/locations/us-west1/ragCorpora/2305843009213693952`
     (Atelier Zero v7 design system, Brand Foundations, Storefront Facts, Approved Support Facts, Rebrand Campaign)
2. Cloud Storage Assets in `the-hair-concierge-2026` (`us-east1`):
   - `gs://the-hair-concierge-2026-assets/` (54 versioned knowledge, brand, SFT/DPO, and R2 manifest files)
3. Local & R2 Reference Manifest (`AgentsStudio/src/agents/shared/hsc_reference_manifest_v01.jsonl`):
   - 1,551 verified R2 reference swatches and product photos (`framebase-blobs-prod`)
4. Domain Spec Engine (`AgentsStudio/src/agents/hair_system_expert/tools.py`):
   - `match_hair_color`, `recommend_base_type`, `calculate_density`, `get_prompt_spec`
"""

from __future__ import annotations

import json
import socket
import subprocess
import sys
from pathlib import Path
from typing import Any

# Fast IPv4 DNS resolver for *.googleapis.com when macOS DHCPv6 DNS is unresponsive
_orig_getaddrinfo = socket.getaddrinfo
_dns_cache: dict[str, str] = {}


def install_google_ipv4_dns_resolver() -> None:
    """Ensure *.googleapis.com resolves immediately over IPv4 (8.8.8.8) without IPv6 timeout."""
    def _fast_getaddrinfo(host: Any, port: Any, family: int = 0, type: int = 0, proto: int = 0, flags: int = 0) -> Any:
        host_str = str(host) if host else ""
        if host_str.endswith(".googleapis.com") or host_str.endswith(".google.com"):
            if host_str not in _dns_cache:
                try:
                    out = subprocess.check_output(
                        ["dig", "+time=1", "+tries=1", "@8.8.8.8", host_str, "A", "+short"],
                        text=True,
                        stderr=subprocess.DEVNULL,
                    ).strip().splitlines()
                    ips = [line.strip() for line in out if line.strip() and line.strip()[0].isdigit()]
                    if ips:
                        _dns_cache[host_str] = ips[0]
                except Exception:
                    pass
            if host_str in _dns_cache:
                return _orig_getaddrinfo(_dns_cache[host_str], port, socket.AF_INET, type, proto, flags)
        return _orig_getaddrinfo(host, port, family, type, proto, flags)

    socket.getaddrinfo = _fast_getaddrinfo  # type: ignore[assignment]


install_google_ipv4_dns_resolver()

MONOREPO_ROOT = Path(__file__).resolve().parents[2]
AGENTS_STUDIO_ROOT = MONOREPO_ROOT / "AgentsStudio"
if str(AGENTS_STUDIO_ROOT) not in sys.path:
    sys.path.insert(0, str(AGENTS_STUDIO_ROOT))

import importlib.util
from src.agents.shared.rag import (  # noqa: E402
    HAIR_SYSTEM_RAG_CORPUS,
    MARKETING_BRAND_RAG_CORPUS,
    retrieve_rag_sync,
)
from src.agents.shared.references import (  # noqa: E402
    lookup_manifest_references,
    select_hair_system_references,
    select_marketing_references,
)

_tools_spec = importlib.util.spec_from_file_location(
    "src.agents.hair_system_expert.tools",
    AGENTS_STUDIO_ROOT / "src" / "agents" / "hair_system_expert" / "tools.py",
)
_tools_mod = importlib.util.module_from_spec(_tools_spec)  # type: ignore[arg-type]
_tools_mod.__package__ = "src.agents.hair_system_expert"
assert _tools_spec and _tools_spec.loader
_tools_spec.loader.exec_module(_tools_mod)

COLORS = _tools_mod.COLORS
CURL_PATTERNS = _tools_mod.CURL_PATTERNS
BASE_TYPES = _tools_mod.BASE_TYPES
HAIR_ORIGINS = _tools_mod.HAIR_ORIGINS
DENSITY_LABELS = _tools_mod.DENSITY_LABELS
ATTACHMENT_METHODS = _tools_mod.ATTACHMENT_METHODS
calculate_density = _tools_mod.calculate_density
get_prompt_spec = _tools_mod.get_prompt_spec
match_hair_color = _tools_mod.match_hair_color
recommend_base_type = _tools_mod.recommend_base_type

HAIR_CONCIERGE_GCP_PROJECT = "the-hair-concierge-2026"
HAIR_CONCIERGE_GCS_BUCKET = "gs://the-hair-concierge-2026-assets"
HAIR_SYSTEM_BIBLE_PATH = (
    AGENTS_STUDIO_ROOT
    / "src"
    / "agents"
    / "hair_system_expert"
    / "knowledge"
    / "hair_system_bible.md"
)
MANIFEST_PATH = (
    AGENTS_STUDIO_ROOT
    / "src"
    / "agents"
    / "shared"
    / "hsc_reference_manifest_v01.jsonl"
)


def query_hair_concierge_rag(
    query: str,
    corpus: str = "hair_system",
    top_k: int = 5,
) -> dict[str, Any]:
    """Query the live Vertex AI RAG corpus in `the-hair-concierge-2026` (`us-west1`),
    with automatic fallback to the local `hair_system_bible.md` if offline.
    """
    target_corpus = (
        MARKETING_BRAND_RAG_CORPUS
        if corpus in ("marketing", "brand", "marketing_brand")
        else HAIR_SYSTEM_RAG_CORPUS
    )
    try:
        contexts = retrieve_rag_sync(target_corpus, query=query, similarity_top_k=top_k)
        return {
            "status": "ok",
            "source": "vertex_ai_rag",
            "project": HAIR_CONCIERGE_GCP_PROJECT,
            "corpus": target_corpus,
            "count": len(contexts),
            "contexts": contexts,
        }
    except Exception as exc:
        sections = []
        if HAIR_SYSTEM_BIBLE_PATH.exists():
            raw = HAIR_SYSTEM_BIBLE_PATH.read_text(encoding="utf-8")
            q_terms = [t.lower() for t in query.split() if len(t) >= 3]
            for block in raw.split("\n---\n"):
                score = sum(1 for t in q_terms if t in block.lower())
                if score > 0:
                    sections.append((score, block.strip()))
            sections.sort(key=lambda x: x[0], reverse=True)
        return {
            "status": "ok_local_fallback",
            "source": str(HAIR_SYSTEM_BIBLE_PATH),
            "project": HAIR_CONCIERGE_GCP_PROJECT,
            "corpus": target_corpus,
            "rag_error": str(exc),
            "count": min(top_k, len(sections)),
            "contexts": [
                {"source_uri": str(HAIR_SYSTEM_BIBLE_PATH), "text": text, "score": score}
                for score, text in sections[:top_k]
            ],
        }


def get_sorter_grounding_context(fetch_live_rag: bool = True) -> str:
    """Return the complete domain grounding rubric from The Hair Concierge Brain
    (`the-hair-concierge-2026` RAG corpora + Hair System Bible v2 + Atelier Zero v7)
    to inject into `multi_pass_sorter.py` and `nano_banana_studio.py` prompts.
    """
    color_summary = ", ".join(f"#{k} ({v})" for k, v in COLORS.items())
    curl_summary = ", ".join(
        f"{k} ({v['rod']} rod: {v['desc']})" for k, v in CURL_PATTERNS.items()
    )
    base_summary = "; ".join(
        f"{k}: {v}"
        for k, v in BASE_TYPES.items()
    )

    live_rag_snippets: list[str] = []
    if fetch_live_rag:
        for corpus_key, q in [
            ("hair_system", "base construction Swiss lace ultra-thin skin 0.03mm hairline graduation color codes grey blend"),
            ("marketing", "Atelier Zero v7 marble head Leo Miles Marc Ray collage approved claims before after policy"),
        ]:
            res = query_hair_concierge_rag(q, corpus=corpus_key, top_k=2)
            for ctx in res.get("contexts", [])[:2]:
                snippet = (ctx.get("text") or "").strip().replace("\n", " ")
                if snippet:
                    live_rag_snippets.append(f"[{corpus_key.upper()} RAG ({res.get('source')})]: {snippet[:380]}...")

    rag_block = "\n".join(live_rag_snippets) if live_rag_snippets else "Loaded from local Hair System Bible v2."

    return (
        "### THE HAIR CONCIERGE BRAIN GROUNDING (`the-hair-concierge-2026` — ACTIVE)\n"
        f"- **Base Constructions**: {base_summary}\n"
        "  * `base:poly-skin`: Ultra-Thin Skin (0.03mm polyurethane, invisible edge) & Thin Skin (0.06–0.08mm polyurethane).\n"
        "  * `base:swiss-lace`: Delicate fine Swiss lace mesh, disappears on scalp, maximum exposed hairline realism.\n"
        "  * `base:french-lace`: Durable breathable French lace mesh, slightly more visible grid than Swiss.\n"
        "  * `base:mono-mesh`: Fine monofilament polyester mesh top with poly perimeter.\n"
        f"- **HSC Factory Color System**: {color_summary}, #22 (Light Blonde).\n"
        "- **Grey Percentage Scale**: `#1B10` (10% grey, subtle temple salt-and-pepper), `#1B20` (20% grey), `#1B30` (30% grey), `#1B40` (40% grey), `#1B50` (50% silver fox) — naturally heavier at temples.\n"
        f"- **Curl & Wave Rod Geometry**: {curl_summary}\n"
        "- **Hairline Graduation Standard (Leading 0.5cm)**:\n"
        "  * Must graduate from 60–65% density down to ~40% at the leading edge, with single bleached knots (no dark dots), irregular wispy baby hairs (0.2–0.5cm), and natural scalp pore translucency (`hairline:undetectable` / `quality:strong`).\n"
        "  * Blunt cutoffs, visible lace grids, dark unbleached knots, or >120% helmet density must be flagged in `rationale` and downgraded.\n"
        "- **Attachment & Care Ecosystem**: Walker No-Shine Tape, Walker Ultra Hold Tape, Walker Extenda-Bond, Ghost Bond Platinum / XL, C-22 Solvent.\n"
        "- **Atelier Zero v7 & Marble Head Brand System**:\n"
        "  * Classical white Carrara marble busts wearing hyper-realistic human-hair systems (characters: `Leo`, `Miles`, `Marc`, `Ray`) and Krea numbered editorial collages (warm paper `#EFE7D2`, coral sun disc `#FF5757`, mustard ochre `#E9B94A`, olive `#6E7448`) belong to `hair_solutions_co` (`08_marketing/brand` or `01_products/hair-systems`).\n"
        "- **Approved Claims Policy (2026-10-29)**:\n"
        "  * Real customer/model before-and-after proof photos (`before_bald_thinning`, `before_after_split`) are consented real photography in `03_people/models/<name>/before-after`.\n"
        "- **Hair System Visual Presentation & Photography Archetypes (CRITICAL ORIENTATION RULES)**:\n"
        "  1. `presentation:mushroom-head-hair-up` (`orientation:hair-side-up`, `base-visibility:hidden-underneath`):\n"
        "     * Standalone rounded 'mushroom-head' dome hair system resting with its **base material facing DOWN** against the white studio surface so the base is **100% hidden/invisible**.\n"
        "     * Reveals **only the full 360° hair dome all around** (crown swirl, slight/body wave texture, and true hair color/grey blend like `#1`, `#1A`, `#1B`, `#1B05`..`#1B80`, `#2`, `#205`..`#280`, `#3`, `#305`..`#380`, `#4`, `#4ASH`, `#5`, `#6`, `#7`, `#17`, `#18`, `#22`). Often includes a large `#3` / `#1B20` background watermark or `COLOR #...` label.\n"
        "     * **NEVER confuse with inverted base-side-up domes!**\n"
        "  2. `presentation:inverted-dome-base-up` (`orientation:base-side-up`, `base-visibility:exposed-top-dome`):\n"
        "     * Standalone hair system turned **inside-out / base-side-up** on a dome mold so the **base material (`base:poly-skin`, `base:swiss-lace`, `base:french-lace`, `base:mono-mesh`, PU perimeter, zig-zag lace front)** forms the top 65% of the dome, with only a short skirt of hair around the bottom rim.\n"
        "  3. `presentation:macro-base-zoom` (`shot:macro-base`):\n"
        "     * Zoomed-in e-commerce close-up focusing on the base material mesh/skin (Swiss/French lace honeycomb holes, 0.03mm ultra-thin skin translucency over fingers/scalp, bleached single knots, or V-looped knotless hair emergence).\n"
        "  4. `presentation:technical-callout-diagram`:\n"
        "     * E-commerce base construction diagram with circular magnifying-glass callout insets (`DOUBLE SPLIT KNOT`, `SINGLE SPLIT KNOT`, `FRONT 1/2\" V-LOOPED`, `Graduated hairline`, `0.08mm thin skin`).\n"
        "  5. `presentation:flat-circle-swatch` & `presentation:ring-swatch`:\n"
        "     * Flat circular cropped hair texture discs (`variant-wizard-*.png`) or fanned metal swatch rings (`02_specs/swatches/circle-swatches`, `ring-swatches`).\n"
        f"- **Live Retrieved RAG Contexts (`the-hair-concierge-2026`)**:\n{rag_block}"
    )


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="Query The Hair Concierge Brain (`the-hair-concierge-2026`).")
    parser.add_argument("--query", "-q", type=str, default="Swiss lace vs 0.03mm ultra-thin skin hairline graduation")
    parser.add_argument("--corpus", choices=["hair_system", "marketing"], default="hair_system")
    parser.add_argument("--swatches", type=str, default="", help="Optional tag query for 1,551 R2 reference swatches")
    args = parser.parse_args()

    res = query_hair_concierge_rag(args.query, corpus=args.corpus)
    print(json.dumps(res, indent=2))
    if args.swatches:
        print("\n=== Matching R2 Reference Swatches ===")
        print(json.dumps(lookup_manifest_references(tag_query=args.swatches, limit=5), indent=2))

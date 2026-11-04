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
import sys
from pathlib import Path
from typing import Any

MONOREPO_ROOT = Path(__file__).resolve().parents[2]
AGENTS_STUDIO_ROOT = MONOREPO_ROOT / "AgentsStudio"
if str(AGENTS_STUDIO_ROOT) not in sys.path:
    sys.path.insert(0, str(AGENTS_STUDIO_ROOT))

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
from src.agents.hair_system_expert.tools import (  # noqa: E402
    BANNED_CUSTOMER_WORDS,
    BASE_TYPES,
    COLOR_CODES,
    CURL_PATTERNS,
    DENSITY_SCALE,
    GREY_PERCENTAGES,
    HAIR_ORIGINS,
    calculate_density,
    get_prompt_spec,
    match_hair_color,
    recommend_base_type,
)

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
        # Offline / local fallback to Hair System Bible sections
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


def get_sorter_grounding_context() -> str:
    """Return a concise domain grounding rubric from The Hair Concierge Brain
    to inject into `multi_pass_sorter.py` and `nano_banana_studio.py` prompts.
    """
    color_summary = ", ".join(
        f"#{k} ({v.split('—')[0].strip()})" for k, v in COLOR_CODES.items()
    )
    curl_summary = ", ".join(
        f"{k} ({v['rod_mm']} rod)" for k, v in CURL_PATTERNS.items()
    )
    return (
        "THE HAIR CONCIERGE BRAIN GROUNDING (`the-hair-concierge-2026`):\n"
        f"- Color Codes: {color_summary}\n"
        f"- Grey Blends: {', '.join(GREY_PERCENTAGES.keys())} (heavier at temples)\n"
        f"- Curl Patterns: {curl_summary}\n"
        f"- Base Types: {', '.join(BASE_TYPES.keys())}\n"
        "- Hairline Graduation Rule: Leading 0.5cm graduates 60-65% -> 40% with single bleached knots & irregular baby hairs.\n"
        "- Approved Claims Policy: Before/after proof photos are real consented photos only; never AI-generated."
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

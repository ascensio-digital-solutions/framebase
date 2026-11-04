"""Reference image loader for Hair System Expert and Marketing Director.

Loads curated reference images from:
1. Cloudflare R2 (``framebase-blobs-prod``) indexed by ``hsc_reference_manifest_v01.jsonl``
   with local disk caching under ``.adk/ref_cache/``.
2. Local Hair Solutions Co. brand assets (Krea ``REFERENCE_BOARD.png``, marble character
   sheets/cutouts, and approved logos).
"""

from __future__ import annotations

import json
import mimetypes
import os
import urllib.request
from pathlib import Path
from typing import Any, Optional

from google.genai import types as genai_types

_MANIFEST_PATH = Path(__file__).parent / "hsc_reference_manifest_v01.jsonl"
_CACHE_DIR = Path(__file__).resolve().parents[3] / ".adk" / "ref_cache"

_KREA_REFERENCE_BOARD = Path(
    "/Users/vincent/01_hair_solutions_co/design/krea_marble_exploration_2026_10_13/"
    "outputs/krea-marble-free-trial/REFERENCE_BOARD.png"
)
_MARBLE_IMAGES_DIR = Path(
    "/Users/vincent/01_hair_solutions_co/design/brand/marble heads/images"
)
_APPROVED_LOGOS_DIR = Path(
    "/Users/vincent/01_hair_solutions_co/design/brand/logos/masterfile-approved"
)
_BDS_REPO_DIR = Path("/Users/vincent/06_code/brand-design-system")
_BDS_LOGOS_DIR = (
    _BDS_REPO_DIR / "atelier_zero_design_system_artifact" / "project" / "assets" / "Logos"
)

_MANIFEST_CACHE: Optional[list[dict[str, Any]]] = None
_R2_CREDS_CACHE: Optional[tuple[str, str]] = None

# Tags that indicate non-product/non-swatch screenshots or operational documents
_EXCLUDED_TAGS = {
    "doc:tax-record",
    "doc:financial",
    "topic:taxes",
    "topic:operations",
    "category:businessoperations",
    "app:safari",
    "app:temu",
    "quality:weak",
    "topic:before-after",
    "marketing:comparison",
}


def _load_manifest() -> list[dict[str, Any]]:
    global _MANIFEST_CACHE
    if _MANIFEST_CACHE is not None:
        return _MANIFEST_CACHE
    rows: list[dict[str, Any]] = []
    if _MANIFEST_PATH.exists():
        with open(_MANIFEST_PATH, encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if line:
                    rows.append(json.loads(line))
    _MANIFEST_CACHE = rows
    return rows


def _get_r2_credentials() -> tuple[Optional[str], Optional[str]]:
    """Resolve Cloudflare Account ID and R2-capable API token in memory."""
    global _R2_CREDS_CACHE
    if _R2_CREDS_CACHE is not None:
        return _R2_CREDS_CACHE

    env_map: dict[str, str] = {}
    master_env = Path("/Users/vincent/.env")
    if master_env.exists():
        try:
            with open(master_env, encoding="utf-8") as f:
                for line in f:
                    line = line.strip()
                    if line and not line.startswith("#") and "=" in line:
                        k, v = line.split("=", 1)
                        env_map[k.strip()] = v.strip().strip("\"'")
        except Exception:
            pass

    account_id = os.environ.get("CLOUDFLARE_ACCOUNT_ID") or env_map.get("CLOUDFLARE_ACCOUNT_ID")
    token = None
    for key in (
        "CLOUDFLARE_FB_DEPLOY_TOKEN",
        "CLOUDFLARE_MASTER_ACCOUNT_API_TOKEN",
        "CLOUDFLARE_MASTER_TOKEN",
    ):
        token = os.environ.get(key) or env_map.get(key)
        if token:
            break

    _R2_CREDS_CACHE = (account_id, token)
    return _R2_CREDS_CACHE


def fetch_r2_blob(row: dict[str, Any]) -> Optional[tuple[bytes, str, str]]:
    """Fetch an image blob from Cloudflare R2 (with local disk cache).

    Returns (bytes, mime_type, cached_path) or None if unavailable.
    """
    sha256 = row.get("sha256", "")
    r2_key = row.get("r2_key", "")
    bucket = row.get("r2_bucket", "framebase-blobs-prod")
    media_type = row.get("media_type", "image/jpeg")
    if not sha256 or not r2_key:
        return None

    ext = r2_key.rsplit(".", 1)[-1] if "." in r2_key else "jpg"
    _CACHE_DIR.mkdir(parents=True, exist_ok=True)
    cache_file = _CACHE_DIR / f"{sha256}.{ext}"
    if cache_file.exists() and cache_file.stat().st_size > 0:
        return cache_file.read_bytes(), media_type, str(cache_file)

    account_id, token = _get_r2_credentials()
    if not account_id or not token:
        return None

    url = (
        f"https://api.cloudflare.com/client/v4/accounts/{account_id}"
        f"/r2/buckets/{bucket}/objects/{r2_key}"
    )
    req = urllib.request.Request(
        url,
        headers={
            "Authorization": f"Bearer {token}",
            "User-Agent": "agents-studio/1.0",
        },
    )
    try:
        with urllib.request.urlopen(req, timeout=12) as resp:
            data = resp.read()
        if data:
            cache_file.write_bytes(data)
            return data, media_type, str(cache_file)
    except Exception:
        return None
    return None


def _read_local_file(path: Path) -> Optional[tuple[bytes, str, str]]:
    """Read a local image file and return (bytes, mime_type, resolved_path)."""
    try:
        resolved = path.resolve()
        if not resolved.exists() or not resolved.is_file():
            return None
        mime, _ = mimetypes.guess_type(str(resolved))
        return resolved.read_bytes(), (mime or "image/png"), str(resolved)
    except Exception:
        return None


def select_hair_system_references(
    color_code: str = "1B",
    curl_pattern: str = "slight_wave",
    density_percent: int = 95,
    base_type: str = "ultra_thin_skin",
    grey_percentage: int = 0,
    hairline_style: str = "exposed",
    max_refs: int = 3,
) -> tuple[list[genai_types.Part], list[dict[str, Any]]]:
    """Select and load up to ``max_refs`` reference images from the R2 swatch manifest.

    Prioritizes:
    1. Matching hair-color swatch from ``02_specs/swatches/hair-color``
    2. Matching curl-pattern swatch from ``02_specs/swatches/curl-pattern``
    3. Matching base-material swatch from ``02_specs/swatches/base-material``
    4. High-quality studio hairline/product photo from ``01_products/hair-systems``
    """
    rows = _load_manifest()
    if not rows:
        return [], []

    color_tag_Hints = {
        "1": ["color:1", "color:1a", "hair:black", "jet-black"],
        "1B": ["color:1b", "1b", "off-black"],
        "2": ["color:2", "darkest-brown", "#2"],
        "3": ["color:3", "dark-brown", "color:brown"],
        "4": ["color:4", "medium-brown", "color:brown"],
        "5": ["color:5", "light-brown", "hair:light-brown"],
        "6": ["color:6", "dark-blonde", "hair:blonde"],
        "7": ["color:7", "color-7", "hair:blonde"],
        "8": ["color:8", "light-blonde", "hair:blonde"],
        "9": ["color:9", "hair:blonde"],
        "10": ["color:10", "platinum", "hair:blonde"],
    }.get(color_code.upper(), [f"color:{color_code.lower()}"])

    curl_rod_map = {
        "straight": ["32mm", "straight"],
        "slight_wave": ["25mm", "slight-wave"],
        "body_wave": ["20mm", "body-wave"],
        "medium_wave": ["15mm", "curl:15mm"],
        "tight_wave": ["10mm", "10cm"],
        "afro_curl": ["4mm", "6mm", "curl:4mm", "curl:6mm"],
    }.get(curl_pattern, [])

    base_tag_map = {
        "ultra_thin_skin": ["material:ultra-thin-skin", "spec:003mm", "spec:003-pu", "material:poly-skin", "base:skin"],
        "thin_skin": ["spec:poly-006mm", "material:poly-skin", "base:skin"],
        "swiss_lace": ["part:lace-front", "base:lace", "material:lace"],
        "french_lace": ["base:french-lace", "part:lace-front", "base:lace"],
        "mono": ["base:monofilament", "material:mono-lace"],
        "hybrid": ["part:lace-front", "base:poly-coating", "base:lace"],
    }.get(base_type, [])

    def _is_clean(r: dict[str, Any]) -> bool:
        if r.get("media_type") not in ("image/jpeg", "image/png", "image/webp"):
            return False
        tags = set(r.get("tags", []))
        if tags & _EXCLUDED_TAGS:
            return False
        if "type:screenshot" in tags and r.get("folder") == "01_products/hair-systems":
            return False
        return True

    def _pick_best(folder: str, hints: list[str], require_camera: bool = False) -> Optional[dict[str, Any]]:
        candidates = [r for r in rows if r.get("folder") == folder and _is_clean(r)]
        if require_camera:
            candidates = [r for r in candidates if "type:camera-photo" in r.get("tags", [])]
        if not candidates:
            return None

        def _hint_matches(r: dict[str, Any]) -> int:
            tags = r.get("tags", [])
            tag_blob = " ".join(tags).lower() + " " + r.get("display_name", "").lower()
            return sum(1 for h in hints if h.lower() in tag_blob)

        def _score(r: dict[str, Any]) -> int:
            hm = _hint_matches(r)
            if hm == 0:
                return 0
            tags = r.get("tags", [])
            s = hm * 10
            if "quality:strong" in tags:
                s += 5
            if "type:camera-photo" in tags:
                s += 3
            if "source:studio" in tags:
                s += 3
            if "item:swatch" in tags or "hair:swatch" in tags:
                s += 2
            return s

        candidates.sort(key=_score, reverse=True)
        return candidates[0] if _score(candidates[0]) > 0 else None

    picked_rows: list[dict[str, Any]] = []
    seen_sha: set[str] = set()

    for candidate in (
        _pick_best("02_specs/swatches/hair-color", color_tag_Hints),
        _pick_best("02_specs/swatches/base-material", base_tag_map),
        _pick_best("02_specs/swatches/curl-pattern", curl_rod_map),
        _pick_best(
            "01_products/hair-systems",
            ["hairline:natural", "source:studio", "hairline:exposed" if hairline_style == "exposed" else "quality:strong"],
            require_camera=True,
        ),
    ):
        if candidate and candidate["sha256"] not in seen_sha and len(picked_rows) < max_refs:
            seen_sha.add(candidate["sha256"])
            picked_rows.append(candidate)

    parts: list[genai_types.Part] = []
    meta: list[dict[str, Any]] = []
    for row in picked_rows:
        fetched = fetch_r2_blob(row)
        if fetched:
            data, mime, cached_path = fetched
            parts.append(genai_types.Part.from_bytes(data=data, mime_type=mime))
            meta.append({
                "asset_id": row.get("asset_id"),
                "display_name": row.get("display_name"),
                "folder": row.get("folder"),
                "r2_key": row.get("r2_key"),
                "cached_path": cached_path,
            })

    return parts, meta


def select_marketing_references(
    mode: str = "marble",
    character_name: str = "",
    logo_variant: str = "",
) -> tuple[list[genai_types.Part], list[dict[str, Any]]]:
    """Load local/R2 reference images for Marketing Director tools.

    - ``mode="collage"``: always loads Krea ``REFERENCE_BOARD.png`` first.
    - If ``character_name`` is ``leo``, ``miles``, ``marc``, or ``ray``: loads their
      ``<char>-busts.png`` and ``<char>-angles.png`` sheets.
    - Otherwise (free-form marble head): loads a single Carrara marble bust cutout
      reference for stone veining, blank carved eyes, and fractured plinth truncation.
    - If ``logo_variant`` is provided: loads the matching approved logo from
      ``masterfile-approved/``.
    """
    parts: list[genai_types.Part] = []
    meta: list[dict[str, Any]] = []

    def _add_path(p: Path, role: str) -> None:
        loaded = _read_local_file(p)
        if loaded:
            data, mime, resolved = loaded
            parts.append(genai_types.Part.from_bytes(data=data, mime_type=mime))
            meta.append({"role": role, "path": resolved})

    if mode == "collage":
        _add_path(_KREA_REFERENCE_BOARD, "krea_collage_reference_board")

    char_key = character_name.strip().lower()
    if char_key in ("leo", "miles", "marc", "ray"):
        _add_path(_MARBLE_IMAGES_DIR / f"{char_key}-busts.png", f"character_{char_key}_busts")
        _add_path(_MARBLE_IMAGES_DIR / f"{char_key}-angles.png", f"character_{char_key}_angles")
    elif mode in ("marble", "collage", "social", "campaign"):
        # Provide one sculpted Carrara stone material/plinth reference
        _add_path(
            _MARBLE_IMAGES_DIR / "cutouts" / "marc-busts-1.png",
            "carrara_marble_material_reference",
        )

    if logo_variant:
        key = logo_variant.strip().lower()
        bds_variant_map = {
            "wordmark-ink": _BDS_LOGOS_DIR / "wordmark-ink.png",
            "wordmark-bone": _BDS_LOGOS_DIR / "wordmark-bone.png",
            "wordmark-ink-padded": _BDS_LOGOS_DIR / "wordmark-ink-padded.png",
            "wordmark-bone-padded": _BDS_LOGOS_DIR / "wordmark-bone-padded.png",
            "monogram-ink": _BDS_LOGOS_DIR / "monogram-ink.png",
            "monogram-bone": _BDS_LOGOS_DIR / "monogram-bone.png",
            "monogram-ink-on-paper": _BDS_LOGOS_DIR / "monogram-ink-on-paper.png",
            "monogram-bone-on-ink": _BDS_LOGOS_DIR / "monogram-bone-on-ink.png",
        }
        master_variant_map = {
            "wordmark-dark-on-light": _APPROVED_LOGOS_DIR / "wordmark-dark-on-light-bg.png",
            "wordmark-dark-on-transparent": _APPROVED_LOGOS_DIR / "wordmark-dark-on-transparent-bg.png",
            "wordmark-light-on-dark": _APPROVED_LOGOS_DIR / "wordmark-light-on-dark-bg.png",
            "monogram-dark-on-light": _APPROVED_LOGOS_DIR / "monogram-dark-on-light-bg.png",
            "monogram-dark-on-transparent": _APPROVED_LOGOS_DIR / "monogram-dark-on-transparent-bg.png",
            "monogram-light-on-dark": _APPROVED_LOGOS_DIR / "monogram-light-on-dark-bg.png",
        }
        target_path = (
            bds_variant_map.get(key)
            or master_variant_map.get(key)
            or (_BDS_LOGOS_DIR / "wordmark-ink.png")
        )
        _add_path(target_path, f"approved_logo_{logo_variant}")

    return parts, meta


def lookup_manifest_references(
    folder: str = "",
    tag_query: str = "",
    limit: int = 10,
) -> dict[str, Any]:
    """Search the 1,551-row HSC R2 reference manifest by folder and/or tag substring."""
    rows = _load_manifest()
    matches = []
    q = tag_query.strip().lower()
    f_prefix = folder.strip().lower()

    for r in rows:
        if f_prefix and not r.get("folder", "").lower().startswith(f_prefix):
            continue
        if q:
            haystack = " ".join(r.get("tags", [])).lower() + " " + r.get("display_name", "").lower()
            if q not in haystack:
                continue
        matches.append({
            "asset_id": r.get("asset_id"),
            "display_name": r.get("display_name"),
            "folder": r.get("folder"),
            "r2_key": r.get("r2_key"),
            "tags": r.get("tags", [])[:10],
        })
        if len(matches) >= max(1, min(limit, 50)):
            break

    return {
        "status": "found",
        "total_manifest_rows": len(rows),
        "returned": len(matches),
        "matches": matches,
    }

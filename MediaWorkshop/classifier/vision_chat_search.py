#!/usr/bin/env python3
"""
Multimodal Vision & Interactive Visual Similarity Search Engine for Framebase 2.0 AI Chat.

Powered by Google Cloud Vertex AI (`ascensio-media-os`, location=`global`, model=`gemini-3.8-flash`)
and grounded in The Hair Concierge Brain (`the-hair-concierge-2026`).

Capabilities:
1. Accepts an uploaded reference photo (`--image`) and/or a natural-language visual query (`--prompt`).
2. Distinguishes Hair System Visual Presentation Archetypes:
   - `mushroom-head-hair-up`: Base facing DOWN (hidden underneath), full 360° hair dome visible all around
     showing hair color (#1..#22, grey blends #1B05..#740) and wave texture.
   - `inverted-dome-base-up`: Base facing UP on a dome mold showing poly-skin, Swiss/French lace, or mono construction.
   - `macro-base-zoom`: Zoomed-in close-up on lace mesh, thin-skin translucency, knots, or hairline graduation.
   - `technical-callout-diagram`: E-commerce diagram with magnifying-glass callout circles (DOUBLE/SINGLE SPLIT KNOT, V-LOOP).
   - `flat-circle-swatch` / `ring-swatch`: Flat circular swatch discs or metal color rings.
   - `mannequin-head` / `human-wearer-portrait`: Mannequin display or human model photography.
3. Generates interactive clarification questions + 3-4 clickable Focus Options (`focus_options`) so the user can
   pivot or narrow their visual search by photography style, base material, orientation, or shade family.
"""

from __future__ import annotations

import argparse
import io
import json
import re
import sqlite3
import sys
import time
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import numpy as np
from PIL import Image, ImageDraw, ImageFile, ImageOps
from pydantic import BaseModel, Field
from google import genai
from google.genai import types

ImageFile.LOAD_TRUNCATED_IMAGES = True

SCRIPT_DIR = Path(__file__).parent.resolve()
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

from hair_concierge_brain import (  # noqa: E402
    get_sorter_grounding_context,
    install_google_ipv4_dns_resolver,
)

install_google_ipv4_dns_resolver()

PROJECT_ID = "ascensio-media-os"
LOCATION = "global"
MODEL_NAME = "gemini-3.8-flash"

THUMB_CACHE_DIR = Path.home() / "Library/Caches/com.vincentlaroche.framebase/Thumbnails"
FEATURE_CACHE_PATH = SCRIPT_DIR.parent / "reports" / "vision_silhouette_cache_v2.npz"


class FocusOption(BaseModel):
    label: str = Field(
        description="Numbered concise button label for the user to click (e.g. '1) Mushroom-head full-hair domes (all hair colors, base hidden)', '2) Lace material hair systems', '3) Zoomed-in base material macros')."
    )
    follow_up_prompt: str = Field(
        description="The exact natural-language search command to execute when the user clicks this focus option."
    )


class ContactSheetVerification(BaseModel):
    visual_presentation_type: str = Field(
        description="One of: 'mushroom-head-hair-up', 'inverted-dome-base-up', 'macro-base-zoom', 'technical-callout-diagram', 'flat-circle-swatch', 'ring-swatch', 'mannequin-head', 'human-wearer-portrait'."
    )
    reference_analysis: str = Field(
        description="2-3 sentence expert explanation of the uploaded photo using The Hair Concierge Brain. Explicitly state: (a) photography style (e.g. studio e-commerce product shot, macro material close-up), (b) physical orientation (e.g. mushroom-head dome with base facing down/hidden revealing only full hair all around vs inverted base-side-up dome vs zoomed-in lace/skin material), and (c) visible shade code (#3, #1B20), base material, or wave texture."
    )
    clarification_question: str = Field(
        description="Conversational question asking the user what dimension they want to focus on for similar image search (e.g. 'What would you like me to focus on for this similar image search?')."
    )
    focus_options: List[FocusOption] = Field(
        description="3 to 4 distinct, actionable focus options tailored to the uploaded image (for example: 1) Exact presentation style across all colors/variants, 2) Specific hair color or grey blend family, 3) Specific base material like Swiss/French lace or thin skin, 4) Zoomed-in macro vs full unit orientation)."
    )
    suggested_album_title: str = Field(
        description="Concise 2-4 word album title for these matching photos (e.g. 'Mushroom-Head Hair Colors')."
    )
    query_summary: str = Field(
        description="Short phrase describing what was matched (e.g. 'hair-side-up mushroom-head hair systems across all color shades')."
    )
    verified_tile_numbers: List[int] = Field(
        description="Exact 1-based tile numbers (#1, #2, ...) from the contact sheets that visually match the user's reference photo orientation and prompt. CRITICAL: If the reference photo or prompt is for 'mushroom-head' full-hair domes (base facing down/hidden, full hair visible all around), STRICTLY EXCLUDE inverted base-side-up domes where the translucent poly/lace base cap is visible on top!"
    )
    detected_shades_or_codes: List[str] = Field(
        default_factory=list,
        description="List of hair color codes or shade names visible across the matched photos (e.g. ['#1', '#1A', '#1B', '#1B20', '#2', '#3', '#4ASH', '#6', '#18', '#22'])."
    )


def _open_rgb_over_white(img_path: Path) -> Image.Image:
    """Open an image and alpha-composite RGBA/palette transparency over studio white (255, 255, 255)."""
    with Image.open(img_path) as raw_img:
        im = ImageOps.exif_transpose(raw_img)
        if im.mode in ("RGBA", "LA") or (im.mode == "P" and "transparency" in im.info):
            rgba = im.convert("RGBA")
            white = Image.new("RGBA", rgba.size, (255, 255, 255, 255))
            return Image.alpha_composite(white, rgba).convert("RGB")
        return im.convert("RGB")


def resolve_fast_thumbnail(
    lib_path: Path,
    asset_id: str,
    storage_key: Optional[str],
) -> Optional[Path]:
    """Resolve the fastest local thumbnail or preview for an asset."""
    shard_dir = THUMB_CACHE_DIR / asset_id[:2]
    if shard_dir.exists():
        for pat in (f"v1-thumbnail-{asset_id}-*.png", f"v1-preview-{asset_id}-*.png"):
            matches = sorted(shard_dir.glob(pat))
            if matches:
                return matches[0]
    if storage_key:
        orig = lib_path / "Originals" / storage_key
        if orig.exists():
            return orig
    return None


def compute_color_invariant_descriptor(img_path: Path) -> Optional[np.ndarray]:
    """
    Compute a 522-dim float32 orientation-aware descriptor:
    - [0:256]: 16x16 color-invariant Foreground Silhouette Mask on a center-cropped 1:1 square (64x64)
               so 16:9 and 1:1 studio dome shots align in silhouette space regardless of hair shade (#1 black to #22 blonde).
    - [256:512]: 16x16 spatial gradient magnitude map.
    - [512:522]: Studio background lightness, border uniformity, aspect ratio, center mass,
                 top margin cleanliness, and Crown-vs-Skirt Material Uniformity (`crown_skirt_uniformity`,
                 which separates hair-side-up mushroom-head domes from inverted base-side-up domes!).
    """
    try:
        img = _open_rgb_over_white(img_path)
        w, h = img.size

        # Center-fit to 64x64 square so 16:9 mushroom-head shots and 1:1 studio dome shots share a canonical frame
        sq64 = ImageOps.fit(img, (64, 64), method=Image.Resampling.BILINEAR)
        a64 = np.asarray(sq64, dtype=np.float32)

        corners = np.concatenate(
            [
                a64[:6, :6].reshape(-1, 3),
                a64[:6, -6:].reshape(-1, 3),
                a64[-6:, :6].reshape(-1, 3),
                a64[-6:, -6:].reshape(-1, 3),
            ],
            axis=0,
        )
        bg_rgb = np.median(corners, axis=0)
        bg_std = float(np.mean(np.std(corners, axis=0)))
        bg_lightness = float(np.mean(bg_rgb)) / 255.0

        diff = np.linalg.norm(a64 - bg_rgb[None, None, :], axis=2) / 441.67
        fg64 = np.clip((diff - 0.06) / 0.35, 0.0, 1.0)

        fg16 = fg64.reshape(16, 4, 16, 4).mean(axis=(1, 3)).flatten()
        fg_norm = np.linalg.norm(fg16)
        if fg_norm > 1e-6:
            fg16 = fg16 / fg_norm

        gray64 = a64.mean(axis=2) / 255.0
        gx = np.abs(np.diff(gray64, axis=1, prepend=gray64[:, :1]))
        gy = np.abs(np.diff(gray64, axis=0, prepend=gray64[:1, :]))
        grad64 = np.hypot(gx, gy)
        grad16 = grad64.reshape(16, 4, 16, 4).mean(axis=(1, 3)).flatten()
        grad_norm = np.linalg.norm(grad16)
        if grad_norm > 1e-6:
            grad16 = grad16 / grad_norm

        # Crown-vs-Skirt Material Uniformity:
        # In a hair-side-up mushroom-head dome, upper dome (y=24..34) and lower skirt (y=36..44) have the SAME hair color/texture.
        # In an inverted base-side-up dome, upper dome is grey/beige translucent base and lower skirt is hair (large RGB jump + seam).
        upper_dome = a64[24:34, 20:44]
        lower_skirt = a64[36:44, 18:46]
        crown_skirt_l2 = float(np.linalg.norm(np.mean(upper_dome, axis=(0, 1)) - np.mean(lower_skirt, axis=(0, 1))))
        crown_skirt_uniformity = max(0.0, 1.0 - (crown_skirt_l2 / 60.0))

        # Top margin cleanliness (callouts / diagrams have dark text/circles in top 14 rows)
        top_margin_clean = 1.0 if (float(np.mean(a64[:12, :])) > 230.0 and float(np.std(a64[:12, :])) < 24.0) else 0.0

        aspect = float(w) / max(float(h), 1.0)
        border_uniformity = max(0.0, 1.0 - (bg_std / 64.0))
        center_mass = float(fg64[18:48, 12:52].mean())
        outer_ring = float(
            np.mean([fg64[:10, :].mean(), fg64[-10:, :].mean(), fg64[:, :10].mean(), fg64[:, -10:].mean()])
        )

        stats = np.array(
            [
                bg_lightness,
                border_uniformity,
                min(aspect / 2.0, 1.0),
                center_mass,
                outer_ring,
                float(fg64[:14, :].mean()),
                float(fg64[20:50, :].mean()),
                float(fg64[50:, :].mean()),
                crown_skirt_uniformity,
                top_margin_clean,
            ],
            dtype=np.float32,
        )

        return np.concatenate([fg16 * 0.70, grad16 * 0.45, stats * 0.45]).astype(np.float32)
    except Exception:
        return None


def load_or_build_library_index(
    lib_path: Path,
) -> Tuple[List[Dict[str, Any]], np.ndarray]:
    """Load catalog assets and build/update the cached 522-dim silhouette feature matrix (<50ms on repeat runs)."""
    db_path = lib_path / "Catalog" / "catalog.sqlite"
    conn = sqlite3.connect(str(db_path), timeout=30.0)
    c = conn.cursor()

    c.execute("SELECT id, name, parent_folder_id FROM folders")
    f_rows = c.fetchall()
    f_map = {r[0]: r for r in f_rows}
    folder_paths: Dict[str, str] = {}
    for fid, name, pid in f_rows:
        parts = [name]
        curr = pid
        visited = {fid}
        while curr and curr in f_map and curr not in visited:
            visited.add(curr)
            parts.append(f_map[curr][1])
            curr = f_map[curr][2]
        parts.reverse()
        folder_paths[fid] = "/".join(parts)

    c.execute(
        """
        SELECT a.id, a.filename, COALESCE(a.display_name, a.filename), a.storage_key,
               a.parent_folder_id, a.width, a.height
        FROM assets a
        WHERE a.id NOT IN (SELECT asset_id FROM asset_trash)
        ORDER BY a.imported_at_ms DESC
        """
    )
    asset_rows = c.fetchall()

    c.execute(
        """
        SELECT at.asset_id, GROUP_CONCAT(t.name, ' ')
        FROM asset_tags at
        JOIN tags t ON at.tag_id = t.id
        GROUP BY at.asset_id
        """
    )
    tags_by_asset = {r[0]: (r[1] or "").lower() for r in c.fetchall()}
    conn.close()

    cached_vecs: Dict[str, np.ndarray] = {}
    cached_thumbs: Dict[str, str] = {}
    if FEATURE_CACHE_PATH.exists():
        try:
            data = np.load(str(FEATURE_CACHE_PATH), allow_pickle=False)
            ids_arr = data["asset_ids"]
            mat_arr = data["features"]
            thumbs_arr = data["thumb_paths"]
            for aid_str, vec, tpath_str in zip(ids_arr, mat_arr, thumbs_arr):
                cached_vecs[str(aid_str)] = vec
                cached_thumbs[str(aid_str)] = str(tpath_str)
        except Exception:
            cached_vecs = {}
            cached_thumbs = {}

    records: List[Dict[str, Any]] = []
    vecs: List[np.ndarray] = []
    cache_dirty = False

    for aid, fn, disp, sk, fid, w, h in asset_rows:
        vec = cached_vecs.get(aid)
        tpath_str = cached_thumbs.get(aid)
        if vec is None or vec.shape[0] != 522 or not tpath_str:
            thumb = resolve_fast_thumbnail(lib_path, aid, sk)
            if not thumb:
                continue
            vec = compute_color_invariant_descriptor(thumb)
            if vec is None:
                continue
            tpath_str = str(thumb)
            cached_vecs[aid] = vec
            cached_thumbs[aid] = tpath_str
            cache_dirty = True

        fpath = folder_paths.get(fid, "")
        records.append(
            {
                "id": aid,
                "filename": fn,
                "display_name": disp,
                "folder": fpath,
                "width": w or 0,
                "height": h or 0,
                "tags": tags_by_asset.get(aid, ""),
                "thumb_path": tpath_str,
            }
        )
        vecs.append(vec)

    if cache_dirty and cached_vecs:
        try:
            FEATURE_CACHE_PATH.parent.mkdir(parents=True, exist_ok=True)
            all_ids = np.array(list(cached_vecs.keys()))
            all_mat = np.stack(list(cached_vecs.values()), axis=0)
            all_thumbs = np.array([cached_thumbs[k] for k in cached_vecs.keys()])
            np.savez_compressed(
                str(FEATURE_CACHE_PATH),
                asset_ids=all_ids,
                features=all_mat,
                thumb_paths=all_thumbs,
            )
        except Exception:
            pass

    if not vecs:
        return [], np.zeros((0, 522), dtype=np.float32)
    return records, np.stack(vecs, axis=0)


def build_contact_sheet(
    candidates: List[Dict[str, Any]],
    start_index: int = 1,
    cols: int = 6,
    rows: int = 4,
    tile_w: int = 220,
    tile_h: int = 180,
) -> bytes:
    """Render up to `cols * rows` candidate thumbnails onto a numbered JPEG contact sheet."""
    sheet = Image.new("RGB", (cols * tile_w, rows * tile_h), (24, 24, 28))
    draw = ImageDraw.Draw(sheet)

    for idx, item in enumerate(candidates[: cols * rows]):
        r = idx // cols
        c = idx % cols
        x0 = c * tile_w
        y0 = r * tile_h
        tile_num = start_index + idx

        try:
            tp = Path(item["thumb_path"])
            if not tp.exists():
                shard = item["id"][:2]
                candidates = sorted((THUMBNAIL_CACHE_ROOT / shard).glob(f"v1-thumbnail-{item['id']}-*.png"))
                if candidates:
                    tp = candidates[0]
            im = _open_rgb_over_white(tp)
            im.thumbnail((tile_w - 8, tile_h - 26), Image.Resampling.LANCZOS)
            px = x0 + (tile_w - im.width) // 2
            py = y0 + 22 + (tile_h - 26 - im.height) // 2
            sheet.paste(im, (px, py))
        except Exception:
            pass

        draw.rectangle([x0, y0, x0 + tile_w - 1, y0 + tile_h - 1], outline=(70, 70, 80), width=1)
        badge_text = f"#{tile_num}"
        draw.rectangle([x0 + 2, y0 + 2, x0 + 54, y0 + 20], fill=(15, 15, 18))
        draw.text((x0 + 6, y0 + 4), badge_text, fill=(255, 215, 80))

    buf = io.BytesIO()
    sheet.save(buf, format="JPEG", quality=86)
    return buf.getvalue()


def _shade_sort_key(rec: Dict[str, Any]) -> Tuple[int, str]:
    """Sort mushroom-head hair color assets in natural HSC shade order (#1, #1A, #1B, #1B05..#22)."""
    text = f"{rec.get('display_name', '')} {rec.get('filename', '')} {rec.get('tags', '')}"
    m = re.search(r"#([0-9A-Za-z]+)", text)
    code = m.group(1).upper() if m else rec.get("filename", "")
    lead_num = re.match(r"^(\d+)", code)
    num_val = int(lead_num.group(1)) if lead_num else 999
    return (num_val, code)


def run_visual_chat_search(
    lib_path: Path,
    prompt: str,
    image_path: Optional[Path] = None,
    limit: int = 80,
) -> Dict[str, Any]:
    t0 = time.time()
    records, feature_matrix = load_or_build_library_index(lib_path)
    if not records:
        return {
            "status": "empty",
            "matched_count": 0,
            "matched_assets": [],
            "reference_analysis": "No indexed thumbnails found in the current Framebase library.",
        }

    prompt_lower = prompt.lower()
    wants_base_up = any(
        k in prompt_lower
        for k in ("base-side-up", "base side up", "inverted dome", "base visible", "showing base", "exposed base")
    )
    wants_macro_zoom = any(
        k in prompt_lower
        for k in ("zoomed", "macro", "close-up", "closeup", "lace material", "mesh detail", "knots")
    )
    wants_mushroom_hair_up = not wants_base_up and not wants_macro_zoom and any(
        k in prompt_lower
        for k in ("mushroom", "dome", "hair-side-up", "hair side up", "different hair color", "hair colors", "base hidden", "full hair")
    )
    wants_grey_only = "grey" in prompt_lower or "gray" in prompt_lower or "blend" in prompt_lower
    wants_solid_only = "solid" in prompt_lower or "natural shade" in prompt_lower

    scores = np.zeros(len(records), dtype=np.float32)

    if image_path and image_path.exists():
        ref_vec = compute_color_invariant_descriptor(image_path)
        if ref_vec is not None:
            ref_norm = ref_vec / max(float(np.linalg.norm(ref_vec)), 1e-6)
            norms = np.linalg.norm(feature_matrix, axis=1, keepdims=True)
            normed_mat = feature_matrix / np.maximum(norms, 1e-6)
            scores = np.dot(normed_mat, ref_norm)

            # Check if reference image itself is a hair-side-up mushroom-head dome (high crown-skirt uniformity + clean top margin)
            ref_is_hair_up_dome = float(ref_vec[520]) > 0.30 and float(ref_vec[521]) > 0.30
            if ref_is_hair_up_dome and not wants_base_up and not wants_macro_zoom:
                wants_mushroom_hair_up = True

    for i, rec in enumerate(records):
        tags = rec["tags"]
        fn_l = rec["filename"].lower()
        folder_l = rec["folder"].lower()

        if wants_mushroom_hair_up:
            if "presentation:mushroom-head-hair-up" in tags or "orientation:hair-side-up" in tags:
                scores[i] += 0.45
            if "presentation:inverted-dome-base-up" in tags or "orientation:base-side-up" in tags:
                # Strictly penalize inverted base-side-up domes when looking for hair-side-up mushroom-heads!
                scores[i] -= 0.85
            if any(bad in fn_l for bad in ("side-view-main-product-shot", "feature-shot-white", "base-closeup", "details-shot", "split-knot", "variant-wizard")):
                scores[i] -= 0.75
            if wants_grey_only and "grey:0%" in tags:
                scores[i] -= 0.50
            elif wants_solid_only and "grey:" in tags and "grey:0%" not in tags:
                scores[i] -= 0.50
        elif wants_base_up:
            if "presentation:inverted-dome-base-up" in tags or "orientation:base-side-up" in tags:
                scores[i] += 0.50
            if "presentation:mushroom-head-hair-up" in tags:
                scores[i] -= 0.60
        elif wants_macro_zoom:
            if "shot:macro-base" in tags or "base-material" in folder_l or "base-closeup" in fn_l or "hairline-detail" in fn_l:
                scores[i] += 0.55
            if " lace" in prompt_lower and ("lace" in tags or "lace" in fn_l):
                scores[i] += 0.25

    top_indices = np.argsort(-scores)[:120]
    shortlist: List[Dict[str, Any]] = []
    seen_keys = set()
    for idx in top_indices:
        rec = dict(records[int(idx)])
        rec["similarity"] = round(float(scores[int(idx)]), 4)
        clean_fn = rec["filename"].lower().replace(".webp.webp", ".webp").replace(".jpg.jpg", ".jpg")
        dedup_key = (clean_fn, rec["width"], rec["height"])
        if dedup_key in seen_keys:
            continue
        seen_keys.add(dedup_key)
        shortlist.append(rec)
        if len(shortlist) >= 48:
            break

    sheet1_bytes = build_contact_sheet(shortlist[:24], start_index=1)
    sheet2_bytes = build_contact_sheet(shortlist[24:48], start_index=25) if len(shortlist) > 24 else None

    client = genai.Client(vertexai=True, project=PROJECT_ID, location=LOCATION)
    brain_context = get_sorter_grounding_context(fetch_live_rag=False)

    contents: List[Any] = []
    if image_path and image_path.exists():
        ref_rgb = _open_rgb_over_white(image_path)
        ref_rgb.thumbnail((1024, 1024), Image.Resampling.LANCZOS)
        buf = io.BytesIO()
        ref_rgb.save(buf, format="JPEG", quality=88)
        contents.append(types.Part.from_bytes(data=buf.getvalue(), mime_type="image/jpeg"))
        contents.append("IMAGE 1 ABOVE: The user's uploaded reference image.")

    contents.append(types.Part.from_bytes(data=sheet1_bytes, mime_type="image/jpeg"))
    contents.append("CONTACT SHEET 1 ABOVE: Library candidate tiles #1 through #24.")
    if sheet2_bytes:
        contents.append(types.Part.from_bytes(data=sheet2_bytes, mime_type="image/jpeg"))
        contents.append(f"CONTACT SHEET 2 ABOVE: Library candidate tiles #25 through #{len(shortlist)}.")

    verification_prompt = (
        f"You are the Framebase 2.0 Multimodal Hair System Visual Expert powered by Vertex AI Gemini 3.8 Flash and The Hair Concierge Brain.\n"
        f"{brain_context}\n\n"
        f"USER REQUEST: \"{prompt}\"\n\n"
        "INSTRUCTIONS:\n"
        "1. Deconstruct the user's uploaded reference photo (Image 1) and request with deep hair system photography expertise:\n"
        "   - Identify the exact `visual_presentation_type`: e.g. `mushroom-head-hair-up` (base material facing DOWN so it is hidden/invisible, revealing ONLY the full 360° hair dome and hair color all around), `inverted-dome-base-up` (base material facing UP on top of the dome), `macro-base-zoom` (zoomed-in close-up on lace/skin material), `technical-callout-diagram`, `flat-circle-swatch`, `ring-swatch`, etc.\n"
        "   - In `reference_analysis`, explain clearly what you see in the photo (photography style, physical orientation of the base vs hair, base material if visible, hair shade code like #3 or #1B20, wave pattern).\n"
        "2. Formulate a helpful `clarification_question` and 3-4 clickable `focus_options` (`label` numbered 1)..4) and `follow_up_prompt`) so the user can confirm or pivot what aspect they want to focus on:\n"
        "   - Example for a zoomed-in lace photo: 1) E-commerce style studio photography, 2) Lace material hair systems (Swiss & French lace), 3) Zoomed-in base material & hairline macro photos.\n"
        "   - Example for a mushroom-head full-hair dome: 1) All mushroom-head full-hair domes across all hair colors (base hidden underneath), 2) Natural solid shades only (#1 to #22 mushroom-heads), 3) Grey-blend mushroom-head domes (#1B05 to #740), 4) Inverted base-side-up construction domes (showing base material).\n"
        "3. Inspect every tile (#1 to #48) on the Contact Sheet(s) and return `verified_tile_numbers`:\n"
        "   - CRITICAL RULE: When matching `mushroom-head-hair-up` photos (base facing down, hidden underneath, revealing only full hair all around), ONLY select tiles where the base faces down and ONLY full hair is visible all around! NEVER select inverted base-side-up domes where the translucent poly/lace base cap is visible on top!\n"
        "4. Extract visible hair shade codes in `detected_shades_or_codes`."
    )
    contents.append(verification_prompt)

    verified_items: List[Dict[str, Any]] = []
    visual_type = "mushroom-head-hair-up" if wants_mushroom_hair_up else "ecommerce-product"
    ref_analysis = "Analyzed reference image and compared against Framebase library thumbnails."
    clarification_q = "What would you like me to focus on for this similar image search?"
    focus_opts: List[Dict[str, str]] = []
    album_title = "Mushroom-Head Hair Colors" if wants_mushroom_hair_up else "Visual Style Matches"
    query_summary = prompt
    detected_codes: List[str] = []

    for attempt in range(4):
        try:
            resp = client.models.generate_content(
                model=MODEL_NAME,
                contents=contents,
                config=types.GenerateContentConfig(
                    response_mime_type="application/json",
                    response_schema=ContactSheetVerification,
                    temperature=0.0,
                ),
            )
            parsed: Optional[ContactSheetVerification] = None
            if resp.parsed and isinstance(resp.parsed, ContactSheetVerification):
                parsed = resp.parsed
            else:
                raw = resp.text or "{}"
                if "```json" in raw:
                    raw = raw.split("```json")[1].split("```")[0].strip()
                parsed = ContactSheetVerification(**json.loads(raw))

            visual_type = parsed.visual_presentation_type
            ref_analysis = parsed.reference_analysis
            clarification_q = parsed.clarification_question
            focus_opts = [
                {"label": opt.label, "follow_up_prompt": opt.follow_up_prompt}
                for opt in (parsed.focus_options or [])
            ]
            album_title = parsed.suggested_album_title
            query_summary = parsed.query_summary
            detected_codes = parsed.detected_shades_or_codes or []
            for tnum in parsed.verified_tile_numbers:
                if 1 <= tnum <= len(shortlist):
                    verified_items.append(shortlist[tnum - 1])
            break
        except Exception as err:
            time.sleep(2.0 * (attempt + 1))
            if attempt == 3:
                ref_analysis = f"Visual orientation match completed (Vertex AI note: {err})."

    # If the user is searching for mushroom-head hair-side-up domes across all hair colors, include ALL verified
    # `presentation:mushroom-head-hair-up` assets in the library (so all 56+ #1..#22 shades are included in the album!)
    if (wants_mushroom_hair_up or visual_type == "mushroom-head-hair-up") and not wants_base_up and not wants_macro_zoom:
        filtered_initial: List[Dict[str, Any]] = []
        verified_ids = set()
        for item in verified_items:
            t_str = item.get("tags", "")
            if "orientation:base-side-up" in t_str or "presentation:inverted-dome-base-up" in t_str:
                continue
            if wants_grey_only and "grey:0%" in t_str:
                continue
            if wants_solid_only and "grey:" in t_str and "grey:0%" not in t_str:
                continue
            filtered_initial.append(item)
            verified_ids.add(item["id"])
        verified_items = filtered_initial

        for rec in records:
            tags = rec["tags"]
            if "presentation:mushroom-head-hair-up" in tags and "orientation:base-side-up" not in tags:
                if wants_grey_only and "grey:0%" in tags:
                    continue
                if wants_solid_only and "grey:" in tags and "grey:0%" not in tags:
                    continue
                if rec["id"] not in verified_ids:
                    r_copy = dict(rec)
                    r_copy["similarity"] = 0.95
                    verified_items.append(r_copy)
                    verified_ids.add(rec["id"])
        verified_items.sort(key=_shade_sort_key)
        all_shades = []
        for item in verified_items:
            m = re.search(r"shade:(#[0-9a-zA-Z]+)", item.get("tags", ""))
            if m:
                code_up = m.group(1).upper()
                if code_up not in all_shades:
                    all_shades.append(code_up)
        if all_shades:
            detected_codes = all_shades

    if not verified_items:
        verified_items = shortlist[: min(limit, 24)]

    if not focus_opts:
        focus_opts = [
            {
                "label": "1) Mushroom-Head Full-Hair Domes (All Hair Colors, Base Hidden)",
                "follow_up_prompt": "Find me all the mushroom-head style photos of hair systems showing different hair colors with the base hidden underneath",
            },
            {
                "label": "2) Natural Solid Hair Shades Only (#1 to #22 Mushroom-Heads)",
                "follow_up_prompt": "Find mushroom-head hair-side-up dome photos showing only natural solid shades",
            },
            {
                "label": "3) Grey-Blend Mushroom-Head Domes (#1B05 to #740)",
                "follow_up_prompt": "Find mushroom-head hair-side-up dome photos showing grey blend percentages",
            },
            {
                "label": "4) Zoomed-In Base Material & Lace Macros",
                "follow_up_prompt": "Find zoomed-in base material and lace hairline macro e-commerce photos",
            },
        ]

    elapsed = round(time.time() - t0, 2)
    return {
        "status": "ok",
        "model": MODEL_NAME,
        "project": PROJECT_ID,
        "location": LOCATION,
        "latency_sec": elapsed,
        "visual_presentation_type": visual_type,
        "reference_analysis": ref_analysis,
        "clarification_question": clarification_q,
        "focus_options": focus_opts,
        "suggested_album_title": album_title,
        "query_summary": query_summary,
        "detected_shades_or_codes": detected_codes,
        "matched_count": len(verified_items[:limit]),
        "matched_assets": verified_items[:limit],
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Framebase 2.0 Multimodal Vision Chat Search")
    parser.add_argument(
        "--library-path",
        type=Path,
        default=Path.home() / "Pictures/HSC Library.framebase",
        help="Path to the .framebase library bundle",
    )
    parser.add_argument("--prompt", "-p", type=str, required=True, help="User natural-language prompt")
    parser.add_argument("--image", "-i", type=Path, default=None, help="Optional path to uploaded reference image")
    parser.add_argument("--limit", type=int, default=80, help="Max matched assets to return")
    args = parser.parse_args()

    result = run_visual_chat_search(
        lib_path=args.library_path,
        prompt=args.prompt,
        image_path=args.image,
        limit=args.limit,
    )
    print(json.dumps(result, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()

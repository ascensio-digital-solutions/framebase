#!/usr/bin/env python3
"""
High-Speed Local MLX Classifier using Qwen 2.5 VL 32B (4-bit quantized).
Optimized with:
1. 448px resolution downscaling (reducing visual tokens from 1280 to 256 for 3x+ speedup)
2. Direct in-memory PIL processing (no disk /tmp I/O bottlenecks)
3. Proactive Metal GPU cache management to prevent memory bloat/swap
4. Local InsightFace Vincent facial recognition
5. Specialized Screenshot & Shopping classification rules
6. 2017-2026 year scoping with safe SQLite transactional persistence
"""

import sqlite3
import time
import json
import os
import sys
import gc
import argparse
from pathlib import Path
from PIL import Image
from PIL.ExifTags import TAGS
from pillow_heif import register_heif_opener
import numpy as np
import mlx.core as mx
import mlx_vlm
from mlx_vlm.prompt_utils import apply_chat_template

register_heif_opener()

# Add current directory to path to import taxonomy
SCRIPT_DIR = Path(__file__).parent
sys.path.append(str(SCRIPT_DIR))
from taxonomy import ClassificationResult

DB_PATH = SCRIPT_DIR / "state.sqlite"
MODEL_PATH = Path("/Users/vincent/mlx-models/qwen2.5-vl-32b")
REF_DIR = SCRIPT_DIR / "reference_faces"

# InsightFace setup
try:
    from insightface.app import FaceAnalysis
    HAVE_INSIGHTFACE = True
except ImportError:
    HAVE_INSIGHTFACE = False

def get_db():
    conn = sqlite3.connect(str(DB_PATH), timeout=60.0)
    conn.execute("PRAGMA journal_mode=WAL;")
    conn.execute("PRAGMA busy_timeout=60000;")
    return conn

def is_screenshot_metadata(img: Image.Image, filename: str) -> bool:
    """Deterministic check for Apple and system screenshot metadata."""
    try:
        if 'xmp' in img.info and b'Screenshot' in img.info['xmp']:
            return True
        if 'XML:com.adobe.xmp' in img.info and 'Screenshot' in str(img.info['XML:com.adobe.xmp']):
            return True
        exif = img.getexif()
        if exif:
            for tag_id, value in exif.items():
                tag = TAGS.get(tag_id, tag_id)
                if tag == 'UserComment' and 'Screenshot' in str(value):
                    return True
    except Exception:
        pass

    fname_lower = filename.lower()
    if 'screenshot' in fname_lower or 'capture d’écran' in fname_lower:
        return True

    return False

def load_reference_embeddings(face_app):
    """Load face embeddings for Vincent from reference_faces/ directory."""
    embeddings = []
    if not REF_DIR.exists() or face_app is None:
        return embeddings

    for p in REF_DIR.glob("*.*"):
        if p.suffix.lower() in [".jpg", ".jpeg", ".png", ".heic", ".webp"]:
            try:
                with Image.open(p) as img:
                    img_rgb = img.convert("RGB")
                    img_bgr = np.array(img_rgb)[:, :, ::-1].copy()
                faces = face_app.get(img_bgr)
                for f in faces:
                    embeddings.append(f.normed_embedding)
            except Exception as e:
                print(f"[Warning] Could not load reference face from {p.name}: {e}")

    return embeddings

def detect_vincent(img_rgb: Image.Image, face_app, ref_embeddings, threshold: float = 0.45):
    """Detect if Vincent's face is present in the image using InsightFace."""
    if not ref_embeddings or face_app is None:
        return False

    try:
        img_bgr = np.array(img_rgb)[:, :, ::-1].copy()
        faces = face_app.get(img_bgr)
        for face in faces:
            for ref_emb in ref_embeddings:
                sim = float(np.dot(face.normed_embedding, ref_emb))
                if sim >= threshold:
                    return True
        return False
    except Exception:
        return False

def prepare_image_fast(img_path: Path, max_dim: int = 448):
    """
    3x Faster image preparation:
    - Downscaled to max 448px (reduces visual tokens from 1280 to 256)
    - Directly in-memory (no disk /tmp bottleneck)
    """
    with Image.open(img_path) as img:
        is_screenshot = is_screenshot_metadata(img, img_path.name)
        img.thumbnail((max_dim, max_dim), Image.Resampling.LANCZOS)
        if img.mode != "RGB":
            img = img.convert("RGB")
        return img.copy(), is_screenshot

def main():
    parser = argparse.ArgumentParser(description="Run Qwen2.5-VL-32B MLX photo classifier with 3x speed optimizations")
    parser.add_argument("--min-year", type=int, default=2017, help="Minimum year (default: 2017)")
    parser.add_argument("--max-year", type=int, default=2026, help="Maximum year (default: 2026)")
    parser.add_argument("--limit", type=int, default=None, help="Max images to process")
    parser.add_argument("--resolution", type=int, default=448, help="Max image thumbnail resolution for 3x speed (default: 448)")
    parser.add_argument("--model-path", type=str, default=str(MODEL_PATH), help="Path to MLX model")
    parser.add_argument("--skip-face-detection", action="store_true", help="Skip InsightFace Vincent detection")
    args = parser.parse_args()

    model_dir = Path(args.model_path)
    if not model_dir.exists():
        print(f"FATAL: Model directory {model_dir} does not exist.")
        sys.exit(1)

    # 1. Initialize Face Recognition
    face_app = None
    ref_embeddings = []
    if HAVE_INSIGHTFACE and not args.skip_face_detection:
        print("[Face Recognition] Initializing InsightFace buffalo_s...")
        try:
            face_app = FaceAnalysis(name='buffalo_s')
            face_app.prepare(ctx_id=0, det_size=(640, 640))
            ref_embeddings = load_reference_embeddings(face_app)
            print(f"[Face Recognition] Loaded {len(ref_embeddings)} reference face embeddings for Vincent.")
        except Exception as e:
            print(f"[Face Recognition] Warning: Could not initialize InsightFace ({e}).")

    # 2. Load Local MLX Model
    print(f"[{time.strftime('%X')}] Loading local Qwen2.5-VL-32B MLX model into Unified Memory...")
    start_load = time.time()
    model, processor = mlx_vlm.load(str(model_dir))
    print(f"[{time.strftime('%X')}] Model loaded in {time.time() - start_load:.1f}s!")

    schema = ClassificationResult.model_json_schema()

    # 3. Query eligible photos
    conn = get_db()
    c = conn.cursor()

    query = """
        SELECT id, file_path, year, filename 
        FROM inventory 
        WHERE qwen_json IS NULL 
          AND local_only = 0 
          AND is_sidecar = 0 
          AND is_live_video = 0
          AND LOWER(extension) IN ('.jpg', '.jpeg', '.png', '.heic', '.webp', '.tiff', '.tif')
          AND year >= ? AND year <= ?
        ORDER BY id ASC
    """
    params = [args.min_year, args.max_year]
    if args.limit:
        query += f" LIMIT {args.limit}"

    c.execute(query, params)
    rows = c.fetchall()
    conn.close()

    total = len(rows)
    print(f"\n=======================================================")
    print(f"  LOCAL QWEN2.5-VL-32B MLX CLASSIFIER (3X SPEED OPTIMIZED)")
    print(f"=======================================================")
    print(f"Scope:             Years {args.min_year} - {args.max_year}")
    print(f"Eligible Photos:   {total}")
    print(f"Resolution:        {args.resolution}px (3x visual token reduction)")
    print(f"Face Detection:    {'Enabled (' + str(len(ref_embeddings)) + ' refs)' if ref_embeddings else 'Disabled'}")
    print(f"Model Path:        {model_dir}")
    print(f"Database:          {DB_PATH}")
    print(f"=======================================================\n")

    if total == 0:
        print("No unclassified photos found for criteria.")
        return

    processed = 0
    success = 0
    vincent_count = 0
    screenshots_count = 0
    shopping_count = 0
    start_all = time.time()

    for row_id, path_str, year, filename in rows:
        path = Path(path_str)
        if not path.exists():
            print(f"[{row_id}] File missing: {path}")
            continue

        start_t = time.time()
        try:
            # 1. 3x Fast in-memory image preparation
            pil_img, is_screenshot = prepare_image_fast(path, max_dim=args.resolution)

            # 2. Local Vincent face detection
            has_vincent = False
            if ref_embeddings:
                has_vincent = detect_vincent(pil_img, face_app, ref_embeddings)

            # 3. Prompt Construction
            face_hint = ""
            if has_vincent:
                face_hint = (
                    "\nCRITICAL NOTE: Facial recognition has confirmed that Vincent (the library owner) is in this photo. "
                    "When describing the photo, assigning domain, or generating tags, note that Vincent is the main subject/present (e.g. 'Vincent portrait', 'Vincent with friends')."
                )

            meta_hint = ""
            if is_screenshot:
                meta_hint = "\nNOTE: File metadata confirms this image is an on-device screenshot."

            raw_prompt = (
                f"Analyze this image and classify it strictly according to this JSON schema: {json.dumps(schema)}.{face_hint}{meta_hint}\n"
                "IMPORTANT INSTRUCTIONS FOR SCREENSHOTS, APPS & SHOPPING:\n"
                "1. If this is a screenshot, set capture_type='screenshot'. Determine the specific app if visible (e.g. Grindr, WhatsApp, Instagram, Facebook, Amazon, eBay, Safari).\n"
                "2. If it is a Grindr screenshot, category must be '99_noise_and_review/screenshots/grindr' and app_name='Grindr'.\n"
                "3. If it is a WhatsApp screenshot, category must be '99_noise_and_review/screenshots/whatsapp' and app_name='WhatsApp'.\n"
                "4. If it is an Instagram screenshot, category must be '99_noise_and_review/screenshots/instagram' and app_name='Instagram'.\n"
                "5. If it is a Facebook screenshot, category must be '99_noise_and_review/screenshots/facebook' and app_name='Facebook'.\n"
                "6. If it is a shopping screenshot, product listing, e-commerce store, cart, store label, or price tag (e.g. Amazon, eBay, online store, retail price sticker, packaging label): "
                "category must be '99_noise_and_review/screenshots/shopping', is_shopping=true, and app_name should be the store name (e.g. 'Amazon', 'eBay', or retail store).\n"
                "7. For any other screenshot: if personal, use '99_noise_and_review/screenshots/personal_other'; if business, use '99_noise_and_review/screenshots/business'.\n"
                "Return ONLY the valid JSON object conforming to the schema."
            )

            formatted_prompt = apply_chat_template(
                processor,
                config=model.config,
                prompt=raw_prompt,
                num_images=1
            )

            # 4. Generate classification in-memory
            output = mlx_vlm.generate(
                model,
                processor,
                prompt=formatted_prompt,
                image=pil_img,
                max_tokens=256,
                temperature=0.0,
                verbose=False
            )
            text = output.text if hasattr(output, 'text') else str(output)

            # Strip markdown formatting
            if "```json" in text:
                text = text.split("```json")[1].split("```")[0].strip()
            elif "```" in text:
                text = text.split("```")[1].split("```")[0].strip()

            data = json.loads(text)
            result = ClassificationResult(**data)

            if has_vincent:
                result.has_vincent = True
                if "vincent" not in [t.lower() for t in result.tags]:
                    result.tags.append("vincent")
                vincent_count += 1

            if result.capture_type.value == "screenshot":
                screenshots_count += 1
            if result.is_shopping:
                shopping_count += 1

            cat = result.category.value if result.category else "unknown"
            conf = result.confidence
            res_json = result.model_dump_json()

            # 5. Persist to SQLite with retry
            for attempt in range(5):
                try:
                    update_conn = get_db()
                    update_conn.execute("""
                        UPDATE inventory 
                        SET qwen_category = ?, qwen_confidence = ?, qwen_json = ?, has_vincent = ?
                        WHERE id = ?
                    """, (cat, conf, res_json, 1 if has_vincent else 0, row_id))
                    update_conn.commit()
                    update_conn.close()
                    break
                except sqlite3.OperationalError:
                    time.sleep(0.3)

            elapsed = time.time() - start_t
            processed += 1
            success += 1

            # Periodic cache clearing to prevent memory bloat
            if processed % 5 == 0:
                mx.metal.clear_cache()
                gc.collect()

            v_tag = " [👤 VINCENT]" if has_vincent else ""
            app_tag = f" [📱 {result.app_name}]" if result.app_name else ""
            shop_tag = " [🛒 SHOPPING]" if result.is_shopping else ""

            total_elapsed = time.time() - start_all
            speed = processed / total_elapsed if total_elapsed > 0 else 0
            eta_m = (total - processed) / speed / 60 if speed > 0 else 0

            print(
                f"[{processed}/{total}] ({speed:.2f} img/s | ETA: {eta_m:.1f}m) | "
                f"{path.name} -> {cat}{v_tag}{app_tag}{shop_tag} ({elapsed:.1f}s)",
                flush=True
            )

        except Exception as e:
            elapsed = time.time() - start_t
            processed += 1
            print(f"[{processed}/{total}] FAILED ({elapsed:.1f}s) on {path.name}: {e}", flush=True)

    print(f"\n[{time.strftime('%X')}] [Local Qwen2.5-VL-32B MLX] Finished! Processed {processed}/{total}, Success: {success}")

if __name__ == "__main__":
    main()

import sqlite3
import time
import json
import io
import os
import sys
import argparse
from pathlib import Path
from PIL import Image
from pillow_heif import register_heif_opener
from dotenv import load_dotenv

register_heif_opener()

# Load environment
load_dotenv("/Users/vincent/.env")
api_key = os.environ.get("GEMINI_API_KEY")
if not api_key:
    print("FATAL: GEMINI_API_KEY missing from environment and /Users/vincent/.env")
    sys.exit(1)

from google import genai
from google.genai import types

# Add current dir to path to import taxonomy
sys.path.append(str(Path(__file__).parent))
from taxonomy import ClassificationResult

DB_PATH = Path(__file__).parent / "state.sqlite"

def get_db():
    conn = sqlite3.connect(str(DB_PATH), timeout=60.0)
    conn.execute("PRAGMA journal_mode=WAL;")
    conn.execute("PRAGMA busy_timeout=60000;")
    return conn

def classify_image_gemini(client: genai.Client, img_path: Path) -> ClassificationResult | None:
    try:
        with Image.open(img_path) as img:
            img.thumbnail((1536, 1536), Image.Resampling.LANCZOS)
            if img.mode != "RGB":
                img = img.convert("RGB")
            buf = io.BytesIO()
            img.save(buf, format="JPEG", quality=85)
            img_bytes = buf.getvalue()
    except Exception as e:
        print(f"Error reading {img_path}: {e}")
        return None

    # Retry with backoff for rate limits or temporary server demand
    max_retries = 3
    for attempt in range(max_retries):
        try:
            response = client.models.generate_content(
                model='gemini-2.5-flash',
                contents=[
                    'Analyze this image and classify it strictly according to the schema.',
                    types.Part.from_bytes(data=img_bytes, mime_type='image/jpeg')
                ],
                config=types.GenerateContentConfig(
                    response_mime_type='application/json',
                    response_schema=ClassificationResult,
                )
            )
            data = json.loads(response.text)
            return ClassificationResult(**data)
        except Exception as e:
            err_str = str(e)
            if "429" in err_str or "503" in err_str:
                wait_sec = (attempt + 1) * 3
                print(f"Gemini busy/rate-limit ({err_str[:40]}...), retrying in {wait_sec}s...")
                time.sleep(wait_sec)
            else:
                print(f"Gemini error on {img_path.name}: {e}")
                return None
    return None

def main():
    parser = argparse.ArgumentParser(description="Run Gemini 2.5 Flash photo classifier")
    parser.add_argument("--limit", type=int, default=None, help="Max images to process")
    args = parser.parse_args()

    client = genai.Client(api_key=api_key)

    conn = get_db()
    c = conn.cursor()

    query = """
        SELECT id, file_path 
        FROM inventory 
        WHERE gemini_json IS NULL 
          AND local_only = 0 
          AND is_sidecar = 0 
          AND is_live_video = 0
          AND LOWER(extension) IN ('.jpg', '.jpeg', '.png', '.heic', '.webp', '.tiff', '.tif')
        ORDER BY id ASC
    """
    if args.limit:
        query += f" LIMIT {args.limit}"

    c.execute(query)
    rows = c.fetchall()
    conn.close()

    total = len(rows)
    print(f"[{time.strftime('%X')}] [Gemini 2.5 Flash] Starting batch of {total} photos...")

    processed = 0
    success = 0

    for row_id, path_str in rows:
        path = Path(path_str)
        if not path.exists():
            print(f"[{row_id}] File missing: {path}")
            continue

        start_t = time.time()
        result = classify_image_gemini(client, path)
        elapsed = time.time() - start_t

        if result:
            success += 1
            cat = result.category.value if result.category else "unknown"
            conf = result.confidence
            res_json = result.model_dump_json()

            # Retry DB update if locked
            for attempt in range(5):
                try:
                    update_conn = get_db()
                    update_conn.execute("""
                        UPDATE inventory 
                        SET gemini_category = ?, gemini_confidence = ?, gemini_json = ?
                        WHERE id = ?
                    """, (cat, conf, res_json, row_id))
                    update_conn.commit()
                    update_conn.close()
                    break
                except sqlite3.OperationalError:
                    time.sleep(0.5)

            processed += 1
            print(f"[{processed}/{total}] Gemini ({elapsed:.1f}s): {path.name} -> {cat} ({result.domain.value}, conf: {conf:.2f})")
        else:
            processed += 1
            print(f"[{processed}/{total}] Gemini FAILED ({elapsed:.1f}s): {path.name}")

        # Pacing to avoid hitting burst rate limits
        time.sleep(0.4)

    print(f"[{time.strftime('%X')}] [Gemini 2.5 Flash] Finished! Processed {processed}/{total}, Success: {success}")

if __name__ == "__main__":
    main()

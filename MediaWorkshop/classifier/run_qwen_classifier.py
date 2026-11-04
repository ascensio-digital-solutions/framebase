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
import ollama

register_heif_opener()

# Add current dir to path to import taxonomy
sys.path.append(str(Path(__file__).parent))
from taxonomy import ClassificationResult

DB_PATH = Path(__file__).parent / "state.sqlite"

def get_db():
    conn = sqlite3.connect(str(DB_PATH), timeout=60.0)
    conn.execute("PRAGMA journal_mode=WAL;")
    conn.execute("PRAGMA busy_timeout=60000;")
    return conn

def classify_image_qwen(img_path: Path) -> ClassificationResult | None:
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

    schema = ClassificationResult.model_json_schema()
    try:
        res = ollama.chat(
            model='qwen3.8:27b-mlx',
            messages=[{
                'role': 'user',
                'content': f"Analyze this image and classify it strictly according to this JSON schema: {json.dumps(schema)}",
                'images': [img_bytes]
            }],
            options={'temperature': 0.0}
        )
        msg = res['message']['content']
        if "```json" in msg:
            msg = msg.split("```json")[1].split("```")[0].strip()
        elif "```" in msg:
            msg = msg.split("```")[1].split("```")[0].strip()
        data = json.loads(msg)
        return ClassificationResult(**data)
    except Exception as e:
        print(f"Qwen error on {img_path.name}: {e}")
        return None

def main():
    parser = argparse.ArgumentParser(description="Run Qwen 3.8 photo classifier")
    parser.add_argument("--limit", type=int, default=None, help="Max images to process")
    args = parser.parse_args()

    conn = get_db()
    c = conn.cursor()

    query = """
        SELECT id, file_path 
        FROM inventory 
        WHERE qwen_json IS NULL 
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
    print(f"[{time.strftime('%X')}] [Qwen 3.8] Starting batch of {total} photos...")

    processed = 0
    success = 0

    for row_id, path_str in rows:
        path = Path(path_str)
        if not path.exists():
            print(f"[{row_id}] File missing: {path}")
            continue

        start_t = time.time()
        result = classify_image_qwen(path)
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
                        SET qwen_category = ?, qwen_confidence = ?, qwen_json = ?
                        WHERE id = ?
                    """, (cat, conf, res_json, row_id))
                    update_conn.commit()
                    update_conn.close()
                    break
                except sqlite3.OperationalError:
                    time.sleep(0.5)

            processed += 1
            print(f"[{processed}/{total}] Qwen ({elapsed:.1f}s): {path.name} -> {cat} ({result.domain.value}, conf: {conf:.2f})")
        else:
            processed += 1
            print(f"[{processed}/{total}] Qwen FAILED ({elapsed:.1f}s): {path.name}")

    print(f"[{time.strftime('%X')}] [Qwen 3.8] Finished! Processed {processed}/{total}, Success: {success}")

if __name__ == "__main__":
    main()

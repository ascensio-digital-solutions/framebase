#!/usr/bin/env python3
"""
High-Speed Async Photo Classifier using Qwen 3 VL 32B via OpenRouter.
Targets photos from 2017 to 2026, with local InsightFace detection for Vincent,
specialized screenshot/shopping detection, and thread-safe SQLite persistence.
"""

import os
import sys
import json
import time
import io
import base64
import random
import sqlite3
import asyncio
import logging
import argparse
from pathlib import Path
from typing import Optional, List, Tuple
from dotenv import load_dotenv
import numpy as np
from PIL import Image
from PIL.ExifTags import TAGS
from pillow_heif import register_heif_opener
import httpx

register_heif_opener()

# Load environment variables
load_dotenv("/Users/vincent/.env")
load_dotenv(Path(__file__).parent / ".env")

# Add script directory to sys.path to import taxonomy
SCRIPT_DIR = Path(__file__).parent
sys.path.append(str(SCRIPT_DIR))
from taxonomy import ClassificationResult, Category, get_final_category

DB_PATH = SCRIPT_DIR / "state.sqlite"
REF_DIR = SCRIPT_DIR / "reference_faces"

OPENROUTER_URL = "https://openrouter.ai/api/v1/chat/completions"
DEFAULT_MODEL = "qwen/qwen3-vl-32b-instruct"

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

def init_db_schema():
    conn = get_db()
    try:
        conn.execute("ALTER TABLE inventory ADD COLUMN has_vincent INTEGER DEFAULT 0")
        conn.commit()
    except sqlite3.OperationalError:
        pass
    conn.close()

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

def load_reference_embeddings(face_app) -> List[np.ndarray]:
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

def detect_vincent_in_image(img_rgb: Image.Image, face_app, ref_embeddings: List[np.ndarray], threshold: float = 0.45) -> Tuple[bool, int]:
    """Detect if Vincent's face is present in the image using InsightFace."""
    if not ref_embeddings or face_app is None:
        return False, 0

    try:
        img_bgr = np.array(img_rgb)[:, :, ::-1].copy()
        faces = face_app.get(img_bgr)
        for face in faces:
            for ref_emb in ref_embeddings:
                sim = float(np.dot(face.normed_embedding, ref_emb))
                if sim >= threshold:
                    return True, len(faces)
        return False, len(faces)
    except Exception:
        return False, 0

def prepare_image(img_path: Path) -> Tuple[str, Image.Image, bool]:
    """Resize image to max 1024px, compress to JPEG base64, and check screenshot metadata."""
    with Image.open(img_path) as img:
        is_screenshot = is_screenshot_metadata(img, img_path.name)
        img.thumbnail((1024, 1024), Image.Resampling.LANCZOS)
        if img.mode != "RGB":
            img = img.convert("RGB")
        
        buf = io.BytesIO()
        img.save(buf, format="JPEG", quality=85)
        img_b64 = base64.b64encode(buf.getvalue()).decode("utf-8")
        return img_b64, img.copy(), is_screenshot

class Stats:
    def __init__(self, total: int):
        self.total = total
        self.processed = 0
        self.success = 0
        self.failed = 0
        self.vincent_count = 0
        self.screenshots_count = 0
        self.shopping_count = 0
        self.total_cost = 0.0
        self.total_tokens = 0
        self.start_time = time.time()
        self.lock = asyncio.Lock()

    async def update(self, success: bool, has_vincent: bool, is_screenshot: bool, is_shopping: bool, cost: float, tokens: int):
        async with self.lock:
            self.processed += 1
            if success:
                self.success += 1
            else:
                self.failed += 1
            if has_vincent:
                self.vincent_count += 1
            if is_screenshot:
                self.screenshots_count += 1
            if is_shopping:
                self.shopping_count += 1
            self.total_cost += cost
            self.total_tokens += tokens

    def get_summary_str(self) -> str:
        elapsed = time.time() - self.start_time
        speed = self.processed / elapsed if elapsed > 0 else 0
        remaining = self.total - self.processed
        eta_s = remaining / speed if speed > 0 else 0
        eta_min = eta_s / 60
        return (
            f"[{self.processed}/{self.total}] ({speed:.1f} img/s | ETA: {eta_min:.1f}m) | "
            f"Success: {self.success} | Failed: {self.failed} | "
            f"Vincent: {self.vincent_count} | Screenshots: {self.screenshots_count} | "
            f"Cost: ${self.total_cost:.4f}"
        )

async def classify_worker(
    queue: asyncio.Queue,
    client: httpx.AsyncClient,
    api_key: str,
    model_name: str,
    face_app,
    ref_embeddings: List[np.ndarray],
    stats: Stats,
    schema_json: str,
    dry_run: bool = False
):
    while True:
        item = await queue.get()
        if item is None:
            queue.task_done()
            break

        row_id, path_str, year, filename = item
        img_path = Path(path_str)

        if not img_path.exists():
            print(f"[{row_id}] File missing on disk: {img_path.name}")
            await stats.update(False, False, False, False, 0.0, 0)
            queue.task_done()
            continue

        item_start = time.time()
        try:
            # 1. Prepare thumbnail and check screenshot metadata
            img_b64, pil_img, meta_screenshot = prepare_image(img_path)

            # 2. Local InsightFace check for Vincent
            has_vincent = False
            if ref_embeddings:
                has_vincent, num_faces = detect_vincent_in_image(pil_img, face_app, ref_embeddings)

            # 3. Construct intelligent prompt
            face_hint = ""
            if has_vincent:
                face_hint = (
                    "\nCRITICAL NOTE: Facial recognition has confirmed that Vincent (the library owner) is in this photo. "
                    "When describing the photo, assigning domain, or generating tags, note that Vincent is the main subject/present (e.g. 'Vincent portrait', 'Vincent with friends')."
                )

            screenshot_hint = ""
            if meta_screenshot:
                screenshot_hint = "\nNOTE: File metadata confirms this image is an on-device screenshot."

            prompt = (
                f"Analyze this image and classify it strictly according to this JSON schema: {schema_json}.{face_hint}{screenshot_hint}\n\n"
                "CRITICAL TAXONOMY & CLASSIFICATION RULES:\n"
                "1. VINCENT (THE LIBRARY OWNER):\n"
                "   - has_vincent must ONLY be true if Vincent's human FACE is physically visible in the photo.\n"
                "   - NEVER set has_vincent=true just because the name 'Vincent' or 'Vincent Laroche' is written as text on an invoice, bank statement, WhatsApp message, email, or profile. Text mentions are NOT a human face!\n\n"
                "2. FINANCES, BILLS & INVOICES:\n"
                "   - Any invoice, utility bill (water, electric, gas), receipt, Boleto, Pix transfer receipt, bank transfer, bank statement (e.g. Nubank, Revolut, Mercado Pago, Neon, PicPay), tax form, or payment confirmation:\n"
                "     MUST be classified as category='finances/bills_invoices' with sensitivity='financial_document'.\n"
                "   - Do NOT classify bills or invoices as business screenshots or personal portraits.\n\n"
                "3. SHOPIFY & STORE BUILDING KNOWLEDGE:\n"
                "   - Any screenshot, slide, or post discussing Shopify store architecture, ideal product page (PDP) structure, e-commerce conversion rate optimization (CRO), e-commerce navigation, Shopify themes/apps, or how to build an online store:\n"
                "     MUST be classified as category='business/shopify', domain='business', app_name='Shopify', tags=['shopify', 'ecommerce', ...].\n\n"
                "4. USER'S BUSINESS (HAIR SOLUTIONS CO) VS PERSONAL CONSUMER ITEMS:\n"
                "   - The user's ONLY business is 'Hair Solutions Co' (men's hair replacement systems, toupees, hair pieces, wig lace, base cap construction, hair density swatches, hair factory/supplier chats like OneHead, and client hair before/afters).\n"
                "     ONLY these hair system items can be classified as business/01_products or business/*!\n"
                "   - ALL OTHER physical products or consumer goods are strictly PERSONAL:\n"
                "     * Household appliances (water heaters like Rinnai, air conditioners, furniture) -> personal/home_daily\n"
                "     * Pharmacy medications, blister packs, pill bottles, ointments, creams (e.g. Fucidine, Cimecort) -> personal/home_daily\n"
                "     * Clothing, shoe or brand tags (Adidas, Nike, Zara) -> personal/home_daily or personal/people\n"
                "     * Smartwatch bands, Apple Watch straps, jewelry, personal gadgets -> personal/home_daily\n"
                "     * Gym, fitness, sports, lifting weights -> personal/sports_hobbies\n"
                "     * Food, meals, cooking, restaurants, groceries -> personal/food\n"
                "     Do NOT classify appliances, medicines, or watch straps as business/01_products!\n\n"
                "5. SCREENSHOT APPS HIERARCHY:\n"
                "   - If capture_type is 'screenshot':\n"
                "     * If financial invoice/bill/bank transfer -> category='finances/bills_invoices'\n"
                "     * If discussing Shopify architecture/stores -> category='business/shopify'\n"
                "     * If retail shopping store (Amazon, Mercado Livre, Shopee, Zara, AliExpress) -> category='99_noise_and_review/screenshots/shopping', is_shopping=true\n"
                "     * If Instagram post/story/reel -> category='99_noise_and_review/screenshots/instagram', app_name='Instagram'\n"
                "     * If WhatsApp chat -> category='99_noise_and_review/screenshots/whatsapp', app_name='WhatsApp'\n"
                "     * If Grindr chat/profile -> category='99_noise_and_review/screenshots/grindr', app_name='Grindr'\n"
                "     * Other personal screenshot -> category='99_noise_and_review/screenshots/personal_other'\n"
                "     * Other business SaaS / software tools -> category='99_noise_and_review/screenshots/business'\n"
                "   - A physical camera photo of handwritten notes or paper is NEVER a screenshot. Use capture_type='camera_photo' or 'scanned_document'.\n\n"
                "Return ONLY the valid JSON object conforming to the schema."
            )

            payload = {
                "model": model_name,
                "messages": [
                    {
                        "role": "user",
                        "content": [
                            {"type": "text", "text": prompt},
                            {"type": "image_url", "image_url": {"url": f"data:image/jpeg;base64,{img_b64}"}}
                        ]
                    }
                ],
                "response_format": {"type": "json_object"},
                "temperature": 0.0,
                "max_tokens": 512
            }

            headers = {
                "Authorization": f"Bearer {api_key}",
                "Content-Type": "application/json",
                "HTTP-Referer": "https://github.com/vincent",
                "X-Title": "Media Workshop Photo Classifier"
            }

            # 4. Request with exponential backoff on 429 rate limit
            max_retries = 5
            backoff = 2.0
            data = None
            cost = 0.0
            tokens = 0

            for attempt in range(max_retries):
                try:
                    response = await client.post(OPENROUTER_URL, headers=headers, json=payload, timeout=90.0)
                    if response.status_code == 200:
                        res_json = response.json()
                        usage = res_json.get("usage", {})
                        cost = float(usage.get("cost", 0.0) or 0.0)
                        tokens = int(usage.get("total_tokens", 0) or 0)
                        raw_content = res_json["choices"][0]["message"]["content"]

                        if "```json" in raw_content:
                            raw_content = raw_content.split("```json")[1].split("```")[0].strip()
                        elif "```" in raw_content:
                            raw_content = raw_content.split("```")[1].split("```")[0].strip()

                        data = json.loads(raw_content)
                        break
                    elif response.status_code == 429:
                        wait_time = backoff + random.uniform(0.5, 2.0)
                        print(f"[{row_id}] OpenRouter 429 Rate Limit. Backing off for {wait_time:.1f}s...")
                        await asyncio.sleep(wait_time)
                        backoff *= 1.5
                    elif response.status_code in [400, 403] and "content" in response.text.lower():
                        # Flagged by content policy / privacy filter upstream
                        print(f"[{row_id}] Content policy block on {img_path.name} -> routed to quarantine.")
                        data = {
                            "capture_type": "camera_photo",
                            "domain": "personal",
                            "category": "06_private_quarantine/intimate",
                            "sensitivity": "intimate",
                            "quality": "ok",
                            "confidence": 0.99,
                            "rationale": "Automated privacy refusal upstream; quarantined locally."
                        }
                        break
                    else:
                        print(f"[{row_id}] OpenRouter HTTP {response.status_code}: {response.text[:150]}")
                        await asyncio.sleep(2.0)
                except (httpx.TimeoutException, httpx.NetworkError) as net_err:
                    if attempt < max_retries - 1:
                        await asyncio.sleep(backoff)
                        backoff *= 1.5
                    else:
                        raise net_err

            if not data:
                raise RuntimeError("Failed to obtain classification after retries.")

            # Validate with Pydantic
            result = ClassificationResult(**data)
            
            # Sync has_vincent flag into tags/model
            if has_vincent:
                result.has_vincent = True
                if "vincent" not in [t.lower() for t in result.tags]:
                    result.tags.append("vincent")

            final_cat = get_final_category(result, year)
            cat = final_cat.value if final_cat else (result.category.value if result.category else "unknown")
            conf = result.confidence
            res_json_str = result.model_dump_json()

            # 5. Persist to SQLite with retry
            if not dry_run:
                for db_attempt in range(5):
                    try:
                        db = get_db()
                        db.execute("""
                            UPDATE inventory 
                            SET qwen_category = ?, qwen_confidence = ?, qwen_json = ?, has_vincent = ?
                            WHERE id = ?
                        """, (cat, conf, res_json_str, 1 if has_vincent else 0, row_id))
                        db.commit()
                        db.close()
                        break
                    except sqlite3.OperationalError:
                        await asyncio.sleep(0.3)

            elapsed_item = time.time() - item_start
            is_sc = (result.capture_type.value == "screenshot")
            is_sh = bool(result.is_shopping)
            await stats.update(True, has_vincent, is_sc, is_sh, cost, tokens)

            v_tag = " [👤 VINCENT]" if has_vincent else ""
            app_tag = f" [📱 {result.app_name}]" if result.app_name else ""
            shop_tag = " [🛒 SHOPPING]" if is_sh else ""
            summary_info = stats.get_summary_str()
            print(f"{summary_info} | {img_path.name} -> {cat}{v_tag}{app_tag}{shop_tag} ({elapsed_item:.1f}s)", flush=True)

        except Exception as err:
            elapsed_item = time.time() - item_start
            await stats.update(False, False, False, False, 0.0, 0)
            print(f"[{row_id}] FAILED on {img_path.name} ({elapsed_item:.1f}s): {err}", flush=True)

        finally:
            queue.task_done()

async def main_async():
    parser = argparse.ArgumentParser(description="Run Qwen 3 VL 32B photo classifier via OpenRouter")
    parser.add_argument("--min-year", type=int, default=2017, help="Minimum year to process (default: 2017)")
    parser.add_argument("--max-year", type=int, default=2026, help="Maximum year to process (default: 2026)")
    parser.add_argument("--limit", type=int, default=None, help="Limit number of photos to process")
    parser.add_argument("--workers", type=int, default=10, help="Number of concurrent async workers (default: 10)")
    parser.add_argument("--model", type=str, default=DEFAULT_MODEL, help=f"OpenRouter model ID (default: {DEFAULT_MODEL})")
    parser.add_argument("--skip-face-detection", action="store_true", help="Skip local face detection for Vincent")
    parser.add_argument("--dry-run", action="store_true", help="Do not write results to SQLite")
    args = parser.parse_args()

    api_key = os.environ.get("OPENROUTER_API_KEY")
    if not api_key:
        print("FATAL: OPENROUTER_API_KEY environment variable is missing.")
        sys.exit(1)

    init_db_schema()

    # Load Face Recognition
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
            print(f"[Face Recognition] Warning: Could not initialize InsightFace ({e}). Proceeding without face detection.")
    else:
        print("[Face Recognition] Skipping face detection.")

    # Query eligible photos
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

    total_photos = len(rows)
    print(f"\n=======================================================")
    print(f"  QWEN 3 VL 32B PHOTO CLASSIFICATION PIPELINE")
    print(f"=======================================================")
    print(f"Target Years:      {args.min_year} - {args.max_year}")
    print(f"Eligible Photos:   {total_photos}")
    print(f"Model:             {args.model} via OpenRouter")
    print(f"Concurrency:       {args.workers} async workers")
    print(f"Face Detection:    {'Enabled (' + str(len(ref_embeddings)) + ' refs)' if ref_embeddings else 'Disabled'}")
    print(f"Database:          {DB_PATH}")
    print(f"=======================================================\n")

    if total_photos == 0:
        print("No eligible unclassified photos found for the specified criteria.")
        return

    schema_json = json.dumps(ClassificationResult.model_json_schema())
    stats = Stats(total_photos)

    queue = asyncio.Queue(maxsize=args.workers * 2)

    # Connection limits for high throughput
    limits = httpx.Limits(max_keepalive_connections=args.workers * 2, max_connections=args.workers * 4)
    async with httpx.AsyncClient(limits=limits, timeout=90.0) as client:
        # Spawn workers
        workers = [
            asyncio.create_task(
                classify_worker(
                    queue=queue,
                    client=client,
                    api_key=api_key,
                    model_name=args.model,
                    face_app=face_app,
                    ref_embeddings=ref_embeddings,
                    stats=stats,
                    schema_json=schema_json,
                    dry_run=args.dry_run
                )
            )
            for _ in range(args.workers)
        ]

        # Feed queue
        for r in rows:
            await queue.put(r)

        # Stop signals
        for _ in range(args.workers):
            await queue.put(None)

        # Wait for all workers to finish
        await asyncio.gather(*workers)

    elapsed_total = time.time() - stats.start_time
    print(f"\n=======================================================")
    print(f"  CLASSIFICATION RUN COMPLETE")
    print(f"=======================================================")
    print(f"Processed:         {stats.processed} / {total_photos}")
    print(f"Successful:        {stats.success}")
    print(f"Failed:            {stats.failed}")
    print(f"Vincent Identified:{stats.vincent_count}")
    print(f"Screenshots:       {stats.screenshots_count} (Shopping: {stats.shopping_count})")
    print(f"Total API Cost:    ${stats.total_cost:.4f}")
    print(f"Total Time:        {elapsed_total / 60:.2f} minutes")
    print(f"=======================================================\n")

def main():
    try:
        asyncio.run(main_async())
    except KeyboardInterrupt:
        print("\n[!] Run interrupted by user. Progress is safely saved in SQLite. You can resume anytime!")

if __name__ == "__main__":
    main()

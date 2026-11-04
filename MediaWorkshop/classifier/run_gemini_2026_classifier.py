#!/usr/bin/env python3
"""
Production Gemini 2.5 Flash Classifier for 2026 Archive.
Runs async batch classification using Google Gemini 2.5 Flash via OpenRouter.
Features:
- Checkpoints progress to state.sqlite (resumable)
- Uses pre-computed InsightFace results for Vincent
- Strict taxonomy rules for Hair Solutions Co, finances, Shopify, and screenshots
- Live throughput, ETA, token, and cost tracking
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
import argparse
from pathlib import Path
from typing import Optional, List, Tuple
from dotenv import load_dotenv
from PIL import Image
from PIL.ExifTags import TAGS
from pillow_heif import register_heif_opener
import httpx

register_heif_opener()

SCRIPT_DIR = Path(__file__).parent
load_dotenv("/Users/vincent/.env")
load_dotenv(SCRIPT_DIR / ".env")

sys.path.append(str(SCRIPT_DIR))
from taxonomy import ClassificationResult, Category, Domain, get_final_category

DB_PATH = SCRIPT_DIR / "state.sqlite"
OPENROUTER_URL = "https://openrouter.ai/api/v1/chat/completions"
DEFAULT_MODEL = "google/gemini-2.5-flash"

SCHEMA_JSON = json.dumps(ClassificationResult.model_json_schema())

BASE_PROMPT = f"""Analyze this image and classify it strictly according to this JSON schema:
{SCHEMA_JSON}

CRITICAL TAXONOMY & CLASSIFICATION RULES:
1. VINCENT (THE LIBRARY OWNER):
   - has_vincent must ONLY be true if Vincent's human FACE is physically visible in the photo.
   - NEVER set has_vincent=true just because the name 'Vincent' or 'Vincent Laroche' is written as text on an invoice, bank statement, WhatsApp message, email, or profile. Text mentions are NOT a human face!

2. FINANCES, BILLS & INVOICES:
   - Any invoice, utility bill (water, electric, gas), receipt, Boleto, Pix transfer receipt, bank transfer, bank statement (e.g. Nubank, Revolut, Mercado Pago, Neon, PicPay), tax form, or payment confirmation:
     MUST be classified as category='finances/bills_invoices' with sensitivity='financial_document'.
   - Do NOT classify bills or invoices as business screenshots or personal portraits.

3. SHOPIFY & STORE BUILDING KNOWLEDGE:
   - Any screenshot, slide, or post discussing Shopify store architecture, ideal product page (PDP) structure, e-commerce conversion rate optimization (CRO), e-commerce navigation, Shopify themes/apps, or how to build an online store:
     MUST be classified as category='business/shopify', domain='business', app_name='Shopify', tags=['shopify', 'ecommerce', ...].

4. USER'S BUSINESS (HAIR SOLUTIONS CO) VS PERSONAL CONSUMER ITEMS:
   - The user's ONLY business is 'Hair Solutions Co' (men's hair replacement systems, toupees, hair pieces, wig lace, base cap construction, hair density swatches, hair factory/supplier chats like OneHead, and client hair before/afters).
     ONLY these hair system items can be classified as business/01_products or business/*!
   - ALL OTHER physical products or consumer goods are strictly PERSONAL:
     * Household appliances (water heaters like Rinnai, air conditioners, furniture) -> personal/home_daily
     * Pharmacy medications, blister packs, pill bottles, ointments, creams (e.g. Fucidine, Cimecort) -> personal/home_daily
     * Clothing, shoe or brand tags (Adidas, Nike, Zara) -> personal/home_daily or personal/people
     * Smartwatch bands, Apple Watch straps, jewelry, personal gadgets -> personal/home_daily
     * Gym, fitness, sports, lifting weights -> personal/sports_hobbies
     * Food, meals, cooking, restaurants, groceries -> personal/food
     Do NOT classify appliances, medicines, or watch straps as business/01_products!

5. SCREENSHOT APPS HIERARCHY:
   - If capture_type is 'screenshot':
     * If financial invoice/bill/bank transfer -> category='finances/bills_invoices'
     * If discussing Shopify architecture/stores -> category='business/shopify'
     * If retail shopping store (Amazon, Mercado Livre, Shopee, Zara, AliExpress) -> category='99_noise_and_review/screenshots/shopping', is_shopping=true
     * If Instagram post/story/reel -> category='99_noise_and_review/screenshots/instagram', app_name='Instagram'
     * If WhatsApp chat -> category='99_noise_and_review/screenshots/whatsapp', app_name='WhatsApp'
     * If Grindr chat/profile -> category='99_noise_and_review/screenshots/grindr', app_name='Grindr'
     * Other personal screenshot -> category='99_noise_and_review/screenshots/personal_other'
     * Other business SaaS / software tools -> category='99_noise_and_review/screenshots/business'
   - A physical camera photo of handwritten notes or paper is NEVER a screenshot. Use capture_type='camera_photo' or 'scanned_document'.

Return ONLY the valid JSON object conforming to the schema."""


def get_db():
    conn = sqlite3.connect(str(DB_PATH), timeout=60.0)
    conn.execute("PRAGMA journal_mode=WAL;")
    conn.execute("PRAGMA busy_timeout=60000;")
    return conn


def is_screenshot_metadata(img: Image.Image, filename: str) -> bool:
    fn_lower = filename.lower()
    if fn_lower.startswith("screenshot") or fn_lower.startswith("screen shot"):
        return True
    w, h = img.size
    aspect = max(w, h) / max(min(w, h), 1)
    if aspect > 2.05 and fn_lower.endswith(".png"):
        return True
    return False


def prepare_image(img_path: Path) -> Tuple[str, bool]:
    with Image.open(img_path) as img:
        is_sc = is_screenshot_metadata(img, img_path.name)
        img.thumbnail((1024, 1024), Image.Resampling.LANCZOS)
        if img.mode != "RGB":
            img = img.convert("RGB")
        buf = io.BytesIO()
        img.save(buf, format="JPEG", quality=85)
        return base64.b64encode(buf.getvalue()).decode("utf-8"), is_sc


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
    stats: Stats,
    dry_run: bool = False
):
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
        "HTTP-Referer": "https://media-workshop.local",
        "X-Title": "Media Workshop 2026 Gemini Classifier"
    }

    while True:
        item = await queue.get()
        if item is None:
            queue.task_done()
            break

        row_id, path_str, year, filename, db_has_vincent = item
        img_path = Path(path_str)

        if not img_path.exists():
            print(f"[{row_id}] File missing on disk: {img_path.name}")
            await stats.update(False, False, False, False, 0.0, 0)
            queue.task_done()
            continue

        item_start = time.time()
        try:
            # 1. Prepare image thumbnail & check screenshot metadata
            loop = asyncio.get_running_loop()
            img_b64, meta_screenshot = await loop.run_in_executor(None, prepare_image, img_path)

            # 2. Build tailored prompt with pre-computed face knowledge
            face_hint = ""
            if db_has_vincent == 1:
                face_hint = (
                    "\nCRITICAL NOTE: Facial recognition has confirmed that Vincent (the library owner) is in this photo. "
                    "When describing the photo, assigning domain, or generating tags, note that Vincent is the main subject/present (e.g. 'Vincent portrait', 'Vincent with friends')."
                )
            else:
                face_hint = "\nNOTE: Facial recognition confirmed Vincent is NOT in this photo. Do not assume or tag Vincent unless a human face matches him."

            screenshot_hint = ""
            if meta_screenshot:
                screenshot_hint = "\nNOTE: File metadata confirms this image is an on-device screenshot."

            prompt = f"{BASE_PROMPT}{face_hint}{screenshot_hint}"

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

            # 3. Call OpenRouter with exponential backoff on 429
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
                        # Upstream privacy / intimate filter
                        print(f"[{row_id}] Content policy block on {img_path.name} -> quarantined.")
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
                        print(f"[{row_id}] OpenRouter status {response.status_code} on {img_path.name}: {response.text[:100]}")
                        wait_time = (attempt + 1) * 3.0
                        await asyncio.sleep(wait_time)
                except Exception as net_err:
                    wait_time = (attempt + 1) * 3.0
                    print(f"[{row_id}] Network error on {img_path.name}: {net_err}, retrying in {wait_time}s...")
                    await asyncio.sleep(wait_time)

            if not data:
                await stats.update(False, False, False, False, 0.0, 0)
                queue.task_done()
                continue

            # 4. Parse with defensive validation fallback
            try:
                result = ClassificationResult(**data)
            except Exception:
                valid_categories = {c.value for c in Category}
                cat_val = data.get("category", "")
                if cat_val not in valid_categories:
                    data["category"] = "personal/other"
                if data.get("sensitivity") not in ["none", "intimate", "identity_document", "financial_document"]:
                    data["sensitivity"] = "none"
                if "quality" not in data or not data["quality"]:
                    data["quality"] = "ok"
                if "confidence" not in data or not isinstance(data["confidence"], (int, float)):
                    data["confidence"] = 0.85
                if "rationale" not in data or not data["rationale"]:
                    data["rationale"] = str(data.get("visual_content", "Classified by Gemini 2.5 Flash"))
                if data.get("domain") not in ["personal", "business", "ambiguous"]:
                    data["domain"] = "personal"
                if "capture_type" not in data:
                    data["capture_type"] = "camera_photo"
                result = ClassificationResult(**data)

            # Ensure Vincent face consistency
            if db_has_vincent == 1:
                result.has_vincent = True
                if "vincent" not in [t.lower() for t in result.tags]:
                    result.tags.append("vincent")
            elif result.has_vincent and db_has_vincent == 0:
                # Disallow false positive face tags on documents
                result.has_vincent = False

            final_cat = get_final_category(result, year)
            cat = final_cat.value if final_cat else (result.category.value if result.category else "unknown")
            conf = float(result.confidence)
            res_json_str = result.model_dump_json()

            # 5. Persist to SQLite with retry
            if not dry_run:
                for db_attempt in range(5):
                    try:
                        db = get_db()
                        db.execute("""
                            UPDATE inventory 
                            SET gemini_category = ?, gemini_confidence = ?, gemini_json = ?
                            WHERE id = ?
                        """, (cat, conf, res_json_str, row_id))
                        db.commit()
                        db.close()
                        break
                    except sqlite3.OperationalError:
                        await asyncio.sleep(0.3)

            elapsed_item = time.time() - item_start
            is_sc = (result.capture_type.value == "screenshot")
            is_sh = bool(result.is_shopping)
            await stats.update(True, result.has_vincent, is_sc, is_sh, cost, tokens)

            v_tag = " [👤 VINCENT]" if result.has_vincent else ""
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


async def main():
    parser = argparse.ArgumentParser(description="Classify 2026 Archive using Gemini 2.5 Flash via OpenRouter")
    parser.add_argument("--limit", type=int, default=None, help="Limit number of photos to process")
    parser.add_argument("--concurrency", type=int, default=6, help="Number of concurrent workers (default: 6)")
    parser.add_argument("--force", action="store_true", help="Re-classify photos that already have gemini_category")
    parser.add_argument("--dry-run", action="store_true", help="Do not save results to SQLite")
    args = parser.parse_args()

    api_key = os.environ.get("OPENROUTER_API_KEY")
    if not api_key:
        print("FATAL: OPENROUTER_API_KEY not found in environment.")
        sys.exit(1)

    conn = get_db()
    c = conn.cursor()

    where_clause = """
        year = 2026
        AND local_only = 0
        AND is_sidecar = 0
        AND is_live_video = 0
        AND LOWER(extension) IN ('.jpg', '.jpeg', '.png', '.heic', '.webp')
    """
    if not args.force:
        where_clause += " AND gemini_category IS NULL"

    query = f"""
        SELECT id, file_path, year, filename, COALESCE(has_vincent, 0)
        FROM inventory
        WHERE {where_clause}
        ORDER BY id ASC
    """
    if args.limit:
        query += f" LIMIT {args.limit}"

    c.execute(query)
    items = c.fetchall()
    conn.close()

    total_items = len(items)
    print(f"\n{'='*75}")
    print(f"GEMINI 2.5 FLASH CLASSIFIER - 2026 ARCHIVE")
    print(f"Target Photos: {total_items} | Concurrency: {args.concurrency} | Model: {DEFAULT_MODEL}")
    print(f"{'='*75}\n")

    if total_items == 0:
        print("All 2026 photos have already been classified by Gemini 2.5 Flash! Use --force to re-run.")
        return

    stats = Stats(total_items)
    queue = asyncio.Queue()

    for item in items:
        await queue.put(item)

    # Start workers
    limits = httpx.Limits(max_keepalive_connections=args.concurrency * 2, max_connections=args.concurrency * 3)
    async with httpx.AsyncClient(limits=limits, timeout=90.0) as client:
        workers = [
            asyncio.create_task(classify_worker(queue, client, api_key, DEFAULT_MODEL, stats, args.dry_run))
            for _ in range(args.concurrency)
        ]

        await queue.join()

        for _ in range(args.concurrency):
            await queue.put(None)
        await asyncio.gather(*workers)

    elapsed = time.time() - stats.start_time
    print(f"\n{'='*75}")
    print(f"CLASSIFICATION COMPLETE in {elapsed/60:.1f} minutes")
    print(f"Total Processed: {stats.processed} | Success: {stats.success} | Failed: {stats.failed}")
    print(f"Vincent Photos: {stats.vincent_count} | Screenshots: {stats.screenshots_count} | Shopping: {stats.shopping_count}")
    print(f"Total Tokens: {stats.total_tokens:,} | Total Cost: ${stats.total_cost:.4f}")
    print(f"{'='*75}\n")


if __name__ == "__main__":
    asyncio.run(main())

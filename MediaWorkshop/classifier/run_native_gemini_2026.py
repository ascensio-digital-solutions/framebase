#!/usr/bin/env python3
"""
Production Vertex AI Gemini 3.8 Flash Classifier for Media Workshop (2025 & 2026 Archives).
Routed through Google Cloud Vertex AI (project: ascensio-media-os / Framebase Media OS)
to utilize the $300 Google Cloud Free Trial credit ($0 out-of-pocket).

Features:
- Vertex AI REST endpoint (aiplatform.googleapis.com) with auto-refreshing ADC OAuth2 token
- Conditional extraction rules (Instagram creator handle, tools/apps discussed, Framebase Phase 6 hair rubric)
- Framebase namespace:value tag generation (app:, tool:, channel:, source:, product:, status:)
- Strict human-subject validation for has_vincent (eliminates 20px avatar false positives on screenshots)
- Resumable SQLite state tracking (inventory table)
- High-throughput asynchronous worker pool
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
from PIL import Image, ImageFile
from pillow_heif import register_heif_opener
import httpx
import google.auth
import google.auth.transport.requests

register_heif_opener()
ImageFile.LOAD_TRUNCATED_IMAGES = True

SCRIPT_DIR = Path(__file__).parent.resolve()
WORKSPACE_DIR = SCRIPT_DIR.parent.parent.resolve()
DB_PATH = SCRIPT_DIR / "state.sqlite"

PROJECT_ID = "ascensio-media-os"
PROJECT_POOL = [
    "ascensio-media-os",
    "valio-life-assistant",
    "gen-lang-client-0275978372",
]
LOCATION = "global"
MODEL_NAME = "gemini-3.8-flash"

def get_vertex_endpoint(project_id: str) -> str:
    return (
        f"https://aiplatform.googleapis.com/v1/projects/{project_id}"
        f"/locations/{LOCATION}/publishers/google/models/{MODEL_NAME}:generateContent"
    )

sys.path.append(str(SCRIPT_DIR))
from taxonomy import ClassificationResult, Category, Domain, get_final_category

SCHEMA_JSON = json.dumps(ClassificationResult.model_json_schema())

BASE_PROMPT = f"""Analyze this image and classify it strictly according to this JSON schema:
{SCHEMA_JSON}

CRITICAL 3-PILLAR TAXONOMY RULES (NOTHING IS AMBIGUOUS):

Every single image belongs strictly to ONE of the THREE PILLARS:
1. `personal`: Personal life, travel, family, friends, selfies, home, daily life, food, fitness, personal shopping, casual chats (WhatsApp, Grindr), personal medical records, personal bills.
2. `business`: Hair Solutions Co. hair replacement systems, swatches, base cap specs, supplier chats (OneHead/Bono Hair), client before/after candidates, Shopify store architecture, e-commerce CRO, and Ascensio startup/admin contracts.
3. `knowledge`: The Creative & Tech Swipe File. ANY social media post, carousel slide, reel, or screenshot discussing AI tools (Claude, Cursor, n8n), prompt engineering, graphic design (Pantone palettes, typography), UI/UX web design, marketing hooks/copy, or developer advice.
NEVER classify an image as ambiguous! Every image has a clear home in Personal, Business, or Knowledge.

SPECIFIC FIELD RULES:

1. VINCENT (THE LIBRARY OWNER) — STRICT HUMAN SUBJECT RULE:
   - has_vincent MUST ONLY be true if this image is a photograph/portrait/selfie/group shot where Vincent's real human face/person is a genuine subject of the scene.
   - NEVER set has_vincent=true on text slides, infographics, carousels, or app screenshots just because a tiny 20px profile avatar appears in the bottom-right Instagram navigation bar or top stories tray!
   - NEVER set has_vincent=true just because the name 'Vincent' or 'Vincent Laroche' is written in text on an invoice, message, or document.

2. CONDITIONAL EXTRACTION FOR KNOWLEDGE SWIPE FILE & SCREENSHOTS (Instagram, X, TikTok, LinkedIn, YouTube, Web):
   - Whenever you identify a slide, carousel, or screenshot discussing tools, design, marketing, or code:
     * Set `domain='knowledge'`.
     * Set `app_name` to the platform (e.g. "Instagram", "WhatsApp", "Shopify", "Claude").
     * Set `creator_handle` to the visible creator @handle, account name, or header title (e.g. "@startupindiastories", "@alenn.design", "@sifuyik") if visible on screen.
     * Set `subject_or_tool_discussed` to the specific app, AI model, tool, or core topic being discussed in the post (e.g. "Claude + Metricool Instagram scheduling", "Startup developer hiring advice", "Pantone color palette").
     * In `rationale`, explicitly mention the creator (if visible) and the specific app/tool/topic discussed.
     * In `tags`, include Framebase lowercase namespace:value tags such as `app:instagram`, `channel:instagram`, `tool:claude`, `tool:metricool`, `topic:ai-automation`, etc.

3. CONDITIONAL EXTRACTION FOR HAIR SOLUTIONS CO. BUSINESS PHOTOS:
   - The user's ONLY business is 'Hair Solutions Co' (men's non-surgical hair replacement systems, toupees, lace/skin/mono bases, hair swatches, factory/supplier chats like OneHead, and client hair before/after photos).
   - ONLY these hair system assets belong in `domain='business'` (`business/01_products`, `business/02_specs`, `business/03_people`, etc.) — EXCEPT Shopify/e-commerce educational screenshots (`business/shopify`) and business administration (`business/operations`).
   - Whenever an image shows a hair system, hairline, scalp, swatch, or model/client:
     * Populate `hairline_presentation`: 'clearlyVisible', 'partiallyVisible', 'notVisible', or 'unclear'.
     * Populate `business_quality`: 'strong', 'usable', 'weak', or 'needsReview'.
     * Populate `photo_role`: 'beforeCandidate', 'afterCandidate', 'comparisonCandidate', 'other', or 'unclear'.
     * Include Framebase tags: e.g. `product:hair-system`, `source:vendor` or `source:customer` or `source:studio`, `status:review`.

4. PERSONAL LIFE VS BUSINESS & KNOWLEDGE:
   - Real-world consumer goods, travel, and personal documents belong strictly in `domain='personal'`:
     * Beaches, oceans, cityscapes, flights, hotels -> `personal/travel`
     * Friends, selfies, group dinners -> `personal/people`
     * Household appliances, furniture, gym, sports -> `personal/home_daily` or `personal/sports_hobbies`
     * Pharmacy medications, blister packs, doctor referrals -> `personal/health_medical`
     * Utility bills, receipts, Pix slips -> `personal/bills_receipts`
     * WhatsApp personal chats, dating apps -> `personal/screenshots/whatsapp` or `personal/screenshots/grindr`
     * Intimate photos -> `06_private_quarantine/intimate`
     * Brazilian IDs/passports -> `06_private_quarantine/identity_documents`

Return ONLY the valid JSON object conforming to the schema."""


class VertexTokenManager:
    """Manages and auto-refreshes Google Cloud ADC OAuth2 tokens for long-running batch jobs."""
    def __init__(self):
        self.creds, self.project = google.auth.default(
            scopes=["https://www.googleapis.com/auth/cloud-platform"]
        )
        self.last_refresh = 0.0
        self.lock = asyncio.Lock()

    async def get_headers(self, project_id: str = PROJECT_ID) -> dict:
        async with self.lock:
            now = time.time()
            # Refresh token every 25 minutes (tokens last 60 mins)
            if not self.creds.token or (now - self.last_refresh) > 1500:
                loop = asyncio.get_running_loop()
                await loop.run_in_executor(
                    None, self.creds.refresh, google.auth.transport.requests.Request()
                )
                self.last_refresh = time.time()
            return {
                "Authorization": f"Bearer {self.creds.token}",
                "Content-Type": "application/json",
                "x-goog-user-project": project_id,
            }


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


def prepare_image(img_path: Path) -> Tuple[Optional[str], bool]:
    try:
        with Image.open(img_path) as img:
            is_sc = is_screenshot_metadata(img, img_path.name)
            img.thumbnail((1024, 1024), Image.Resampling.LANCZOS)
            if img.mode != "RGB":
                img = img.convert("RGB")
            buf = io.BytesIO()
            img.save(buf, format="JPEG", quality=85)
            return base64.b64encode(buf.getvalue()).decode("utf-8"), is_sc
    except Exception as e:
        print(f"Warning: Corrupt or unreadable image {img_path.name}: {e}")
        return None, False


def resolve_image_path(path_str: str, year: int, filename: str) -> Optional[Path]:
    """Resolve image path strictly for the specific year to prevent cross-year filename collisions."""
    local_year_path = WORKSPACE_DIR / str(year) / filename
    if local_year_path.exists():
        return local_year_path

    orig = Path(path_str)
    if orig.exists():
        return orig

    candidates = [
        Path(f"/Volumes/SeaDisk/media_workshop/iPhoto export 2010-2026/{year}") / filename,
        Path(f"/Volumes/SeaDisk/{year}") / filename,
        Path(f"/Volumes/SeaDisk/Apple_Photos_9Y/{year}") / filename,
    ]
    for cand in candidates:
        if cand.exists():
            return cand
    return None


class Stats:
    def __init__(self, total: int):
        self.total = total
        self.processed = 0
        self.success = 0
        self.failed = 0
        self.vincent_count = 0
        self.screenshots_count = 0
        self.shopping_count = 0
        self.business_count = 0
        self.finance_count = 0
        self.total_cost = 0.0
        self.total_input_tokens = 0
        self.total_output_tokens = 0
        self.start_time = time.time()
        self.lock = asyncio.Lock()
        self.classified_rows = []

    async def update(
        self,
        success: bool,
        has_vincent: bool,
        is_screenshot: bool,
        is_shopping: bool,
        is_biz: bool,
        is_fin: bool,
        cost: float,
        in_tokens: int,
        out_tokens: int,
        row_data: dict = None,
    ):
        async with self.lock:
            self.processed += 1
            if success:
                self.success += 1
                if row_data:
                    self.classified_rows.append(row_data)
            else:
                self.failed += 1
            if has_vincent:
                self.vincent_count += 1
            if is_screenshot:
                self.screenshots_count += 1
            if is_shopping:
                self.shopping_count += 1
            if is_biz:
                self.business_count += 1
            if is_fin:
                self.finance_count += 1
            self.total_cost += cost
            self.total_input_tokens += in_tokens
            self.total_output_tokens += out_tokens

    def get_summary_str(self) -> str:
        elapsed = time.time() - self.start_time
        speed = self.processed / elapsed if elapsed > 0 else 0
        remaining = self.total - self.processed
        eta_s = remaining / speed if speed > 0 else 0
        eta_min = eta_s / 60
        return (
            f"[{self.processed}/{self.total}] ({speed:.1f} img/s | ETA: {eta_min:.1f}m) | "
            f"OK: {self.success} | 👤 Vin: {self.vincent_count} | 💼 Biz: {self.business_count} | "
            f"💰 Fin: {self.finance_count} | 📱 Shot: {self.screenshots_count} | GCP Credit Used: ${self.total_cost:.4f}"
        )


async def classify_worker(
    queue: asyncio.Queue,
    client: httpx.AsyncClient,
    token_mgr: VertexTokenManager,
    stats: Stats,
    dry_run: bool = False,
):
    while True:
        item = await queue.get()
        if item is None:
            queue.task_done()
            break

        row_id, path_str, year, filename, db_has_vincent = item
        img_path = resolve_image_path(path_str, year, filename)

        if not img_path:
            print(f"[{row_id}] File missing on local disk & SeaDisk: {filename}")
            await stats.update(False, False, False, False, False, False, 0.0, 0, 0)
            queue.task_done()
            continue

        item_start = time.time()
        try:
            loop = asyncio.get_running_loop()
            img_b64, meta_screenshot = await loop.run_in_executor(None, prepare_image, img_path)

            if not img_b64:
                print(f"[{row_id}] Skipping unreadable or corrupt image {img_path.name}")
                await stats.update(False, False, False, False, False, False, 0.0, 0, 0)
                continue

            # Nuanced face hint that prevents false positives on screenshots
            if db_has_vincent == 1:
                face_hint = (
                    "\nNOTE: A prior face-detector matched Vincent in this file, BUT it often false-triggers on tiny 20px "
                    "profile icons in Instagram/app corners. Set has_vincent=true ONLY if this is an actual photo/portrait "
                    "where Vincent is a real human subject. If this is an app/text screenshot where his face is only a tiny "
                    "navigation/story icon, you MUST set has_vincent=false!"
                )
            else:
                face_hint = (
                    "\nNOTE: Local facial recognition did not detect Vincent's primary face. Set has_vincent=false "
                    "unless he is clearly the primary human subject."
                )

            screenshot_hint = (
                "\nNOTE: File dimensions/metadata indicate this image is an on-device screenshot."
                if meta_screenshot
                else ""
            )
            prompt = f"{BASE_PROMPT}{face_hint}{screenshot_hint}"

            payload = {
                "contents": [
                    {
                        "role": "user",
                        "parts": [
                            {"text": prompt},
                            {"inlineData": {"mimeType": "image/jpeg", "data": img_b64}},
                        ],
                    }
                ],
                "generationConfig": {
                    "responseMimeType": "application/json",
                    "temperature": 0.0,
                    "maxOutputTokens": 1024,
                    "thinkingConfig": {"thinkingBudget": 0},
                },
            }

            max_retries = 7
            backoff = 2.5
            data = None
            cost = 0.0
            in_tokens = 0
            out_tokens = 0

            await asyncio.sleep(random.uniform(0.1, 0.4))

            for attempt in range(max_retries):
                target_project = PROJECT_POOL[(row_id + attempt) % len(PROJECT_POOL)]
                endpoint_url = get_vertex_endpoint(target_project)
                try:
                    headers = await token_mgr.get_headers(target_project)
                    response = await client.post(
                        endpoint_url,
                        headers=headers,
                        json=payload,
                        timeout=60.0,
                    )

                    if response.status_code == 200:
                        res_json = response.json()
                        usage = res_json.get("usageMetadata", {})
                        in_tokens = int(usage.get("promptTokenCount", 0) or 0)
                        out_tokens = int(usage.get("candidatesTokenCount", 0) or 0)

                        # Vertex AI Gemini Flash pricing ($0.30 / 1M input, $2.50 / 1M output)
                        cost = (in_tokens / 1_000_000 * 0.30) + (out_tokens / 1_000_000 * 2.50)

                        candidates = res_json.get("candidates", [])
                        if not candidates or "content" not in candidates[0]:
                            # Check if blocked by safety/prompt feedback
                            data = {
                                "capture_type": "camera_photo",
                                "domain": "personal",
                                "category": "06_private_quarantine/intimate",
                                "sensitivity": "intimate",
                                "quality": "ok",
                                "confidence": 0.95,
                                "rationale": "Safety filter triggered on Vertex AI; routed to private quarantine.",
                            }
                            break

                        raw_content = candidates[0]["content"]["parts"][0]["text"]
                        if "```json" in raw_content:
                            raw_content = raw_content.split("```json")[1].split("```")[0].strip()
                        elif "```" in raw_content:
                            raw_content = raw_content.split("```")[1].split("```")[0].strip()

                        data = json.loads(raw_content)
                        break

                    elif response.status_code == 429:
                        wait_time = backoff + random.uniform(0.5, 2.0)
                        print(f"[{row_id}] Vertex 429 Quota on {img_path.name}. Sleeping {wait_time:.1f}s...")
                        await asyncio.sleep(wait_time)
                        backoff *= 1.6

                    elif response.status_code == 401:
                        # Force token refresh
                        token_mgr.last_refresh = 0.0
                        await asyncio.sleep(1.0)

                    elif response.status_code == 400 and "block" in response.text.lower():
                        data = {
                            "capture_type": "camera_photo",
                            "domain": "personal",
                            "category": "06_private_quarantine/intimate",
                            "sensitivity": "intimate",
                            "quality": "ok",
                            "confidence": 0.99,
                            "rationale": "Upstream safety trigger; routed to private quarantine.",
                        }
                        break
                    else:
                        print(f"[{row_id}] Vertex HTTP {response.status_code}: {response.text[:140]}")
                        await asyncio.sleep((attempt + 1) * 2.0)

                except Exception as net_err:
                    print(f"[{row_id}] Request error on {img_path.name} (attempt {attempt+1}): {net_err}")
                    await asyncio.sleep((attempt + 1) * 2.0)

            if not data:
                await stats.update(False, False, False, False, False, False, 0.0, 0, 0)
                continue

            # Defensive Pydantic validation
            try:
                result = ClassificationResult(**data)
            except Exception:
                valid_categories = {c.value for c in Category}
                cat_val = data.get("category", "")
                if cat_val not in valid_categories:
                    data["category"] = "personal/other"
                if data.get("sensitivity") not in ["none", "intimate", "identity_document", "financial_document"]:
                    data["sensitivity"] = "none"
                if data.get("quality") not in ["keeper", "ok", "weak", "reject"]:
                    data["quality"] = "ok"
                if "confidence" not in data or not isinstance(data["confidence"], (int, float)):
                    data["confidence"] = 0.85
                if "rationale" not in data or not data["rationale"]:
                    data["rationale"] = "Classified by Vertex AI Gemini 3.8 Flash"
                if data.get("domain") not in ["personal", "business", "ambiguous"]:
                    data["domain"] = "personal"
                if data.get("capture_type") not in [
                    "camera_photo", "screenshot", "screen_recording", "downloaded_image",
                    "meme", "scanned_document", "graphic_design", "ai_generated", "unknown"
                ]:
                    data["capture_type"] = "camera_photo"
                result = ClassificationResult(**data)

            # Respect Gemini's visual verification of whether Vincent is truly a human subject!
            # Only block false positives when db_has_vincent == 0:
            if db_has_vincent == 0 and result.has_vincent:
                result.has_vincent = False

            # If Gemini determined has_vincent is False, ensure 'vincent' isn't in tags
            if not result.has_vincent:
                result.tags = [t for t in result.tags if "vincent" not in t.lower()]
            else:
                if not any("vincent" in t.lower() for t in result.tags):
                    result.tags.append("person:vincent")

            final_cat = get_final_category(result, year)
            cat = final_cat.value if final_cat else (result.category.value if result.category else "unknown")
            conf = float(result.confidence)
            res_json_str = result.model_dump_json()

            if not dry_run:
                for _ in range(5):
                    try:
                        db = get_db()
                        db.execute(
                            """
                            UPDATE inventory 
                            SET gemini_category = ?, gemini_confidence = ?, gemini_json = ?
                            WHERE id = ?
                            """,
                            (cat, conf, res_json_str, row_id),
                        )
                        db.commit()
                        db.close()
                        break
                    except sqlite3.OperationalError:
                        await asyncio.sleep(0.3)

            elapsed_item = time.time() - item_start
            is_sc = result.capture_type.value == "screenshot"
            is_sh = bool(result.is_shopping)
            is_biz = result.domain.value == "business"
            is_fin = "finances" in cat or result.sensitivity.value == "financial_document"

            row_record = {
                "id": row_id,
                "year": year,
                "filename": img_path.name,
                "path": str(img_path),
                "category": cat,
                "domain": result.domain.value,
                "confidence": conf,
                "has_vincent": bool(result.has_vincent),
                "app_name": result.app_name,
                "creator_handle": result.creator_handle,
                "subject_or_tool_discussed": result.subject_or_tool_discussed,
                "hairline_presentation": result.hairline_presentation,
                "business_quality": result.business_quality,
                "is_shopping": is_sh,
                "sensitivity": result.sensitivity.value,
                "tags": result.tags,
                "rationale": result.rationale,
            }

            await stats.update(
                True,
                bool(result.has_vincent),
                is_sc,
                is_sh,
                is_biz,
                is_fin,
                cost,
                in_tokens,
                out_tokens,
                row_record,
            )

            v_tag = " [👤 VINCENT]" if result.has_vincent else ""
            app_tag = f" [📱 {result.app_name}]" if result.app_name else ""
            creator_tag = f" [{result.creator_handle}]" if result.creator_handle else ""
            tool_tag = f" [🔧 {result.subject_or_tool_discussed}]" if result.subject_or_tool_discussed else ""
            biz_tag = " [💼 BUSINESS]" if is_biz else ""
            fin_tag = " [💰 FINANCE]" if is_fin else ""

            if stats.processed % 10 == 0 or stats.processed <= 15 or is_biz or result.has_vincent:
                summary_info = stats.get_summary_str()
                print(
                    f"{summary_info} | {year}/{img_path.name} -> {cat}{v_tag}{biz_tag}{fin_tag}{app_tag}{creator_tag}{tool_tag} ({elapsed_item:.1f}s)",
                    flush=True,
                )

        except Exception as err:
            elapsed_item = time.time() - item_start
            await stats.update(False, False, False, False, False, False, 0.0, 0, 0)
            print(f"[{row_id}] FAILED on {img_path.name} ({elapsed_item:.1f}s): {err}", flush=True)

        finally:
            queue.task_done()


def generate_gallery_from_db(years: List[int], output_html_path: Path, limit: int = 500):
    """Generate a rich visual HTML gallery from SQLite state."""
    conn = get_db()
    c = conn.cursor()
    placeholders = ",".join("?" for _ in years)
    c.execute(
        f"""
        SELECT id, year, filename, file_path, gemini_category, gemini_confidence, gemini_json
        FROM inventory
        WHERE year IN ({placeholders}) AND gemini_json IS NOT NULL
        ORDER BY id DESC
        LIMIT ?
        """,
        (*years, limit),
    )
    rows = c.fetchall()
    conn.close()

    cards_html = []
    for r_id, yr, fn, fpath, cat, conf_val, gjson in rows:
        try:
            d = json.loads(gjson)
        except Exception:
            continue
        img_p = resolve_image_path(fpath, yr, fn) or Path(fpath)
        conf = int((conf_val or 0.85) * 100)
        domain = d.get("domain", "personal")
        rationale = d.get("rationale", "")
        tags = d.get("tags", [])
        creator = d.get("creator_handle")
        tool_discussed = d.get("subject_or_tool_discussed")
        hairline = d.get("hairline_presentation")

        if domain == "business":
            domain_color = "bg-blue-600/30 text-blue-300 border-blue-500/40"
            pillar_badge = '<span class="px-2 py-0.5 text-xs font-semibold rounded bg-blue-600/40 text-blue-200 border border-blue-500/50">💼 Business</span>'
        elif domain == "knowledge":
            domain_color = "bg-amber-500/25 text-amber-300 border-amber-400/40"
            pillar_badge = '<span class="px-2 py-0.5 text-xs font-semibold rounded bg-amber-500/35 text-amber-200 border border-amber-400/50">💡 Knowledge</span>'
        else:
            domain_color = "bg-slate-700 text-slate-300 border-slate-600"
            pillar_badge = '<span class="px-2 py-0.5 text-xs font-semibold rounded bg-slate-800 text-slate-300 border border-slate-700">🏖️ Personal</span>'

        if "quarantine" in str(cat):
            domain_color = "bg-rose-600/30 text-rose-300 border-rose-500/40"
            pillar_badge = '<span class="px-2 py-0.5 text-xs font-semibold rounded bg-rose-600/40 text-rose-200 border border-rose-500/50">🔒 Quarantine</span>'

        vincent_badge = (
            '<span class="px-2 py-0.5 text-xs font-semibold rounded bg-purple-600/40 text-purple-200 border border-purple-500/50">👤 Vincent</span>'
            if d.get("has_vincent")
            else ""
        )
        app_badge = (
            f'<span class="px-2 py-0.5 text-xs rounded bg-sky-600/30 text-sky-200 border border-sky-500/40">📱 {d["app_name"]}</span>'
            if d.get("app_name")
            else ""
        )
        creator_badge = (
            f'<span class="px-2 py-0.5 text-xs rounded bg-pink-600/30 text-pink-200 border border-pink-500/40">✍️ {creator}</span>'
            if creator
            else ""
        )
        tool_badge = (
            f'<span class="px-2 py-0.5 text-xs rounded bg-indigo-600/30 text-indigo-200 border border-indigo-500/40">🔧 {tool_discussed}</span>'
            if tool_discussed
            else ""
        )
        hair_badge = (
            f'<span class="px-2 py-0.5 text-xs rounded bg-teal-600/30 text-teal-200 border border-teal-500/40">💈 Hairline: {hairline}</span>'
            if hairline and hairline != "notVisible"
            else ""
        )

        tags_html = "".join(
            [
                f'<span class="text-[10px] px-1.5 py-0.5 rounded bg-slate-800 text-slate-400 border border-slate-700/60">#{t}</span>'
                for t in tags[:6]
            ]
        )
        file_url = f"file://{img_p.resolve()}"

        card = f"""
        <div class="bg-slate-900 border border-slate-800 rounded-xl overflow-hidden flex flex-col shadow-lg hover:border-slate-700 transition" data-category="{cat}" data-domain="{domain}">
            <div class="relative aspect-square bg-slate-950 flex items-center justify-center overflow-hidden group">
                <img src="{file_url}" alt="{fn}" loading="lazy" class="w-full h-full object-cover group-hover:scale-105 transition duration-300">
                <div class="absolute top-2 left-2 bg-black/70 backdrop-blur-md px-2 py-0.5 rounded text-xs font-mono text-slate-300">
                    {yr}
                </div>
                <div class="absolute top-2 right-2 bg-black/70 backdrop-blur-md px-2 py-0.5 rounded-full text-xs font-mono font-medium text-slate-300">
                    {conf}%
                </div>
            </div>
            <div class="p-3.5 flex-1 flex flex-col justify-between">
                <div>
                    <div class="flex items-center gap-1.5 flex-wrap mb-1.5">
                        {pillar_badge}
                        <span class="px-2 py-0.5 text-xs font-medium rounded border {domain_color}">{cat}</span>
                        {vincent_badge}
                        {app_badge}
                        {creator_badge}
                        {tool_badge}
                        {hair_badge}
                    </div>
                    <p class="font-mono text-xs text-slate-300 truncate font-semibold" title="{fn}">{fn}</p>
                    <p class="text-xs text-slate-400 mt-1 line-clamp-3 leading-relaxed" title="{rationale}">{rationale}</p>
                </div>
                <div class="mt-3 pt-2 border-t border-slate-800/80 flex flex-wrap gap-1">
                    {tags_html}
                </div>
            </div>
        </div>
        """
        cards_html.append(card)

    html_content = f"""<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Framebase Media OS — Vertex AI Gemini 3.8 Flash Gallery</title>
    <script src="https://cdn.tailwindcss.com"></script>
    <style>body {{ background-color: #0b0f19; }}</style>
</head>
<body class="text-slate-100 font-sans p-6 md:p-10 max-w-7xl mx-auto">
    <header class="mb-8 flex flex-col md:flex-row md:items-center justify-between gap-4 border-b border-slate-800 pb-6">
        <div>
            <h1 class="text-3xl font-extrabold tracking-tight bg-gradient-to-r from-blue-400 via-indigo-300 to-emerald-400 bg-clip-text text-transparent">
                Framebase Media OS: Gemini 3.8 Flash (Vertex AI)
            </h1>
            <p class="text-slate-400 text-sm mt-1">Project: {PROJECT_ID} | Archives: {", ".join(map(str, years))}</p>
        </div>
        <div class="flex items-center gap-3">
            <span class="px-3 py-1.5 rounded-lg bg-slate-800/80 border border-slate-700 text-sm font-mono text-slate-200">
                Showing: <strong class="text-white">{len(cards_html)}</strong> photos
            </span>
        </div>
    </header>
    <div class="grid grid-cols-1 sm:grid-cols-2 md:grid-cols-3 lg:grid-cols-4 gap-5">
        {"".join(cards_html)}
    </div>
</body>
</html>"""
    with open(output_html_path, "w", encoding="utf-8") as f:
        f.write(html_content)
    print(f"\n[GALLERY] Visual review report generated at: file://{output_html_path.resolve()}")


async def main():
    parser = argparse.ArgumentParser(description="Classify 2025 & 2026 Archives via Vertex AI Gemini 3.8 Flash")
    parser.add_argument("--years", type=int, nargs="+", default=[2026, 2025], help="Years to process (default: 2026 2025)")
    parser.add_argument("--limit", type=int, default=10000, help="Max photos to process (default: 10000)")
    parser.add_argument("--concurrency", type=int, default=12, help="Concurrent Vertex AI workers (default: 12)")
    parser.add_argument("--force", action="store_true", help="Re-classify photos that already have gemini_category")
    parser.add_argument("--ids", type=int, nargs="*", help="Specific inventory IDs to classify")
    parser.add_argument("--dry-run", action="store_true", help="Do not write results to SQLite")
    args = parser.parse_args()

    token_mgr = VertexTokenManager()
    # Pre-flight token check
    await token_mgr.get_headers()

    conn = get_db()
    c = conn.cursor()

    if args.ids:
        id_placeholders = ",".join("?" for _ in args.ids)
        query = f"""
            SELECT id, file_path, year, filename, COALESCE(has_vincent, 0)
            FROM inventory
            WHERE id IN ({id_placeholders})
            ORDER BY id ASC
        """
        c.execute(query, tuple(args.ids))
    else:
        yr_placeholders = ",".join("?" for _ in args.years)
        where_clause = f"""
            year IN ({yr_placeholders})
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
            ORDER BY year DESC, id ASC
            LIMIT ?
        """
        c.execute(query, (*args.years, args.limit))

    items = c.fetchall()
    conn.close()

    total_items = len(items)
    print(f"\n{'='*85}")
    print(f"FRAMEBASE MEDIA OS — VERTEX AI GEMINI 3.8 FLASH CLASSIFIER")
    print(f"GCP Project: {PROJECT_ID} (Billing: $300 GCP Trial Credit)")
    print(f"Target Years: {args.years} | Target Photos: {total_items} | Concurrency: {args.concurrency}")
    print(f"{'='*85}\n", flush=True)

    if total_items == 0:
        print("No unclassified photos found matching query.")
        return

    stats = Stats(total_items)
    queue = asyncio.Queue()

    for item in items:
        await queue.put(item)

    limits = httpx.Limits(max_keepalive_connections=args.concurrency * 2, max_connections=args.concurrency * 3)
    async with httpx.AsyncClient(limits=limits, timeout=60.0) as client:
        workers = [
            asyncio.create_task(classify_worker(queue, client, token_mgr, stats, args.dry_run))
            for _ in range(args.concurrency)
        ]

        await queue.join()

        for _ in range(args.concurrency):
            await queue.put(None)
        await asyncio.gather(*workers)

    elapsed = time.time() - stats.start_time
    print(f"\n{'='*85}")
    print(f"VERTEX AI BATCH COMPLETE in {elapsed/60:.2f} minutes ({elapsed:.1f}s)")
    print(f"Total Processed: {stats.processed} | Success: {stats.success} | Failed: {stats.failed}")
    print(f"👤 Vincent Faces: {stats.vincent_count} | 💼 Business: {stats.business_count} | 💰 Finances: {stats.finance_count}")
    print(f"📱 Screenshots: {stats.screenshots_count} | 🛒 Shopping Items: {stats.shopping_count}")
    print(f"Tokens: {stats.total_input_tokens + stats.total_output_tokens:,} (Input: {stats.total_input_tokens:,}, Output: {stats.total_output_tokens:,})")
    print(f"Total GCP Credit Used: ${stats.total_cost:.4f} USD ($0.00 out-of-pocket)")
    print(f"{'='*85}\n", flush=True)

    # Update galleries
    generate_gallery_from_db([2026], SCRIPT_DIR / "pilot_100_gallery.html", limit=200)
    if 2026 in args.years:
        generate_gallery_from_db([2026], SCRIPT_DIR / "gallery_2026.html", limit=4000)
    if 2025 in args.years:
        generate_gallery_from_db([2025], SCRIPT_DIR / "gallery_2025.html", limit=5500)


if __name__ == "__main__":
    asyncio.run(main())

#!/usr/bin/env python3
"""
Run Gemini 2.5 Flash on 100 random photos that have already been classified by Qwen 3 VL 32B.
Stores results in SQLite and generates an interactive side-by-side comparison HTML report.
"""

import asyncio
import os
import sys
import json
import sqlite3
import time
import base64
import io
from pathlib import Path
from typing import Optional, List, Dict, Any
import httpx
from PIL import Image
from pillow_heif import register_heif_opener
from dotenv import load_dotenv

register_heif_opener()

SCRIPT_DIR = Path(__file__).parent
load_dotenv("/Users/vincent/.env")
load_dotenv(SCRIPT_DIR / ".env")

OPENROUTER_API_KEY = os.environ.get("OPENROUTER_API_KEY")
GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY")

if not OPENROUTER_API_KEY and not GEMINI_API_KEY:
    print("FATAL: Neither OPENROUTER_API_KEY nor GEMINI_API_KEY found.")
    sys.exit(1)

sys.path.append(str(SCRIPT_DIR))
from taxonomy import ClassificationResult, Category, get_final_category

DB_PATH = SCRIPT_DIR / "state.sqlite"
REPORT_HTML = SCRIPT_DIR / "gemini_qwen_comparison.html"
THUMB_CACHE_DIR = SCRIPT_DIR / ".thumb_cache"
THUMB_CACHE_DIR.mkdir(exist_ok=True)

SCHEMA_JSON = json.dumps(ClassificationResult.model_json_schema())

PROMPT_TEXT = f"""Analyze this image and classify it strictly according to this JSON schema:
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

def prepare_image_bytes(path: Path) -> bytes:
    with Image.open(path) as img:
        img.thumbnail((1536, 1536), Image.Resampling.LANCZOS)
        if img.mode != "RGB":
            img = img.convert("RGB")
        buf = io.BytesIO()
        img.save(buf, format="JPEG", quality=85)
        return buf.getvalue()

def get_thumbnail_b64(path: Path, row_id: int) -> str:
    cache_file = THUMB_CACHE_DIR / f"{row_id}.jpg"
    if cache_file.exists():
        try:
            return base64.b64encode(cache_file.read_bytes()).decode("utf-8")
        except Exception:
            pass
    if path.exists():
        try:
            with Image.open(path) as img:
                img.thumbnail((360, 360), Image.Resampling.LANCZOS)
                if img.mode != "RGB":
                    img = img.convert("RGB")
                buf = io.BytesIO()
                img.save(buf, format="JPEG", quality=80)
                b = buf.getvalue()
                cache_file.write_bytes(b)
                return base64.b64encode(b).decode("utf-8")
        except Exception:
            pass
    return ""

async def classify_single(client: httpx.AsyncClient, item: tuple, sem: asyncio.Semaphore) -> Optional[Dict[str, Any]]:
    row_id, file_path_str, filename, year, q_cat, q_conf, q_json_str = item
    img_path = Path(file_path_str)
    if not img_path.exists():
        print(f"[{row_id}] File missing on disk: {filename}")
        return None

    async with sem:
        loop = asyncio.get_running_loop()
        try:
            img_bytes = await loop.run_in_executor(None, prepare_image_bytes, img_path)
            b64 = base64.b64encode(img_bytes).decode("utf-8")
        except Exception as e:
            print(f"[{row_id}] Failed to load image {filename}: {e}")
            return None

        payload = {
            "model": "google/gemini-2.5-flash",
            "messages": [
                {
                    "role": "user",
                    "content": [
                        {"type": "text", "text": PROMPT_TEXT},
                        {"type": "image_url", "image_url": {"url": f"data:image/jpeg;base64,{b64}"}}
                    ]
                }
            ],
            "response_format": {"type": "json_object"},
            "temperature": 0.0
        }

        headers = {
            "Authorization": f"Bearer {OPENROUTER_API_KEY}",
            "Content-Type": "application/json",
            "HTTP-Referer": "https://media-workshop.local",
            "X-Title": "Media Workshop Classifier"
        }

        # Call Gemini 2.5 Flash via OpenRouter
        max_retries = 3
        result = None
        elapsed = 0.0
        for attempt in range(max_retries):
            t0 = time.time()
            try:
                resp = await client.post(
                    "https://openrouter.ai/api/v1/chat/completions",
                    headers=headers,
                    json=payload,
                    timeout=90.0
                )
                elapsed = time.time() - t0
                if resp.status_code == 200:
                    data = resp.json()
                    content = data["choices"][0]["message"]["content"]
                    parsed = json.loads(content)
                    
                    try:
                        result = ClassificationResult(**parsed)
                    except Exception as ve:
                        # Graceful fallback: sanitize required fields
                        valid_categories = {c.value for c in Category}
                        cat_val = parsed.get("category", "")
                        if cat_val not in valid_categories:
                            parsed["category"] = "personal/other"
                        if parsed.get("sensitivity") not in ["none", "intimate", "identity_document", "financial_document"]:
                            parsed["sensitivity"] = "none"
                        if "quality" not in parsed or not parsed["quality"]:
                            parsed["quality"] = "ok"
                        if "confidence" not in parsed or not isinstance(parsed["confidence"], (int, float)):
                            parsed["confidence"] = 0.85
                        if "rationale" not in parsed or not parsed["rationale"]:
                            parsed["rationale"] = str(parsed.get("visual_content", "Classified by Gemini 2.5 Flash"))
                        if parsed.get("domain") not in ["personal", "business", "ambiguous"]:
                            parsed["domain"] = "personal"
                        if "capture_type" not in parsed:
                            parsed["capture_type"] = "camera_photo"
                        result = ClassificationResult(**parsed)
                    break
                elif resp.status_code in (429, 502, 503, 504):
                    wait_time = (attempt + 1) * 3.0
                    print(f"[{row_id}] OpenRouter status {resp.status_code} on {filename}, retrying in {wait_time}s...")
                    await asyncio.sleep(wait_time)
                else:
                    print(f"[{row_id}] OpenRouter error {resp.status_code} on {filename}: {resp.text[:120]}")
                    break
            except Exception as e:
                elapsed = time.time() - t0
                wait_time = (attempt + 1) * 3.0
                print(f"[{row_id}] Network error on {filename}: {e}, retrying in {wait_time}s...")
                await asyncio.sleep(wait_time)

        if not result:
            return None

        final_cat = get_final_category(result, year)
        cat_str = final_cat.value if final_cat else (result.category.value if result.category else "unknown")
        conf = float(result.confidence)
        res_json = result.model_dump_json()

        # Update SQLite
        db = get_db()
        db.execute("""
            UPDATE inventory 
            SET gemini_category = ?, gemini_confidence = ?, gemini_json = ?
            WHERE id = ?
        """, (cat_str, conf, res_json, row_id))
        db.commit()
        db.close()

        print(f"✅ [{row_id}] {filename} ({elapsed:.1f}s) -> Gemini: {cat_str} (Qwen: {q_cat})")

        return {
            "id": row_id,
            "filename": filename,
            "file_path": file_path_str,
            "year": year,
            "thumb": get_thumbnail_b64(img_path, row_id),
            "gemini": {
                "category": cat_str,
                "confidence": round(conf * 100),
                "domain": result.domain.value,
                "app_name": result.app_name,
                "has_vincent": result.has_vincent,
                "rationale": result.rationale,
                "tags": result.tags,
                "raw": result.model_dump()
            },
            "qwen": {
                "category": q_cat,
                "confidence": round((q_conf or 0) * 100),
                "raw": json.loads(q_json_str) if q_json_str else {}
            }
        }

HTML_TEMPLATE = r"""<!DOCTYPE html>
<html lang="en" class="dark">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Model Comparison: Gemini 2.5 Flash vs Qwen 3 VL 32B (100 Photos)</title>
    <script src="https://cdn.tailwindcss.com"></script>
    <script>
        tailwind.config = {
            darkMode: 'class',
            theme: {
                extend: {
                    colors: {
                        dark: { 950: '#07090e', 900: '#0b0f19', 800: '#111827', 700: '#1f293d' },
                        gemini: { 500: '#38bdf8', 600: '#0284c7' },
                        qwen: { 500: '#a855f7', 600: '#9333ea' }
                    }
                }
            }
        }
    </script>
    <style>
        body { background-color: #07090e; color: #f1f5f9; }
        .glass-panel { background: rgba(17, 24, 39, 0.75); backdrop-filter: blur(16px); border: 1px solid rgba(255, 255, 255, 0.08); }
        .glass-card { background: rgba(22, 31, 54, 0.6); backdrop-filter: blur(10px); border: 1px solid rgba(255, 255, 255, 0.06); }
    </style>
</head>
<body class="min-h-screen flex flex-col font-sans">

    <!-- Top Header -->
    <header class="sticky top-0 z-30 glass-panel border-b border-white/5 py-4 px-6 md:px-10">
        <div class="max-w-7xl mx-auto flex flex-col md:flex-row md:items-center justify-between gap-4">
            <div>
                <div class="flex items-center gap-3">
                    <h1 class="text-xl font-bold tracking-tight text-white">Gemini 2.5 Flash vs Qwen 3 VL 32B</h1>
                    <span class="text-xs px-2.5 py-0.5 rounded-full bg-emerald-500/20 text-emerald-300 font-mono font-medium border border-emerald-500/30">100 Photo Benchmark</span>
                </div>
                <p class="text-xs text-slate-400 mt-0.5">Head-to-head classification & rationale analysis</p>
            </div>

            <!-- Stats Bar -->
            <div class="flex items-center gap-2 text-xs">
                <div class="px-3 py-1.5 rounded-lg bg-dark-800 border border-white/5 flex items-center gap-1.5">
                    <span class="text-slate-400">Total:</span>
                    <span class="font-bold text-white font-mono">__TOTAL__</span>
                </div>
                <div class="px-3 py-1.5 rounded-lg bg-dark-800 border border-emerald-500/20 flex items-center gap-1.5">
                    <span>✅ Agreement:</span>
                    <span class="font-bold text-emerald-300 font-mono">__AGREEMENTS__ (__AGREEMENT_PCT__%)</span>
                </div>
                <div class="px-3 py-1.5 rounded-lg bg-dark-800 border border-amber-500/20 flex items-center gap-1.5">
                    <span>⚡ Differences:</span>
                    <span class="font-bold text-amber-300 font-mono">__DISAGREEMENTS__</span>
                </div>
            </div>
        </div>
    </header>

    <main class="flex-1 max-w-7xl w-full mx-auto px-6 md:px-10 py-8">

        <!-- Controls -->
        <section class="glass-panel rounded-2xl p-4 mb-8 flex flex-col sm:flex-row items-center justify-between gap-4">
            <div class="flex flex-wrap items-center gap-2">
                <span class="text-xs text-slate-400 font-semibold mr-2">Filter View:</span>
                <button onclick="filterCards('all')" id="pill-all" class="px-3 py-1.5 rounded-lg text-xs font-semibold bg-sky-600 text-white shadow-sm">All (__TOTAL__)</button>
                <button onclick="filterCards('diff')" id="pill-diff" class="px-3 py-1.5 rounded-lg text-xs font-medium bg-dark-800 text-slate-300 hover:text-white border border-amber-500/30">⚡ Differences Only (__DISAGREEMENTS__)</button>
                <button onclick="filterCards('same')" id="pill-same" class="px-3 py-1.5 rounded-lg text-xs font-medium bg-dark-800 text-slate-300 hover:text-white border border-emerald-500/30">✅ Matching Only (__AGREEMENTS__)</button>
                <button onclick="filterCards('finance')" id="pill-finance" class="px-3 py-1.5 rounded-lg text-xs font-medium bg-dark-800 text-slate-300 hover:text-white border border-yellow-500/30">💳 Finances / Invoices</button>
                <button onclick="filterCards('shopify')" id="pill-shopify" class="px-3 py-1.5 rounded-lg text-xs font-medium bg-dark-800 text-slate-300 hover:text-white border border-teal-500/30">🛍️ Shopify</button>
            </div>

            <div class="w-full sm:w-64">
                <input type="text" id="search-input" oninput="applyFilters()" placeholder="Search filename, tag, rationale..." class="w-full px-3 py-2 rounded-xl bg-dark-950/80 border border-white/10 text-xs text-slate-200 placeholder-slate-500 focus:outline-none focus:border-sky-500">
            </div>
        </section>

        <!-- Grid of Comparison Cards -->
        <div id="cards-container" class="space-y-6"></div>

    </main>

    <script>
        const ALL_DATA = __CARDS_JSON__;
        let currentFilter = 'all';

        function escapeHtml(text) {
            if (!text) return '';
            return text.toString()
                .replace(/&/g, "&amp;")
                .replace(/</g, "&lt;")
                .replace(/>/g, "&gt;")
                .replace(/"/g, "&quot;")
                .replace(/'/g, "&#039;");
        }

        function filterCards(type) {
            currentFilter = type;
            document.querySelectorAll('button[id^="pill-"]').forEach(btn => {
                btn.className = 'px-3 py-1.5 rounded-lg text-xs font-medium bg-dark-800 text-slate-300 hover:text-white border border-white/10';
            });
            const active = document.getElementById('pill-' + type);
            if (active) active.className = 'px-3 py-1.5 rounded-lg text-xs font-semibold bg-sky-600 text-white shadow-sm';
            applyFilters();
        }

        function applyFilters() {
            const search = document.getElementById('search-input').value.toLowerCase().trim();
            const container = document.getElementById('cards-container');
            container.innerHTML = '';

            const filtered = ALL_DATA.filter(item => {
                const gCat = item.gemini.category || '';
                const qCat = item.qwen.category || '';
                const isMatch = (gCat === qCat);

                if (currentFilter === 'diff' && isMatch) return false;
                if (currentFilter === 'same' && !isMatch) return false;
                if (currentFilter === 'finance' && !gCat.includes('finance') && !qCat.includes('finance')) return false;
                if (currentFilter === 'shopify' && !gCat.includes('shopify') && !qCat.includes('shopify') && !JSON.stringify(item).toLowerCase().includes('shopify')) return false;

                if (search) {
                    const text = JSON.stringify(item).toLowerCase();
                    if (!text.includes(search)) return false;
                }
                return true;
            });

            if (filtered.length === 0) {
                container.innerHTML = '<div class="text-center py-16 text-slate-500">No photos match the selected filter.</div>';
                return;
            }

            filtered.forEach(item => {
                const isMatch = (item.gemini.category === item.qwen.category);
                const qRaw = item.qwen.raw || {};
                const card = document.createElement('div');
                card.className = 'glass-card rounded-2xl p-5 border border-white/5 flex flex-col lg:flex-row gap-6 shadow-xl';

                card.innerHTML = `
                    <!-- Thumbnail & Info -->
                    <div class="w-full lg:w-48 flex-shrink-0 flex flex-col items-center">
                        <div class="w-48 h-48 rounded-xl overflow-hidden bg-dark-950 flex items-center justify-center border border-white/10 shadow-md">
                            ${item.thumb ? `<img src="data:image/jpeg;base64,${item.thumb}" class="w-full h-full object-cover">` : '<div class="text-xs text-slate-600">No preview</div>'}
                        </div>
                        <div class="mt-2 text-center">
                            <span class="text-xs font-semibold text-slate-300 truncate max-w-[190px] block" title="${escapeHtml(item.filename)}">${escapeHtml(item.filename)}</span>
                            <span class="text-[10px] text-slate-500 font-mono">Year: ${item.year} • ID: #${item.id}</span>
                            <div class="mt-1">
                                <span class="px-2 py-0.5 rounded-full text-[10px] font-bold ${isMatch ? 'bg-emerald-500/20 text-emerald-300 border border-emerald-500/30' : 'bg-amber-500/20 text-amber-300 border border-amber-500/30'}">
                                    ${isMatch ? '✅ MATCH' : '⚡ DIFFERENCE'}
                                </span>
                            </div>
                        </div>
                    </div>

                    <!-- Side by Side Models -->
                    <div class="flex-1 grid grid-cols-1 md:grid-cols-2 gap-4">
                        
                        <!-- Gemini 2.5 Flash Column -->
                        <div class="p-4 rounded-xl bg-dark-900/90 border border-sky-500/30 flex flex-col justify-between">
                            <div>
                                <div class="flex items-center justify-between pb-2 border-b border-white/5">
                                    <span class="text-xs font-bold text-sky-400 flex items-center gap-1.5">
                                        <span>✨</span> Gemini 2.5 Flash
                                    </span>
                                    <span class="text-[11px] font-mono text-slate-400">${item.gemini.confidence}% conf</span>
                                </div>
                                <div class="mt-3">
                                    <span class="text-xs font-bold text-white font-mono break-all">${escapeHtml(item.gemini.category)}</span>
                                    <div class="flex flex-wrap gap-1 mt-1 text-[10px]">
                                        <span class="px-1.5 py-0.5 rounded bg-sky-500/20 text-sky-300">Domain: ${escapeHtml(item.gemini.domain)}</span>
                                        ${item.gemini.app_name ? `<span class="px-1.5 py-0.5 rounded bg-emerald-500/20 text-emerald-300">App: ${escapeHtml(item.gemini.app_name)}</span>` : ''}
                                        ${item.gemini.has_vincent ? '<span class="px-1.5 py-0.5 rounded bg-purple-500/20 text-purple-300 font-bold">👤 Vincent Face</span>' : ''}
                                    </div>
                                </div>
                                <p class="text-xs text-slate-300 italic mt-3 bg-dark-950/60 p-2.5 rounded-lg border border-white/5 leading-relaxed">
                                    "${escapeHtml(item.gemini.rationale || 'No rationale')}."
                                </p>
                            </div>
                            <div class="flex flex-wrap gap-1 mt-3 pt-2 border-t border-white/5">
                                ${(item.gemini.tags || []).slice(0, 5).map(t => `<span class="px-1.5 py-0.5 rounded bg-dark-800 text-[10px] text-slate-400">#${escapeHtml(t)}</span>`).join('')}
                            </div>
                        </div>

                        <!-- Qwen 3 VL 32B Column -->
                        <div class="p-4 rounded-xl bg-dark-900/90 border border-purple-500/30 flex flex-col justify-between">
                            <div>
                                <div class="flex items-center justify-between pb-2 border-b border-white/5">
                                    <span class="text-xs font-bold text-purple-400 flex items-center gap-1.5">
                                        <span>🧠</span> Qwen 3 VL 32B
                                    </span>
                                    <span class="text-[11px] font-mono text-slate-400">${item.qwen.confidence}% conf</span>
                                </div>
                                <div class="mt-3">
                                    <span class="text-xs font-bold text-white font-mono break-all">${escapeHtml(item.qwen.category)}</span>
                                    <div class="flex flex-wrap gap-1 mt-1 text-[10px]">
                                        <span class="px-1.5 py-0.5 rounded bg-purple-500/20 text-purple-300">Domain: ${escapeHtml(qRaw.domain || 'N/A')}</span>
                                        ${qRaw.app_name ? `<span class="px-1.5 py-0.5 rounded bg-emerald-500/20 text-emerald-300">App: ${escapeHtml(qRaw.app_name)}</span>` : ''}
                                        ${qRaw.has_vincent ? '<span class="px-1.5 py-0.5 rounded bg-purple-500/20 text-purple-300 font-bold">👤 Vincent Face</span>' : ''}
                                    </div>
                                </div>
                                <p class="text-xs text-slate-300 italic mt-3 bg-dark-950/60 p-2.5 rounded-lg border border-white/5 leading-relaxed">
                                    "${escapeHtml(qRaw.rationale || 'No rationale')}."
                                </p>
                            </div>
                            <div class="flex flex-wrap gap-1 mt-3 pt-2 border-t border-white/5">
                                ${(qRaw.tags || []).slice(0, 5).map(t => `<span class="px-1.5 py-0.5 rounded bg-dark-800 text-[10px] text-slate-400">#${escapeHtml(t)}</span>`).join('')}
                            </div>
                        </div>

                    </div>
                `;

                container.appendChild(card);
            });
        }

        // Initial render
        applyFilters();
    </script>
</body>
</html>"""

def build_comparison_html(results: List[Dict[str, Any]]):
    total = len(results)
    agreements = sum(1 for r in results if r["gemini"]["category"] == r["qwen"]["category"])
    disagreements = total - agreements
    agreement_pct = round(agreements / total * 100, 1) if total else 0

    cards_json = json.dumps(results)

    html_content = (
        HTML_TEMPLATE
        .replace("__TOTAL__", str(total))
        .replace("__AGREEMENTS__", str(agreements))
        .replace("__DISAGREEMENTS__", str(disagreements))
        .replace("__AGREEMENT_PCT__", str(agreement_pct))
        .replace("__CARDS_JSON__", cards_json)
    )

    REPORT_HTML.write_text(html_content, encoding="utf-8")
    print(f"\n[Report] Wrote HTML comparison report to: {REPORT_HTML}")

async def main():
    print(f"[{time.strftime('%X')}] Starting Gemini 2.5 Flash 100-Photo Random Benchmark via OpenRouter...")

    conn = get_db()
    c = conn.cursor()
    query = """
        SELECT id, file_path, filename, year, qwen_category, qwen_confidence, qwen_json
        FROM inventory
        WHERE qwen_json IS NOT NULL
          AND local_only = 0
          AND is_sidecar = 0
          AND is_live_video = 0
          AND LOWER(extension) IN ('.jpg', '.jpeg', '.png', '.heic', '.webp')
        ORDER BY RANDOM()
        LIMIT 100
    """
    c.execute(query)
    items = c.fetchall()
    conn.close()

    total = len(items)
    print(f"Selected {total} random photos with existing Qwen classifications.")

    # Concurrency limit
    sem = asyncio.Semaphore(5)
    t_start = time.time()
    limits = httpx.Limits(max_keepalive_connections=10, max_connections=20)
    async with httpx.AsyncClient(limits=limits, timeout=90.0) as client:
        tasks = [classify_single(client, item, sem) for item in items]
        results_raw = await asyncio.gather(*tasks)

    results = [r for r in results_raw if r is not None]
    elapsed_total = time.time() - t_start

    print(f"\n{'='*70}")
    print(f"BENCHMARK COMPLETED in {elapsed_total:.1f}s ({len(results)}/{total} succeeded)")
    print(f"Throughput: {len(results)/elapsed_total:.2f} images/sec")
    print(f"{'='*70}\n")

    build_comparison_html(results)

if __name__ == "__main__":
    asyncio.run(main())

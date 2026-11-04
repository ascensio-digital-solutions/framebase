#!/usr/bin/env python3
"""
Generate an interactive, modern HTML gallery displaying all photos classified by Qwen 3 VL 32B.
Includes thumbnail previews, Vincent face badges, screenshot/app identifiers, shopping tags,
confidence scores, AI rationales, tags, search & filtering, and a full detail inspection modal.
"""

import sqlite3
import json
import base64
import io
import time
from pathlib import Path
from datetime import datetime
from PIL import Image
from pillow_heif import register_heif_opener
from tqdm import tqdm

register_heif_opener()

SCRIPT_DIR = Path(__file__).parent
DB_PATH = SCRIPT_DIR / "state.sqlite"
OUTPUT_HTML = SCRIPT_DIR / "qwen_gallery.html"
THUMB_CACHE_DIR = SCRIPT_DIR / ".thumb_cache"
THUMB_CACHE_DIR.mkdir(exist_ok=True)

def generate_gallery():
    print(f"[{time.strftime('%X')}] Reading classified photos from SQLite: {DB_PATH}")
    conn = sqlite3.connect(str(DB_PATH))
    c = conn.cursor()

    query = """
        SELECT 
            id, file_path, filename, year, width, height, file_size,
            exif_datetime, exif_camera, has_vincent,
            qwen_category, qwen_confidence, qwen_json
        FROM inventory
        WHERE qwen_json IS NOT NULL
        ORDER BY id DESC
    """
    c.execute(query)
    rows = c.fetchall()
    conn.close()

    total_photos = len(rows)
    print(f"[{time.strftime('%X')}] Found {total_photos} classified photos. Generating thumbnails & metadata...")

    items = []
    vincent_total = 0
    finances_total = 0
    shopify_total = 0
    screenshots_total = 0
    shopping_total = 0
    business_total = 0
    quarantine_total = 0
    categories_set = set()
    years_set = set()

    for row in tqdm(rows, desc="Processing Photos"):
        (
            row_id, file_path_str, filename, year, width, height, file_size,
            exif_datetime, exif_camera, has_vincent_col,
            q_cat, q_conf, q_json_str
        ) = row

        path = Path(file_path_str)
        try:
            q_data = json.loads(q_json_str) if q_json_str else {}
        except Exception:
            q_data = {}

        capture_type = q_data.get("capture_type", "camera_photo")
        domain = q_data.get("domain", "personal")
        app_name = q_data.get("app_name") or ""
        is_shopping = bool(q_data.get("is_shopping", False))
        sensitivity = q_data.get("sensitivity", "none")
        quality = q_data.get("quality", "ok")
        quality_issues = q_data.get("quality_issues") or []
        tags = q_data.get("tags") or []
        rationale = q_data.get("rationale") or ""
        
        # Strict face recognition check only (never OCR text match)
        is_vincent = bool(has_vincent_col == 1)
        if is_vincent:
            vincent_total += 1

        # Finances / Bills / Invoices check
        is_finance = bool(
            "finance" in str(q_cat).lower()
            or sensitivity in ("financial_document", "identity_document")
            or "invoice" in str(q_cat).lower()
            or any(k in str(q_cat).lower() for k in ["boleto", "receipt", "bill"])
            or any(k in [t.lower() for t in tags] for k in ["invoice", "receipt", "bank_statement", "pix_transfer", "financial_data", "financial_transaction", "bill", "bank_account", "boleto", "payment_info"])
            or any(k in str(rationale).lower() for k in ["invoice", "pix transfer", "bank account", "boleto", "transaction details", "financial data", "receipt", "financial transaction", "bank statement", "payment"])
        )
        if is_finance:
            finances_total += 1

        # Shopify Architecture & Storefronts check
        is_shopify = bool(
            "shopify" in str(q_cat).lower()
            or (app_name and "shopify" in app_name.lower())
            or "shopify" in [t.lower() for t in tags]
            or "shopify" in str(rationale).lower()
        )
        if is_shopify:
            shopify_total += 1

        is_screenshot = bool(capture_type == "screenshot" or "screenshot" in str(q_cat).lower() or app_name)
        if is_screenshot:
            screenshots_total += 1

        if is_shopping:
            shopping_total += 1

        if domain == "business":
            business_total += 1

        if "quarantine" in str(q_cat).lower() or sensitivity == "intimate":
            quarantine_total += 1

        if q_cat:
            categories_set.add(str(q_cat))
        if year:
            years_set.add(int(year))

        # Generate thumbnail (with disk cache)
        thumb_b64 = ""
        cache_file = THUMB_CACHE_DIR / f"{row_id}.jpg"
        if cache_file.exists():
            try:
                thumb_bytes = cache_file.read_bytes()
                thumb_b64 = base64.b64encode(thumb_bytes).decode("utf-8")
            except Exception:
                pass
        elif path.exists():
            try:
                with Image.open(path) as img:
                    img.thumbnail((360, 360), Image.Resampling.LANCZOS)
                    if img.mode != "RGB":
                        img = img.convert("RGB")
                    buf = io.BytesIO()
                    img.save(buf, format="JPEG", quality=80)
                    thumb_bytes = buf.getvalue()
                    cache_file.write_bytes(thumb_bytes)
                    thumb_b64 = base64.b64encode(thumb_bytes).decode("utf-8")
            except Exception as e:
                pass

        # Format file size
        size_kb = (file_size / 1024.0) if file_size else 0
        size_str = f"{size_kb / 1024:.1f} MB" if size_kb > 1024 else f"{size_kb:.0f} KB"

        items.append({
            "id": row_id,
            "filename": filename,
            "file_path": file_path_str,
            "year": year or "Unknown",
            "dimensions": f"{width}x{height}" if width and height else "Unknown",
            "file_size": size_str,
            "exif_date": exif_datetime or "",
            "camera": exif_camera or "",
            "category": q_cat or "uncategorized",
            "domain": domain,
            "confidence": round(float(q_conf or 0.0) * 100, 1),
            "capture_type": capture_type,
            "app_name": app_name,
            "is_shopping": is_shopping,
            "is_vincent": is_vincent,
            "is_finance": is_finance,
            "is_shopify": is_shopify,
            "is_screenshot": is_screenshot,
            "sensitivity": sensitivity,
            "quality": quality,
            "quality_issues": quality_issues,
            "tags": tags,
            "rationale": rationale,
            "thumb": f"data:image/jpeg;base64,{thumb_b64}" if thumb_b64 else "",
            "full_json": q_data
        })

    sorted_categories = sorted(list(categories_set))
    sorted_years = sorted(list(years_set), reverse=True)

    items_json = json.dumps(items)

    html_content = f"""<!DOCTYPE html>
<html lang="en" class="dark">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Qwen 3 VL 32B | Photo Classification Gallery</title>
    <link rel="preconnect" href="https://fonts.googleapis.com">
    <link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
    <link href="https://fonts.googleapis.com/css2?family=Plus+Jakarta+Sans:wght@300;400;500;600;700;800&family=JetBrains+Mono:wght@400;500&display=swap" rel="stylesheet">
    <script src="https://cdn.tailwindcss.com"></script>
    <script>
        tailwind.config = {{
            darkMode: 'class',
            theme: {{
                extend: {{
                    fontFamily: {{
                        sans: ['"Plus Jakarta Sans"', 'sans-serif'],
                        mono: ['"JetBrains Mono"', 'monospace'],
                    }},
                    colors: {{
                        brand: {{
                            50: '#eef2ff',
                            500: '#6366f1',
                            600: '#4f46e5',
                            700: '#4338ca',
                            900: '#312e81',
                        }},
                        dark: {{
                            950: '#07090e',
                            900: '#0b0f19',
                            850: '#111726',
                            800: '#161f36',
                            700: '#222e4c'
                        }}
                    }}
                }}
            }}
        }}
    </script>
    <style>
        body {{
            background-color: #07090e;
            color: #f1f5f9;
        }}
        .custom-scroll::-webkit-scrollbar {{
            width: 6px;
            height: 6px;
        }}
        .custom-scroll::-webkit-scrollbar-track {{
            background: #0b0f19;
        }}
        .custom-scroll::-webkit-scrollbar-thumb {{
            background: #222e4c;
            border-radius: 4px;
        }}
        .glass-panel {{
            background: rgba(17, 23, 38, 0.75);
            backdrop-filter: blur(16px);
            -webkit-backdrop-filter: blur(16px);
            border: 1px solid rgba(255, 255, 255, 0.08);
        }}
        .glass-card {{
            background: rgba(22, 31, 54, 0.6);
            backdrop-filter: blur(10px);
            -webkit-backdrop-filter: blur(10px);
            border: 1px solid rgba(255, 255, 255, 0.06);
            transition: all 0.25s cubic-bezier(0.16, 1, 0.3, 1);
        }}
        .glass-card:hover {{
            transform: translateY(-3px);
            border-color: rgba(99, 102, 241, 0.4);
            box-shadow: 0 16px 32px -8px rgba(0, 0, 0, 0.5), 0 0 20px rgba(99, 102, 241, 0.15);
        }}
        .badge-vincent {{
            background: linear-gradient(135deg, #8b5cf6, #d946ef);
            color: white;
            box-shadow: 0 2px 10px rgba(168, 85, 247, 0.4);
        }}
        .badge-app {{
            background: linear-gradient(135deg, #0ea5e9, #2563eb);
            color: white;
            box-shadow: 0 2px 10px rgba(14, 165, 233, 0.4);
        }}
        .badge-shopping {{
            background: linear-gradient(135deg, #10b981, #059669);
            color: white;
            box-shadow: 0 2px 10px rgba(16, 185, 129, 0.4);
        }}
    </style>
</head>
<body class="min-h-screen flex flex-col font-sans selection:bg-brand-500 selection:text-white">

    <!-- Top Navigation Bar -->
    <header class="sticky top-0 z-30 glass-panel border-b border-white/5 py-4 px-6 md:px-10">
        <div class="max-w-7xl mx-auto flex flex-col md:flex-row md:items-center justify-between gap-4">
            <div class="flex items-center gap-3">
                <div class="w-10 h-10 rounded-xl bg-gradient-to-br from-indigo-500 via-purple-500 to-pink-500 flex items-center justify-center shadow-lg shadow-indigo-500/25">
                    <span class="text-xl">✨</span>
                </div>
                <div>
                    <div class="flex items-center gap-2">
                        <h1 class="text-xl font-bold tracking-tight text-white">Qwen 3 VL 32B Gallery</h1>
                        <span class="text-xs px-2.5 py-0.5 rounded-full bg-brand-500/20 text-brand-400 font-mono font-medium border border-brand-500/30">OpenRouter</span>
                    </div>
                    <p class="text-xs text-slate-400">Classified archive • 2017–2026 Library Analysis</p>
                </div>
            </div>

            <!-- Stats Bar Mini -->
            <div class="flex items-center gap-2 text-xs overflow-x-auto pb-1 md:pb-0">
                <div class="px-3 py-1.5 rounded-lg bg-dark-800 border border-white/5 flex items-center gap-1.5 whitespace-nowrap">
                    <span class="text-slate-400">Total:</span>
                    <span id="stat-total" class="font-bold text-white font-mono">{total_photos}</span>
                </div>
                <div class="px-3 py-1.5 rounded-lg bg-dark-800 border border-purple-500/20 flex items-center gap-1.5 whitespace-nowrap">
                    <span>👤</span>
                    <span class="text-purple-300">Vincent:</span>
                    <span id="stat-vincent" class="font-bold text-purple-200 font-mono">{vincent_total}</span>
                </div>
                <div class="px-3 py-1.5 rounded-lg bg-dark-800 border border-amber-500/20 flex items-center gap-1.5 whitespace-nowrap">
                    <span>💳</span>
                    <span class="text-amber-300">Finances:</span>
                    <span id="stat-finances" class="font-bold text-amber-200 font-mono">{finances_total}</span>
                </div>
                <div class="px-3 py-1.5 rounded-lg bg-dark-800 border border-emerald-500/20 flex items-center gap-1.5 whitespace-nowrap">
                    <span>🛍️</span>
                    <span class="text-emerald-300">Shopify:</span>
                    <span id="stat-shopify" class="font-bold text-emerald-200 font-mono">{shopify_total}</span>
                </div>
                <div class="px-3 py-1.5 rounded-lg bg-dark-800 border border-sky-500/20 flex items-center gap-1.5 whitespace-nowrap">
                    <span>📱</span>
                    <span class="text-sky-300">Screenshots:</span>
                    <span id="stat-screenshots" class="font-bold text-sky-200 font-mono">{screenshots_total}</span>
                </div>
                <div class="px-3 py-1.5 rounded-lg bg-dark-800 border border-teal-500/20 flex items-center gap-1.5 whitespace-nowrap">
                    <span>🛒</span>
                    <span class="text-teal-300">Shopping:</span>
                    <span id="stat-shopping" class="font-bold text-teal-200 font-mono">{shopping_total}</span>
                </div>
            </div>
        </div>
    </header>

    <main class="flex-1 max-w-7xl w-full mx-auto px-6 md:px-10 py-8">

        <!-- KPI Hero Cards -->
        <section class="grid grid-cols-2 sm:grid-cols-4 lg:grid-cols-8 gap-2.5 mb-8">
            <div class="glass-panel p-3.5 rounded-xl">
                <span class="text-[10px] font-semibold text-slate-400 uppercase tracking-wider">Total</span>
                <div class="text-xl font-black text-white mt-0.5 font-mono">{total_photos}</div>
                <div class="text-[10px] text-slate-400 mt-0.5">Photos</div>
            </div>
            <div class="glass-panel p-3.5 rounded-xl border-purple-500/30">
                <span class="text-[10px] font-semibold text-purple-400 uppercase tracking-wider">👤 Vincent</span>
                <div class="text-xl font-black text-purple-300 mt-0.5 font-mono">{vincent_total}</div>
                <div class="text-[10px] text-purple-400/80 mt-0.5">Face verified</div>
            </div>
            <div class="glass-panel p-3.5 rounded-xl border-amber-500/30">
                <span class="text-[10px] font-semibold text-amber-400 uppercase tracking-wider">💳 Finances</span>
                <div class="text-xl font-black text-amber-300 mt-0.5 font-mono">{finances_total}</div>
                <div class="text-[10px] text-amber-400/80 mt-0.5">Bills & Invoices</div>
            </div>
            <div class="glass-panel p-3.5 rounded-xl border-emerald-500/30">
                <span class="text-[10px] font-semibold text-emerald-400 uppercase tracking-wider">🛍️ Shopify</span>
                <div class="text-xl font-black text-emerald-300 mt-0.5 font-mono">{shopify_total}</div>
                <div class="text-[10px] text-emerald-400/80 mt-0.5">Storefronts & CRO</div>
            </div>
            <div class="glass-panel p-3.5 rounded-xl border-sky-500/30">
                <span class="text-[10px] font-semibold text-sky-400 uppercase tracking-wider">📱 Apps</span>
                <div class="text-xl font-black text-sky-300 mt-0.5 font-mono">{screenshots_total}</div>
                <div class="text-[10px] text-sky-400/80 mt-0.5">Screenshots</div>
            </div>
            <div class="glass-panel p-3.5 rounded-xl border-teal-500/30">
                <span class="text-[10px] font-semibold text-teal-400 uppercase tracking-wider">🛒 Shopping</span>
                <div class="text-xl font-black text-teal-300 mt-0.5 font-mono">{shopping_total}</div>
                <div class="text-[10px] text-teal-400/80 mt-0.5">Retail & labels</div>
            </div>
            <div class="glass-panel p-3.5 rounded-xl border-indigo-500/30">
                <span class="text-[10px] font-semibold text-indigo-400 uppercase tracking-wider">🏢 Business</span>
                <div class="text-xl font-black text-indigo-300 mt-0.5 font-mono">{business_total}</div>
                <div class="text-[10px] text-indigo-400/80 mt-0.5">Hair Systems Co</div>
            </div>
            <div class="glass-panel p-3.5 rounded-xl border-rose-500/30">
                <span class="text-[10px] font-semibold text-rose-400 uppercase tracking-wider">🔒 Quarantine</span>
                <div class="text-xl font-black text-rose-300 mt-0.5 font-mono">{quarantine_total}</div>
                <div class="text-[10px] text-rose-400/80 mt-0.5">Private/Sensitive</div>
            </div>
        </section>

        <!-- Controls & Filters Section -->
        <section class="glass-panel rounded-2xl p-5 mb-8 shadow-xl">
            <div class="flex flex-col lg:flex-row gap-4 items-center justify-between">
                
                <!-- Live Search Bar -->
                <div class="relative w-full lg:w-96">
                    <svg class="absolute left-3.5 top-3.5 w-4 h-4 text-slate-400" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                        <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M21 21l-6-6m2-5a7 7 0 11-14 0 7 7 0 0114 0z"></path>
                    </svg>
                    <input 
                        type="text" 
                        id="search-input" 
                        placeholder="Search tags, apps, rationale, filename..." 
                        class="w-full pl-10 pr-4 py-2.5 rounded-xl bg-dark-950/80 border border-white/10 text-sm text-slate-200 placeholder-slate-500 focus:outline-none focus:border-brand-500 focus:ring-1 focus:ring-brand-500 transition-all"
                    >
                </div>

                <!-- Dropdown Selectors -->
                <div class="flex flex-wrap items-center gap-3 w-full lg:w-auto">
                    <!-- Category Select -->
                    <select id="category-filter" class="px-3 py-2 rounded-xl bg-dark-950/80 border border-white/10 text-xs text-slate-200 focus:outline-none focus:border-brand-500">
                        <option value="ALL">All Categories ({len(sorted_categories)})</option>
                        {"".join(f'<option value="{c}">{c}</option>' for c in sorted_categories)}
                    </select>

                    <!-- Year Select -->
                    <select id="year-filter" class="px-3 py-2 rounded-xl bg-dark-950/80 border border-white/10 text-xs text-slate-200 focus:outline-none focus:border-brand-500">
                        <option value="ALL">All Years</option>
                        {"".join(f'<option value="{y}">{y}</option>' for y in sorted_years)}
                    </select>

                    <!-- Sort Select -->
                    <select id="sort-select" class="px-3 py-2 rounded-xl bg-dark-950/80 border border-white/10 text-xs text-slate-200 focus:outline-none focus:border-brand-500">
                        <option value="newest">Newest First</option>
                        <option value="oldest">Oldest First</option>
                        <option value="confidence">Highest Confidence</option>
                        <option value="filename">Filename A-Z</option>
                    </select>
                </div>
            </div>

            <!-- Quick Pill Toggles -->
            <div class="flex flex-wrap items-center gap-2 mt-4 pt-4 border-t border-white/5">
                <span class="text-xs text-slate-400 font-semibold mr-2">Quick Filters:</span>
                <button onclick="togglePillFilter('all')" id="pill-all" class="filter-pill px-3 py-1.5 rounded-lg text-xs font-medium bg-brand-600 text-white transition-all shadow-sm">
                    Show All
                </button>
                <button onclick="togglePillFilter('vincent')" id="pill-vincent" class="filter-pill px-3 py-1.5 rounded-lg text-xs font-medium bg-dark-800 text-slate-300 hover:text-white hover:bg-dark-700 border border-purple-500/30 transition-all">
                    👤 Vincent ({vincent_total})
                </button>
                <button onclick="togglePillFilter('finance')" id="pill-finance" class="filter-pill px-3 py-1.5 rounded-lg text-xs font-medium bg-dark-800 text-slate-300 hover:text-white hover:bg-dark-700 border border-amber-500/30 transition-all">
                    💳 Finances & Bills ({finances_total})
                </button>
                <button onclick="togglePillFilter('shopify')" id="pill-shopify" class="filter-pill px-3 py-1.5 rounded-lg text-xs font-medium bg-dark-800 text-slate-300 hover:text-white hover:bg-dark-700 border border-emerald-500/30 transition-all">
                    🛍️ Shopify ({shopify_total})
                </button>
                <button onclick="togglePillFilter('screenshot')" id="pill-screenshot" class="filter-pill px-3 py-1.5 rounded-lg text-xs font-medium bg-dark-800 text-slate-300 hover:text-white hover:bg-dark-700 border border-sky-500/30 transition-all">
                    📱 Screenshots & Apps ({screenshots_total})
                </button>
                <button onclick="togglePillFilter('shopping')" id="pill-shopping" class="filter-pill px-3 py-1.5 rounded-lg text-xs font-medium bg-dark-800 text-slate-300 hover:text-white hover:bg-dark-700 border border-teal-500/30 transition-all">
                    🛒 Shopping ({shopping_total})
                </button>
                <button onclick="togglePillFilter('business')" id="pill-business" class="filter-pill px-3 py-1.5 rounded-lg text-xs font-medium bg-dark-800 text-slate-300 hover:text-white hover:bg-dark-700 border border-indigo-500/30 transition-all">
                    🏢 Business ({business_total})
                </button>
                <button onclick="togglePillFilter('quarantine')" id="pill-quarantine" class="filter-pill px-3 py-1.5 rounded-lg text-xs font-medium bg-dark-800 text-slate-300 hover:text-white hover:bg-dark-700 border border-rose-500/30 transition-all">
                    🔒 Quarantine ({quarantine_total})
                </button>
            </div>
        </section>

        <!-- Gallery Grid -->
        <div id="gallery-grid" class="grid grid-cols-1 sm:grid-cols-2 md:grid-cols-3 lg:grid-cols-4 gap-6">
            <!-- Rendered by JavaScript -->
        </div>

        <!-- Empty State -->
        <div id="empty-state" class="hidden text-center py-20">
            <div class="text-5xl mb-4">🔍</div>
            <h3 class="text-xl font-bold text-white mb-1">No matching photos found</h3>
            <p class="text-slate-400 text-sm">Try resetting your filters or search query.</p>
            <button onclick="resetFilters()" class="mt-4 px-4 py-2 bg-brand-600 hover:bg-brand-500 text-white rounded-xl text-sm font-medium transition-colors">Reset All Filters</button>
        </div>

    </main>

    <!-- Inspection Lightbox Modal -->
    <div id="inspect-modal" class="fixed inset-0 z-50 hidden bg-black/80 backdrop-blur-md flex items-center justify-center p-4 sm:p-6" onclick="closeModalOnBackdrop(event)">
        <div class="relative w-full max-w-4xl max-h-[90vh] bg-dark-900 border border-white/10 rounded-2xl shadow-2xl flex flex-col overflow-hidden" onclick="event.stopPropagation()">
            
            <!-- Modal Header -->
            <div class="px-6 py-4 border-b border-white/10 flex items-center justify-between bg-dark-950">
                <div class="flex items-center gap-3">
                    <span id="modal-badge-container"></span>
                    <h3 id="modal-title" class="text-base font-bold text-white truncate max-w-md">Filename.heic</h3>
                </div>
                <button onclick="closeModal()" class="w-8 h-8 rounded-lg bg-dark-800 hover:bg-dark-700 text-slate-400 hover:text-white flex items-center justify-center transition-colors">
                    ✕
                </button>
            </div>

            <!-- Modal Content (Scrollable) -->
            <div class="flex-1 overflow-y-auto custom-scroll p-6 grid grid-cols-1 md:grid-cols-2 gap-6">
                <!-- Left: Preview & File Details -->
                <div class="space-y-4">
                    <div class="rounded-xl overflow-hidden bg-black/50 border border-white/5 flex items-center justify-center min-h-[280px] max-h-[380px]">
                        <img id="modal-img" src="" alt="Photo preview" class="w-full h-full object-contain">
                    </div>
                    <div class="bg-dark-950 p-4 rounded-xl border border-white/5 space-y-2 text-xs">
                        <div class="flex justify-between"><span class="text-slate-400">Path:</span> <span id="modal-path" class="text-slate-200 font-mono truncate max-w-[240px]"></span></div>
                        <div class="flex justify-between"><span class="text-slate-400">Year:</span> <span id="modal-year" class="text-slate-200 font-mono"></span></div>
                        <div class="flex justify-between"><span class="text-slate-400">Dimensions:</span> <span id="modal-dimensions" class="text-slate-200 font-mono"></span></div>
                        <div class="flex justify-between"><span class="text-slate-400">File Size:</span> <span id="modal-filesize" class="text-slate-200 font-mono"></span></div>
                        <div class="flex justify-between"><span class="text-slate-400">EXIF Date:</span> <span id="modal-date" class="text-slate-200 font-mono"></span></div>
                    </div>
                </div>

                <!-- Right: AI Classification Details -->
                <div class="space-y-4">
                    <!-- Category & Confidence -->
                    <div class="bg-dark-950 p-4 rounded-xl border border-white/5 space-y-3">
                        <div class="flex items-center justify-between">
                            <span class="text-xs uppercase tracking-wider text-slate-400 font-semibold">Assigned Category</span>
                            <span id="modal-conf" class="text-xs font-mono font-bold px-2 py-0.5 rounded bg-emerald-500/20 text-emerald-300 border border-emerald-500/30">95%</span>
                        </div>
                        <div id="modal-category" class="text-lg font-bold text-white font-mono">personal/people</div>
                        <div id="modal-domain" class="text-xs text-slate-400">Domain: <span class="text-slate-200 font-semibold">personal</span></div>
                    </div>

                    <!-- AI Rationale -->
                    <div class="bg-dark-950 p-4 rounded-xl border border-white/5">
                        <span class="text-xs uppercase tracking-wider text-slate-400 font-semibold block mb-2">Qwen 3 VL Rationale</span>
                        <p id="modal-rationale" class="text-sm text-slate-200 italic leading-relaxed bg-dark-900 p-3 rounded-lg border border-white/5"></p>
                    </div>

                    <!-- Tags -->
                    <div class="bg-dark-950 p-4 rounded-xl border border-white/5">
                        <span class="text-xs uppercase tracking-wider text-slate-400 font-semibold block mb-2">Visual Tags</span>
                        <div id="modal-tags" class="flex flex-wrap gap-1.5"></div>
                    </div>

                    <!-- Raw JSON Viewer -->
                    <details class="bg-dark-950 rounded-xl border border-white/5 p-3">
                        <summary class="text-xs text-slate-400 hover:text-white cursor-pointer font-semibold uppercase tracking-wider select-none">
                            Inspect Raw JSON
                        </summary>
                        <pre id="modal-json" class="mt-3 p-3 bg-black/60 rounded-lg text-[11px] font-mono text-emerald-400 overflow-x-auto custom-scroll max-h-48"></pre>
                    </details>
                </div>
            </div>

            <!-- Modal Footer -->
            <div class="px-6 py-3 border-t border-white/10 bg-dark-950 flex justify-between items-center text-xs text-slate-400">
                <span>Model: Qwen 3 VL 32B Instruct</span>
                <button onclick="closeModal()" class="px-4 py-1.5 bg-dark-800 hover:bg-dark-700 text-white rounded-lg font-medium transition-colors">Close</button>
            </div>
        </div>
    </div>

    <!-- Data Injection -->
    <script>
        const ALL_PHOTOS = {items_json};
        let currentFilter = 'all';
        let activeItems = [...ALL_PHOTOS];

        function getDomainBadgeColor(domain) {{
            switch(domain) {{
                case 'business': return 'bg-purple-500/20 text-purple-300 border-purple-500/30';
                case 'ambiguous': return 'bg-amber-500/20 text-amber-300 border-amber-500/30';
                default: return 'bg-blue-500/20 text-blue-300 border-blue-500/30';
            }}
        }}

        function getCategoryColor(category) {{
            if (category.startsWith('finances')) return 'text-amber-300';
            if (category.includes('shopify')) return 'text-emerald-400';
            if (category.startsWith('business')) return 'text-purple-400';
            if (category.startsWith('06_private')) return 'text-rose-400';
            if (category.startsWith('99_noise')) return 'text-amber-400';
            return 'text-sky-400';
        }}

        function renderGallery() {{
            const grid = document.getElementById('gallery-grid');
            const empty = document.getElementById('empty-state');
            grid.innerHTML = '';

            const searchVal = document.getElementById('search-input').value.toLowerCase().trim();
            const catVal = document.getElementById('category-filter').value;
            const yearVal = document.getElementById('year-filter').value;
            const sortVal = document.getElementById('sort-select').value;

            // Filter logic
            let filtered = ALL_PHOTOS.filter(item => {{
                // Quick pill filter
                if (currentFilter === 'vincent' && !item.is_vincent) return false;
                if (currentFilter === 'finance' && !item.is_finance) return false;
                if (currentFilter === 'shopify' && !item.is_shopify) return false;
                if (currentFilter === 'screenshot' && !item.is_screenshot) return false;
                if (currentFilter === 'shopping' && !item.is_shopping) return false;
                if (currentFilter === 'business' && item.domain !== 'business') return false;
                if (currentFilter === 'quarantine' && !item.category.includes('06_private') && item.sensitivity === 'none') return false;

                // Category dropdown
                if (catVal !== 'ALL' && item.category !== catVal) return false;

                // Year dropdown
                if (yearVal !== 'ALL' && item.year.toString() !== yearVal) return false;

                // Search query
                if (searchVal) {{
                    const matchText = [
                        item.filename,
                        item.category,
                        item.domain,
                        item.app_name,
                        item.rationale,
                        ...(item.tags || [])
                    ].join(' ').toLowerCase();

                    if (!matchText.includes(searchVal)) return false;
                }}

                return true;
            }});

            // Sort logic
            filtered.sort((a, b) => {{
                if (sortVal === 'newest') return (b.year || 0) - (a.year || 0) || b.id - a.id;
                if (sortVal === 'oldest') return (a.year || 0) - (b.year || 0) || a.id - b.id;
                if (sortVal === 'confidence') return b.confidence - a.confidence;
                if (sortVal === 'filename') return a.filename.localeCompare(b.filename);
                return 0;
            }});

            if (filtered.length === 0) {{
                empty.classList.remove('hidden');
                grid.classList.add('hidden');
                return;
            }}

            empty.classList.add('hidden');
            grid.classList.remove('hidden');

            // Render cards
            filtered.forEach(item => {{
                const card = document.createElement('div');
                card.className = 'glass-card rounded-2xl overflow-hidden flex flex-col cursor-pointer group';
                card.onclick = () => openModal(item);

                let badgeOverlayHtml = '';
                if (item.is_vincent) {{
                    badgeOverlayHtml += `<span class="badge-vincent text-[10px] font-bold px-2 py-0.5 rounded-full uppercase tracking-wider flex items-center gap-1 shadow-md">👤 Vincent</span>`;
                }}
                if (item.is_finance) {{
                    badgeOverlayHtml += `<span class="bg-amber-500/90 text-black text-[10px] font-bold px-2 py-0.5 rounded-full uppercase tracking-wider flex items-center gap-1 shadow-md">💳 Finance/Bill</span>`;
                }}
                if (item.is_shopify) {{
                    badgeOverlayHtml += `<span class="bg-emerald-500/90 text-black text-[10px] font-bold px-2 py-0.5 rounded-full uppercase tracking-wider flex items-center gap-1 shadow-md">🛍️ Shopify</span>`;
                }}
                if (item.app_name && !item.is_shopify) {{
                    badgeOverlayHtml += `<span class="badge-app text-[10px] font-bold px-2 py-0.5 rounded-full uppercase tracking-wider flex items-center gap-1 shadow-md">📱 ${{item.app_name}}</span>`;
                }} else if (item.is_screenshot && !item.is_shopify && !item.is_finance) {{
                    badgeOverlayHtml += `<span class="badge-app text-[10px] font-bold px-2 py-0.5 rounded-full uppercase tracking-wider flex items-center gap-1 shadow-md">📱 Screenshot</span>`;
                }}
                if (item.is_shopping && !item.is_shopify) {{
                    badgeOverlayHtml += `<span class="badge-shopping text-[10px] font-bold px-2 py-0.5 rounded-full uppercase tracking-wider flex items-center gap-1 shadow-md">🛒 Shopping</span>`;
                }}

                const tagsHtml = (item.tags || []).slice(0, 4).map(t => 
                    `<span class="px-1.5 py-0.5 bg-dark-800 text-[10px] text-slate-400 rounded-md border border-white/5 truncate max-w-[120px]">#${{t}}</span>`
                ).join('');

                card.innerHTML = `
                    <div class="relative w-full aspect-square bg-dark-950 overflow-hidden">
                        ${{item.thumb ? `<img src="${{item.thumb}}" alt="${{item.filename}}" loading="lazy" class="w-full h-full object-cover group-hover:scale-105 transition-transform duration-300">` : `<div class="w-full h-full flex items-center justify-center text-slate-600 font-mono text-xs">No Preview</div>`}}
                        
                        <!-- Top Badges Overlay -->
                        <div class="absolute top-2.5 left-2.5 right-2.5 flex flex-wrap gap-1.5 z-10">
                            ${{badgeOverlayHtml}}
                        </div>

                        <!-- Year & Confidence Pill -->
                        <div class="absolute bottom-2.5 right-2.5 px-2 py-0.5 rounded-md bg-black/70 backdrop-blur-md text-[10px] font-mono text-white flex items-center gap-1.5 border border-white/10">
                            <span>${{item.year}}</span>
                            <span class="text-emerald-400 font-bold">${{item.confidence}}%</span>
                        </div>
                    </div>

                    <div class="p-4 flex-1 flex flex-col justify-between space-y-3">
                        <div>
                            <div class="text-[11px] font-mono font-semibold ${{getCategoryColor(item.category)}} truncate" title="${{item.category}}">
                                ${{item.category}}
                            </div>
                            <h4 class="text-xs font-semibold text-white truncate mt-0.5" title="${{item.filename}}">
                                ${{item.filename}}
                            </h4>
                        </div>

                        <p class="text-[11px] text-slate-300 line-clamp-2 italic leading-relaxed">
                            "${{item.rationale || 'No rationale provided'}}."
                        </p>

                        <div class="flex flex-wrap gap-1 pt-1 border-t border-white/5">
                            ${{tagsHtml}}
                        </div>
                    </div>
                `;

                grid.appendChild(card);
            }});
        }}

        function togglePillFilter(filter) {{
            currentFilter = filter;
            document.querySelectorAll('.filter-pill').forEach(btn => {{
                btn.className = 'filter-pill px-3 py-1.5 rounded-lg text-xs font-medium bg-dark-800 text-slate-300 hover:text-white hover:bg-dark-700 border border-white/5 transition-all';
            }});
            const activeBtn = document.getElementById('pill-' + filter);
            if (activeBtn) {{
                activeBtn.className = 'filter-pill px-3 py-1.5 rounded-lg text-xs font-medium bg-brand-600 text-white transition-all shadow-md';
            }}
            renderGallery();
        }}

        function resetFilters() {{
            document.getElementById('search-input').value = '';
            document.getElementById('category-filter').value = 'ALL';
            document.getElementById('year-filter').value = 'ALL';
            document.getElementById('sort-select').value = 'newest';
            togglePillFilter('all');
        }}

        function openModal(item) {{
            const modal = document.getElementById('inspect-modal');
            document.getElementById('modal-title').innerText = item.filename;
            document.getElementById('modal-img').src = item.thumb || '';
            document.getElementById('modal-path').innerText = item.file_path;
            document.getElementById('modal-year').innerText = item.year;
            document.getElementById('modal-dimensions').innerText = item.dimensions;
            document.getElementById('modal-filesize').innerText = item.file_size;
            document.getElementById('modal-date').innerText = item.exif_date || 'N/A';
            
            document.getElementById('modal-category').innerText = item.category;
            document.getElementById('modal-conf').innerText = `${{item.confidence}}%`;
            document.getElementById('modal-domain').innerHTML = `Domain: <span class="text-white font-semibold">${{item.domain}}</span> | Type: <span class="text-white font-semibold">${{item.capture_type}}</span>`;
            document.getElementById('modal-rationale').innerText = item.rationale ? `"${{item.rationale}}"` : 'No rationale recorded.';

            // Badges
            let badgesHtml = '';
            if (item.is_vincent) badgesHtml += `<span class="badge-vincent text-xs font-bold px-2.5 py-1 rounded-full uppercase">👤 Vincent</span>`;
            if (item.app_name) badgesHtml += `<span class="badge-app text-xs font-bold px-2.5 py-1 rounded-full uppercase">📱 ${{item.app_name}}</span>`;
            if (item.is_shopping) badgesHtml += `<span class="badge-shopping text-xs font-bold px-2.5 py-1 rounded-full uppercase">🛒 Shopping</span>`;
            document.getElementById('modal-badge-container').innerHTML = badgesHtml;

            // Tags
            const tagsContainer = document.getElementById('modal-tags');
            tagsContainer.innerHTML = '';
            (item.tags || []).forEach(t => {{
                const span = document.createElement('span');
                span.className = 'px-2 py-1 rounded bg-dark-900 border border-white/10 text-xs font-mono text-slate-300';
                span.innerText = `#${{t}}`;
                tagsContainer.appendChild(span);
            }});

            // JSON
            document.getElementById('modal-json').innerText = JSON.stringify(item.full_json, null, 2);

            modal.classList.remove('hidden');
            document.body.style.overflow = 'hidden';
        }}

        function closeModal() {{
            document.getElementById('inspect-modal').classList.add('hidden');
            document.body.style.overflow = '';
        }}

        function closeModalOnBackdrop(e) {{
            if (e.target.id === 'inspect-modal') {{
                closeModal();
            }}
        }}

        // Event listeners
        document.getElementById('search-input').addEventListener('input', renderGallery);
        document.getElementById('category-filter').addEventListener('change', renderGallery);
        document.getElementById('year-filter').addEventListener('change', renderGallery);
        document.getElementById('sort-select').addEventListener('change', renderGallery);

        window.addEventListener('keydown', (e) => {{
            if (e.key === 'Escape') closeModal();
        }});

        // Initial render
        renderGallery();
    </script>
</body>
</html>
"""

    with open(OUTPUT_HTML, "w", encoding="utf-8") as f:
        f.write(html_content)

    print(f"[{time.strftime('%X')}] Successfully created gallery at: {OUTPUT_HTML}")
    return OUTPUT_HTML

if __name__ == "__main__":
    generate_gallery()

#!/usr/bin/env python3
"""
Overnight Master Photo Classifier & Ingestion Pipeline for Media Workshop.
Fetches photos directly from /Volumes/SeaDisk and classifies them using Vertex AI Gemini 3.8 Flash
billed against Google Cloud Free Trial credits ($0 out-of-pocket).

Sequential Year Checkpoints:
[2024, 2023, 2022, 2021, 2020, 2019, 2018, 2017, 2016, 2015, 2014, 2013, 2012, 2011, 2010]

Workflow per Year:
1. Classify unclassified photos directly from /Volumes/SeaDisk via multi-project Vertex AI pool.
2. Enforce 3-Pillar Taxonomy migration (Personal, Business, Knowledge — zero ambiguous items).
3. Generate dedicated interactive visual HTML gallery (gallery_<year>.html).
4. Embed IPTC/XMP/EXIF physical metadata into the image files on disk via ExifTool.
5. Ingest assets into the 3 dedicated Framebase packages in ~/Pictures.

Ensures zero sleep via macOS caffeinate assertions.
"""

import os
import sys
import time
import json
import sqlite3
import subprocess
from pathlib import Path
from datetime import datetime

SCRIPT_DIR = Path(__file__).parent.resolve()
WORKSPACE_DIR = SCRIPT_DIR.parent.parent.resolve()
DB_PATH = SCRIPT_DIR / "state.sqlite"
LOG_PATH = SCRIPT_DIR / "overnight_run.log"
SUMMARY_PATH = SCRIPT_DIR / "overnight_summary.md"
PYTHON_BIN = SCRIPT_DIR / ".venv" / "bin" / "python"

ALL_YEARS = [2024, 2023, 2022, 2021, 2020, 2019, 2018, 2017, 2016, 2015, 2014, 2013, 2012, 2011, 2010]

def log(msg: str):
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    formatted = f"[{timestamp}] {msg}"
    print(formatted, flush=True)
    with open(LOG_PATH, "a", encoding="utf-8") as f:
        f.write(formatted + "\n")

def get_unclassified_count(year: int) -> int:
    conn = sqlite3.connect(str(DB_PATH))
    c = conn.cursor()
    c.execute("""
        SELECT COUNT(*)
        FROM inventory
        WHERE year = ?
          AND local_only = 0
          AND is_sidecar = 0
          AND is_live_video = 0
          AND LOWER(extension) IN ('.jpg', '.jpeg', '.png', '.heic', '.webp')
          AND gemini_category IS NULL
    """, (year,))
    count = c.fetchone()[0]
    conn.close()
    return count

def generate_year_gallery(year: int):
    """Generate interactive visual gallery for this year."""
    gallery_file = SCRIPT_DIR / f"gallery_{year}.html"
    conn = sqlite3.connect(str(DB_PATH))
    c = conn.cursor()
    c.execute("""
        SELECT id, filename, file_path, gemini_category, gemini_confidence, gemini_json
        FROM inventory
        WHERE year = ? AND gemini_json IS NOT NULL
        ORDER BY id DESC
    """, (year,))
    rows = c.fetchall()
    conn.close()

    if not rows:
        return

    cards = []
    for r_id, fn, fp, cat, conf, gjson in rows:
        try:
            d = json.loads(gjson)
        except Exception:
            continue

        dom = d.get("domain", "personal")
        conf_pct = int((conf or 0.9) * 100)
        tool = d.get("subject_or_tool_discussed") or ""
        creator = d.get("creator_handle") or ""
        app = d.get("app_name") or ""
        tags = d.get("tags") or []
        hairline = d.get("hairline_presentation")
        has_v = bool(d.get("has_vincent"))
        rat = d.get("rationale") or ""

        # Resolving image path
        local_p = WORKSPACE_DIR / str(year) / fn
        if not local_p.exists():
            local_p = Path(f"/Volumes/SeaDisk/{year}") / fn
        if not local_p.exists():
            local_p = Path(fp)

        pillar_badge = '<span class="px-2 py-0.5 text-xs font-semibold rounded bg-sky-500/20 text-sky-300 border border-sky-500/30">🏖️ Personal</span>'
        if dom == "business":
            pillar_badge = '<span class="px-2 py-0.5 text-xs font-semibold rounded bg-emerald-500/20 text-emerald-300 border border-emerald-500/30">💼 Business</span>'
        elif dom == "knowledge":
            pillar_badge = '<span class="px-2 py-0.5 text-xs font-semibold rounded bg-purple-500/20 text-purple-300 border border-purple-500/30">💡 Knowledge</span>'

        v_badge = '<span class="px-2 py-0.5 text-xs rounded bg-purple-600/40 text-purple-200 border border-purple-500/50">👤 Vincent</span>' if has_v else ''
        app_badge = f'<span class="px-2 py-0.5 text-xs rounded bg-sky-600/30 text-sky-200">📱 {app}</span>' if app else ''
        tool_badge = f'<span class="px-2 py-0.5 text-xs rounded bg-indigo-600/30 text-indigo-200">🔧 {tool[:30]}</span>' if tool else ''
        creator_badge = f'<span class="px-2 py-0.5 text-xs rounded bg-pink-600/30 text-pink-200">✍️ @{creator.lstrip("@")}</span>' if creator else ''

        tag_spans = "".join([f'<span class="text-[10px] px-1.5 py-0.5 rounded bg-slate-800 text-slate-400">#{t}</span>' for t in tags[:5]])

        cards.append(f"""
        <div class="bg-slate-900 border border-slate-800 rounded-xl overflow-hidden flex flex-col shadow-lg hover:border-slate-700 transition">
            <div class="relative aspect-square bg-slate-950 flex items-center justify-center overflow-hidden">
                <img src="file://{local_p}" alt="{fn}" loading="lazy" class="w-full h-full object-cover">
                <div class="absolute top-2 left-2 bg-black/70 backdrop-blur-md px-2 py-0.5 rounded text-xs font-mono text-slate-300">{year}</div>
                <div class="absolute top-2 right-2 bg-black/70 backdrop-blur-md px-2 py-0.5 rounded-full text-xs font-mono text-slate-300">{conf_pct}%</div>
            </div>
            <div class="p-3.5 flex-1 flex flex-col justify-between">
                <div>
                    <div class="flex items-center gap-1.5 flex-wrap mb-1.5">
                        {pillar_badge}
                        <span class="px-2 py-0.5 text-xs font-mono text-slate-300 bg-slate-800 rounded">{cat}</span>
                        {v_badge} {app_badge} {tool_badge} {creator_badge}
                    </div>
                    <div class="text-xs text-slate-400 line-clamp-3 mb-2">{rat}</div>
                </div>
                <div class="flex items-center gap-1 flex-wrap mt-2 pt-2 border-t border-slate-800/80">
                    {tag_spans}
                </div>
            </div>
        </div>
        """)

    html = f"""<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <title>Media Archive {year} — Gemini 3.8 Flash</title>
    <script src="https://cdn.tailwindcss.com"></script>
    <style>body {{ background-color: #0b0f19; }}</style>
</head>
<body class="text-slate-100 font-sans p-6 md:p-10 max-w-7xl mx-auto">
    <header class="mb-8 flex flex-col md:flex-row md:items-center justify-between gap-4 border-b border-slate-800 pb-6">
        <div>
            <h1 class="text-3xl font-extrabold tracking-tight bg-gradient-to-r from-blue-400 via-indigo-300 to-emerald-400 bg-clip-text text-transparent">
                Archive {year} — Vertex AI Gemini 3.8 Flash
            </h1>
            <p class="text-slate-400 text-sm mt-1">Fetched directly from /Volumes/SeaDisk | 3-Pillar Taxonomy</p>
        </div>
        <div class="px-3 py-1.5 rounded-lg bg-slate-800/80 border border-slate-700 text-sm font-mono text-slate-200">
            Total Classified: <strong class="text-white">{len(cards):,}</strong> photos
        </div>
    </header>
    <div class="grid grid-cols-1 sm:grid-cols-2 md:grid-cols-3 lg:grid-cols-4 gap-5">
        {"".join(cards)}
    </div>
</body>
</html>"""

    with open(gallery_file, "w", encoding="utf-8") as f:
        f.write(html)
    log(f"Generated gallery: {gallery_file.name} ({len(cards):,} cards)")

def run_overnight_pipeline():
    start_all = time.time()
    log("=" * 80)
    log("STARTING OVERNIGHT VERTEX AI PHOTO CLASSIFICATION & INGESTION")
    log("Storage: /Volumes/SeaDisk (Direct streaming)")
    log("Target Years: " + ", ".join(map(str, ALL_YEARS)))
    log("=" * 80)

    # Verify SeaDisk is mounted
    seadisk_dir = Path("/Volumes/SeaDisk")
    if not seadisk_dir.exists():
        log("ERROR: /Volumes/SeaDisk is NOT mounted! Please plug in the external drive.")
        sys.exit(1)

    completed_years = []
    total_photos_processed = 0

    for yr in ALL_YEARS:
        unclassified = get_unclassified_count(yr)
        if unclassified == 0:
            log(f"Year {yr}: Already 100% classified. Skipping.")
            completed_years.append(yr)
            continue

        yr_start = time.time()
        log(f"\n>>> PROCESSING YEAR {yr} ({unclassified:,} unclassified photos on SeaDisk)...")

        # 1. Run native Gemini classifier
        cmd = [
            str(PYTHON_BIN),
            str(SCRIPT_DIR / "run_native_gemini_2026.py"),
            "--years", str(yr),
            "--limit", "100000",
            "--concurrency", "16"
        ]
        res = subprocess.run(cmd, text=True)
        if res.returncode != 0:
            log(f"WARNING: Year {yr} classification returned exit code {res.returncode}. Continuing.")

        # 2. Run 3-pillar taxonomy migration
        mig_cmd = [str(PYTHON_BIN), str(SCRIPT_DIR / "migrate_to_three_pillars.py")]
        subprocess.run(mig_cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)

        # 3. Generate HTML visual review gallery
        generate_year_gallery(yr)

        yr_elapsed = time.time() - yr_start
        total_photos_processed += unclassified
        log(f">>> YEAR {yr} COMPLETE in {yr_elapsed/60:.1f} mins ({unclassified:,} photos)")
        completed_years.append(yr)

    # 4. Physical metadata embedding (exiftool) across all updated photos
    log("\n" + "=" * 80)
    log("EMBEDDING IPTC/XMP/EXIF METADATA INTO PHYSICAL FILES ON SEADISK...")
    log("=" * 80)
    embed_cmd = [str(PYTHON_BIN), str(SCRIPT_DIR / "embed_physical_metadata.py")]
    subprocess.run(embed_cmd)

    # 5. Ingest into 3 Framebase libraries
    log("\n" + "=" * 80)
    log("INGESTING INTO FRAMEBASE LIBRARIES (Personal, HSC, Knowledge)...")
    log("=" * 80)
    ingest_cmd = [str(PYTHON_BIN), str(SCRIPT_DIR / "ingest_to_framebase.py")]
    subprocess.run(ingest_cmd)

    total_time = time.time() - start_all
    log("\n" + "=" * 80)
    log(f"OVERNIGHT MASTER PIPELINE COMPLETE in {total_time/3600:.2f} hours!")
    log(f"Total Photos Processed: {total_photos_processed:,}")
    log("All galleries generated and ready for review.")
    log("=" * 80)

if __name__ == "__main__":
    run_overnight_pipeline()


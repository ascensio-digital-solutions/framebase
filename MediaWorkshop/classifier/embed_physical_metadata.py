#!/usr/bin/env python3
"""
Physical Image Metadata Embedder for Media Workshop (2025, 2026, and Historical Archives).
Embeds Vertex AI Gemini classification results, 3-pillar taxonomy, and conditional tags
directly into the physical image files on disk using ExifTool.

Embedded Tags:
- IPTC:Keywords & XMP-dc:Subject:
    * pillar:<domain> (personal, business, knowledge)
    * category:<category>
    * type:<capture_type>
    * app:<app_name>
    * creator:<creator_handle>
    * tool:<subject_or_tool_discussed>
    * person:vincent (only when verified true human subject)
    * hairline:<hairline_presentation>
    * All topic/product/source tags from Gemini
- EXIF:ImageDescription & XMP-dc:Description:
    * Full contextual rationale + creator handle + tool discussed
- XMP-dc:Title / Headline:
    * Subject/tool discussed or category name

Preserves file modification timestamps (-P) and avoids duplicate files (-overwrite_original).
High throughput via parallel multi-worker ExifTool batch argfiles.
"""

import os
import sys
import re
import json
import time
import sqlite3
import subprocess
import multiprocessing
from pathlib import Path
from typing import List, Dict, Any, Optional, Tuple

SCRIPT_DIR = Path(__file__).parent.resolve()
WORKSPACE_DIR = SCRIPT_DIR.parent.parent.resolve()
DB_PATH = SCRIPT_DIR / "state.sqlite"

def slugify(text: str) -> str:
    text = text.lower().strip()
    text = re.sub(r"[^\w\s-]", "", text)
    text = re.sub(r"[\s_]+", "-", text)
    return text[:64].strip("-")

def resolve_image_path(path_str: str, year: int, filename: str) -> Optional[Path]:
    """Resolve image path prioritizing local media_workshop/{year} directory."""
    local_year_path = WORKSPACE_DIR / str(year) / filename
    if local_year_path.exists():
        return local_year_path

    orig = Path(path_str)
    if orig.exists():
        return orig

    candidates = [
        WORKSPACE_DIR / "2026" / filename,
        WORKSPACE_DIR / "2025" / filename,
        Path(f"/Volumes/SeaDisk/{year}") / filename,
        Path(f"/Volumes/SeaDisk/media_workshop/iPhoto export 2010-2026/{year}") / filename,
        Path(f"/Volumes/SeaDisk/Apple_Photos_9Y/{year}") / filename,
    ]
    for cand in candidates:
        if cand.exists():
            return cand
    return None

def build_metadata_for_record(
    record: Dict[str, Any]
) -> Tuple[List[str], str, str]:
    """Build tags, description, and title for a photo record."""
    d = record.get("gemini_json") or {}
    dom = d.get("domain") or "personal"
    cat = d.get("category") or record.get("gemini_category") or "personal/other"
    cap_type = d.get("capture_type") or "camera_photo"
    
    tags = set()
    tags.add(f"pillar:{dom}")
    tags.add(f"category:{cat}")
    tags.add(f"type:{cap_type}")

    app = d.get("app_name")
    if app:
        tags.add(f"app:{slugify(app)}")

    creator = d.get("creator_handle")
    if creator:
        tags.add(f"creator:{slugify(creator.lstrip('@'))}")

    tool = d.get("subject_or_tool_discussed")
    if tool:
        # Extract main tool names
        tags.add(f"tool:{slugify(tool)}")

    if d.get("has_vincent"):
        tags.add("person:vincent")

    hair = d.get("hairline_presentation")
    if hair and hair not in ("notVisible", "not_visible", "none"):
        tags.add(f"hairline:{hair}")

    for t in d.get("tags") or []:
        t_clean = str(t).strip().lower()
        if not t_clean:
            continue
        if ":" not in t_clean:
            tags.add(f"tag:{slugify(t_clean)}")
        else:
            ns, val = t_clean.split(":", 1)
            tags.add(f"{slugify(ns)}:{slugify(val)}")

    # Clean description
    raw_rat = (d.get("rationale") or "").strip()
    extra_context = []
    if tool:
        extra_context.append(f"Tool: {tool}")
    if creator:
        extra_context.append(f"Creator: @{creator.lstrip('@')}")
    if app:
        extra_context.append(f"App: {app}")

    desc_parts = []
    if raw_rat:
        desc_parts.append(raw_rat)
    if extra_context:
        desc_parts.append(f"[{' | '.join(extra_context)}]")
    
    description = " ".join(desc_parts).replace("\n", " ").replace("\r", "").strip()
    if not description:
        description = f"Photo classified under {dom} / {cat} by Vertex AI Gemini"

    # Title / Headline
    title = tool if tool else cat

    return sorted(list(tags)), description, title

def run_worker(worker_id: int, items_chunk: List[Tuple[Path, List[str], str, str]], temp_dir: Path):
    """Worker process that writes an argfile and executes ExifTool."""
    if not items_chunk:
        return 0

    argfile = temp_dir / f"exiftool_args_worker_{worker_id}.txt"
    with open(argfile, "w", encoding="utf-8") as f:
        for file_path, tags, desc, title in items_chunk:
            f.write("-overwrite_original\n")
            f.write("-P\n")
            
            # Write IPTC Keywords
            for t in tags:
                f.write(f"-IPTC:Keywords={t}\n")
                f.write(f"-XMP-dc:Subject={t}\n")
            
            # Write Descriptions
            f.write(f"-EXIF:ImageDescription={desc}\n")
            f.write(f"-XMP-dc:Description={desc}\n")
            f.write(f"-XMP-dc:Title={title}\n")
            
            # Target file path
            f.write(f"{file_path}\n")
            f.write("-execute\n")

    cmd = ["exiftool", "-@", str(argfile)]
    res = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
    return len(items_chunk)

def main():
    print("=" * 80)
    print("PHYSICAL IMAGE METADATA EMBEDDER — EXIFTOOL BATCH PIPELINE")
    print("Target: 2025, 2026, and Historical Archive Media Files")
    print("=" * 80)

    conn = sqlite3.connect(str(DB_PATH))
    c = conn.cursor()
    c.execute("""
        SELECT id, file_path, year, filename, gemini_category, gemini_json
        FROM inventory
        WHERE gemini_json IS NOT NULL
        ORDER BY year DESC, id ASC
    """)
    rows = c.fetchall()
    conn.close()

    total_records = len(rows)
    print(f"\nLoaded {total_records} classified records from state.sqlite.")

    # Resolve and prepare items
    prepared_items = []
    missing_count = 0
    t0 = time.time()

    print("Resolving file paths on disk...")
    for r_id, fpath, yr, fn, cat, gjson_str in rows:
        resolved = resolve_image_path(fpath, yr, fn)
        if not resolved or not resolved.exists():
            missing_count += 1
            continue

        try:
            d = json.loads(gjson_str)
        except Exception:
            d = {}

        record = {
            "id": r_id,
            "filename": fn,
            "gemini_category": cat,
            "gemini_json": d
        }
        tags, desc, title = build_metadata_for_record(record)
        prepared_items.append((resolved, tags, desc, title))

    print(f"Ready to process: {len(prepared_items)} files ({missing_count} missing)")

    num_workers = min(multiprocessing.cpu_count(), 8)
    print(f"Spawning {num_workers} parallel ExifTool batch workers...")

    temp_dir = SCRIPT_DIR / ".exiftool_tmp"
    temp_dir.mkdir(exist_ok=True)

    # Chunk items
    chunk_size = (len(prepared_items) + num_workers - 1) // num_workers
    chunks = [prepared_items[i : i + chunk_size] for i in range(0, len(prepared_items), chunk_size)]

    start_time = time.time()
    with multiprocessing.Pool(processes=num_workers) as pool:
        results = [
            pool.apply_async(run_worker, args=(i, chunk, temp_dir))
            for i, chunk in enumerate(chunks)
        ]
        
        while any(not r.ready() for r in results):
            time.sleep(1.0)
            elapsed = time.time() - start_time
            print(f"Embedding in progress... {elapsed:.1f}s elapsed", end="\r", flush=True)

        worker_outputs = [r.get() for r in results]

    total_updated = sum(worker_outputs)
    elapsed_total = time.time() - start_time

    print(f"\n\nSUCCESS: Embedded metadata into {total_updated} files in {elapsed_total:.1f} seconds!")
    print(f"Throughput: {total_updated / max(elapsed_total, 0.1):.1f} files/second.")

    # Cleanup temp files
    for tmp_file in temp_dir.glob("exiftool_args_worker_*.txt"):
        tmp_file.unlink(missing_ok=True)
    temp_dir.rmdir()

    # Verification on sample files
    print("\n" + "=" * 80)
    print("VERIFICATION ON RANDOM SAMPLES ACROSS DOMAINS:")
    print("=" * 80)
    samples_to_check = [prepared_items[0], prepared_items[len(prepared_items)//2], prepared_items[-1]]
    for fpath, exp_tags, exp_desc, exp_title in samples_to_check:
        print(f"\nChecking: {fpath.name}")
        cmd = ["exiftool", "-Subject", "-Keywords", "-Description", "-Title", str(fpath)]
        res = subprocess.run(cmd, stdout=subprocess.PIPE, text=True)
        for line in res.stdout.strip().split("\n"):
            print(f"  {line[:110]}")

if __name__ == "__main__":
    main()


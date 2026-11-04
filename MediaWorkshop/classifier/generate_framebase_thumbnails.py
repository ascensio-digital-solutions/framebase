#!/usr/bin/env python3
"""
Generate Framebase Local Thumbnail Cache directly from /Volumes/SeaDisk.
Pre-populates ~/Library/Caches/com.vincentlaroche.framebase/Thumbnails/
so Framebase never needs local master copies to render thumbnails or previews.
"""

import os
import sys
import time
import sqlite3
import subprocess
from pathlib import Path
from concurrent.futures import ProcessPoolExecutor, as_completed
from typing import Dict, List, Tuple, Optional
from PIL import Image

CACHE_DIR = Path.home() / "Library/Caches/com.vincentlaroche.framebase/Thumbnails"
STATE_DB = Path("/Users/vincent/04_systems/media_workshop/tools/photo_classifier/state.sqlite")
PICTURES_DIR = Path.home() / "Pictures"

LIBRARIES = [
    PICTURES_DIR / "HSC Library.framebase/Catalog/catalog.sqlite",
    PICTURES_DIR / "Knowledge Library.framebase/Catalog/catalog.sqlite",
    PICTURES_DIR / "Personal Library.framebase/Catalog/catalog.sqlite",
]

def resolve_source_file(inventory_map: Dict[str, Tuple[str, int, str]], sha256: Optional[str], filename: str) -> Optional[Path]:
    if sha256 and sha256 in inventory_map:
        fp, yr, fn = inventory_map[sha256]
        p_iphoto = Path(f"/Volumes/SeaDisk/media_workshop/iPhoto export 2010-2026/{yr}/{fn}")
        if p_iphoto.exists():
            return p_iphoto
        p_orig = Path(fp)
        if p_orig.exists():
            return p_orig
        p_yr = Path(f"/Volumes/SeaDisk/{yr}/{fn}")
        if p_yr.exists():
            return p_yr

    # Fallback search by filename across years on SeaDisk
    for yr in range(2026, 2009, -1):
        p = Path(f"/Volumes/SeaDisk/media_workshop/iPhoto export 2010-2026/{yr}/{filename}")
        if p.exists():
            return p
        p2 = Path(f"/Volumes/SeaDisk/{yr}/{filename}")
        if p2.exists():
            return p2

    return None

def process_single_asset(item: dict) -> Tuple[str, bool, str]:
    aid = item["id"]
    file_size = item["file_size"]
    mod_ms = item["modified_at_ms"]
    src_path_str = item["src_path"]

    shard = aid[:2]
    shard_dir = CACHE_DIR / shard
    shard_dir.mkdir(parents=True, exist_ok=True)

    # 1. Grid Thumbnails (176x176 at scale 1.0 and scale 2.0)
    t1 = shard_dir / f"v1-thumbnail-{aid}-{file_size}-{mod_ms}-176x176-3ff0000000000000.png"
    t2 = shard_dir / f"v1-thumbnail-{aid}-{file_size}-{mod_ms}-176x176-4000000000000000.png"

    # 2. Inspector Preview (720x720 at scale 1.0)
    p1 = shard_dir / f"v1-preview-{aid}-{file_size}-{mod_ms}-720x720-3ff0000000000000.png"

    have_thumb = t1.exists() and t1.stat().st_size > 0
    have_prev = p1.exists() and p1.stat().st_size > 0

    if have_thumb and have_prev:
        # Ensure hardlink t2 exists
        if not (t2.exists() and t2.stat().st_size > 0):
            try:
                if t2.exists(): t2.unlink()
                os.link(t1, t2)
            except Exception:
                pass
        return (aid, True, "cached")

    src = Path(src_path_str)
    if not src.exists():
        return (aid, False, "source_missing")

    ext = src.suffix.lower()

    # Generate 720px preview first (or 352px thumbnail directly)
    temp_prev = shard_dir / f"tmp_prev_{aid}.png"
    temp_thumb = shard_dir / f"tmp_thumb_{aid}.png"

    try:
        if ext in (".jpg", ".jpeg", ".png", ".webp"):
            try:
                with Image.open(src) as img:
                    # Fix EXIF orientation if needed
                    try:
                        from PIL import ImageOps
                        img = ImageOps.exif_transpose(img)
                    except Exception:
                        pass
                    
                    # Preview (max 720)
                    img_prev = img.copy()
                    img_prev.thumbnail((720, 720), Image.Resampling.LANCZOS)
                    img_prev.save(temp_prev, "PNG")

                    # Thumbnail (max 352 for sharp 2x retina display)
                    img.thumbnail((352, 352), Image.Resampling.LANCZOS)
                    img.save(temp_thumb, "PNG")
            except Exception:
                # Fallback to sips if PIL fails
                subprocess.run(["sips", "-Z", "720", str(src), "-s", "format", "png", "--out", str(temp_prev)], capture_output=True)
                subprocess.run(["sips", "-Z", "352", str(src), "-s", "format", "png", "--out", str(temp_thumb)], capture_output=True)
        else:
            # HEIC, TIFF, DNG, etc. use native macOS sips (Apple hardware decoded)
            subprocess.run(["sips", "-Z", "720", str(src), "-s", "format", "png", "--out", str(temp_prev)], capture_output=True)
            subprocess.run(["sips", "-Z", "352", str(src), "-s", "format", "png", "--out", str(temp_thumb)], capture_output=True)

        # Move into place atomically
        if temp_prev.exists() and temp_prev.stat().st_size > 0:
            temp_prev.replace(p1)
        elif temp_prev.exists():
            temp_prev.unlink()

        if temp_thumb.exists() and temp_thumb.stat().st_size > 0:
            temp_thumb.replace(t1)
            try:
                if t2.exists(): t2.unlink()
                os.link(t1, t2)
            except Exception:
                pass
            return (aid, True, "generated")
        else:
            if temp_thumb.exists(): temp_thumb.unlink()
            return (aid, False, "decode_failed")

    except Exception as e:
        if temp_prev.exists(): temp_prev.unlink(missing_ok=True)
        if temp_thumb.exists(): temp_thumb.unlink(missing_ok=True)
        return (aid, False, str(e))

def main():
    print("=" * 80)
    print("FRAMEBASE HIGH-THROUGHPUT THUMBNAIL CACHE GENERATOR")
    print("Populating local caches from /Volumes/SeaDisk (Zero Mac SSD master copies)")
    print("=" * 80)

    CACHE_DIR.mkdir(parents=True, exist_ok=True)

    # 1. Load state.sqlite inventory mapping
    print("\n[1/4] Loading inventory mapping from state.sqlite...")
    conn = sqlite3.connect(str(STATE_DB))
    c = conn.cursor()
    c.execute("SELECT sha256, file_path, year, filename FROM inventory WHERE sha256 IS NOT NULL")
    inventory_map = {}
    for sha, fp, yr, fn in c.fetchall():
        inventory_map[sha] = (fp, yr, fn)
    conn.close()
    print(f"Loaded {len(inventory_map):,} assets from inventory.")

    # 2. Gather all assets across the 3 Framebase libraries
    print("\n[2/4] Reading assets from Framebase catalogs...")
    all_tasks = []
    
    for lib_path in LIBRARIES:
        if not lib_path.exists():
            continue
        lib_name = lib_path.parent.parent.name
        conn = sqlite3.connect(str(lib_path))
        c = conn.cursor()
        
        c.execute("""
            SELECT a.id, a.filename, a.file_size, a.modified_at_ms, acs.blob_sha256
            FROM assets a
            LEFT JOIN asset_cloud_state acs ON a.id = acs.asset_id
        """)
        rows = c.fetchall()
        conn.close()
        
        lib_found = 0
        for aid, fn, sz, mod_ms, sha in rows:
            shard = aid[:2]
            shard_dir = CACHE_DIR / shard
            t1 = shard_dir / f"v1-thumbnail-{aid}-{sz}-{mod_ms}-176x176-3ff0000000000000.png"
            t2 = shard_dir / f"v1-thumbnail-{aid}-{sz}-{mod_ms}-176x176-4000000000000000.png"
            p1 = shard_dir / f"v1-preview-{aid}-{sz}-{mod_ms}-720x720-3ff0000000000000.png"
            
            if t1.exists() and p1.exists() and t1.stat().st_size > 0:
                if not (t2.exists() and t2.stat().st_size > 0):
                    try:
                        if t2.exists(): t2.unlink()
                        os.link(t1, t2)
                    except Exception:
                        pass
                continue
            
            src = resolve_source_file(inventory_map, sha, fn)
            if src and src.exists():
                all_tasks.append({
                    "id": aid,
                    "filename": fn,
                    "file_size": sz,
                    "modified_at_ms": mod_ms,
                    "src_path": str(src)
                })
                lib_found += 1

        print(f"  {lib_name}: {len(rows):,} total assets | {lib_found:,} pending thumbnail generation")

    total_tasks = len(all_tasks)
    print(f"\n[3/4] Starting parallel thumbnail generation for {total_tasks:,} assets...")

    if total_tasks == 0:
        print("All thumbnails are already generated and up to date!")
        return

    workers = 10
    t0 = time.time()
    generated = 0
    cached = 0
    failed = 0

    with ProcessPoolExecutor(max_workers=workers) as executor:
        futures = {executor.submit(process_single_asset, task): task for task in all_tasks}
        
        for idx, fut in enumerate(as_completed(futures), 1):
            try:
                aid, ok, status = fut.result()
                if ok:
                    if status == "generated":
                        generated += 1
                    else:
                        cached += 1
                else:
                    failed += 1
            except Exception:
                failed += 1

            if idx % 1000 == 0 or idx == total_tasks:
                elapsed = time.time() - t0
                rate = idx / elapsed if elapsed > 0 else 0
                remaining = (total_tasks - idx) / rate if rate > 0 else 0
                print(f"  Progress: {idx:,}/{total_tasks:,} ({idx*100/total_tasks:.1f}%) | "
                      f"Generated: {generated:,} | Failed: {failed:,} | "
                      f"Speed: {rate:.1f} img/s | ETA: {remaining/60:.1f}m")

    total_time = time.time() - t0
    print(f"\n[4/4] COMPLETE in {total_time:.1f} seconds!")
    print(f"  Total processed: {total_tasks:,}")
    print(f"  Generated: {generated:,}")
    print(f"  Failed / Unresolved: {failed:,}")
    print("=" * 80)

if __name__ == "__main__":
    main()

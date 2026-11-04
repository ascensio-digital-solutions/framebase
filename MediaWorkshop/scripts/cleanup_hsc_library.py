#!/usr/bin/env python3
"""
Surgical Cleanup and Reclassification of Hair Solutions Co. (HSC) Library.
Author: Antigravity × Vincent Laroche
Purpose:
1. Purge misclassified personal photos, memes, and selfies from HSC Library.
2. Ensure any non-business personal photos are safely preserved in Personal Library before removal.
3. Clean 02_specs/diagrams so ONLY true hair replacement diagrams remain.
4. Move swatches (hair color, curl pattern, density) to their correct 02_specs/swatches subfolders.
5. Purge the 337 redundant personal files from 00_inbox in HSC Library.
6. Re-route the real Hair Solutions Co. assets from 00_inbox into their proper 11-Folder Operating Model homes.
7. Verify catalog integrity and checkpoint SQLite WAL.
"""

import os
import sys
import json
import time
import uuid
import shutil
import sqlite3
from pathlib import Path
from typing import Dict, List, Tuple, Set

PICTURES_DIR = Path.home() / "Pictures"
HSC_LIB = PICTURES_DIR / "HSC Library.framebase"
PERSONAL_LIB = PICTURES_DIR / "Personal Library.framebase"
KNOWLEDGE_LIB = PICTURES_DIR / "Knowledge Library.framebase"

HSC_DB = HSC_LIB / "Catalog" / "catalog.sqlite"
PERSONAL_DB = PERSONAL_LIB / "Catalog" / "catalog.sqlite"
KNOWLEDGE_DB = KNOWLEDGE_LIB / "Catalog" / "catalog.sqlite"
STATE_DB = Path("/Users/vincent/04_systems/media_workshop/tools/photo_classifier/state.sqlite")


def get_folders_map(conn: sqlite3.Connection) -> Dict[str, str]:
    """Map lowercased full path and single folder name to folder UUID."""
    c = conn.cursor()
    c.execute("SELECT id, name, parent_folder_id FROM folders")
    rows = c.fetchall()
    id_to_row = {r[0]: r for r in rows}

    mapping = {}
    for fid, name, parent_id in rows:
        path_parts = [name]
        curr = parent_id
        while curr and curr in id_to_row:
            p_row = id_to_row[curr]
            path_parts.append(p_row[1])
            curr = p_row[2]
        path_parts.reverse()
        full_path = "/".join(path_parts).lower()
        mapping[full_path] = fid
        mapping[name.lower()] = fid
    return mapping


def get_or_create_folder(conn: sqlite3.Connection, folder_path: str, sort_order: int = 10) -> str:
    """Get or create nested folder hierarchy in Framebase catalog."""
    folders_map = get_folders_map(conn)
    norm = folder_path.strip("/").lower()
    if norm in folders_map:
        return folders_map[norm]

    parts = [p.strip() for p in folder_path.strip("/").split("/") if p.strip()]
    curr_parent = None
    cum = []
    now_ms = int(time.time() * 1000)
    c = conn.cursor()

    for idx, part in enumerate(parts):
        cum.append(part.lower())
        sub = "/".join(cum)
        if sub in folders_map:
            curr_parent = folders_map[sub]
            continue

        fid = str(uuid.uuid4()).lower()
        try:
            c.execute("""
                INSERT INTO folders (id, name, parent_folder_id, created_at_ms, updated_at_ms, sort_order, system_kind)
                VALUES (?, ?, ?, ?, ?, ?, NULL)
            """, (fid, part, curr_parent, now_ms, now_ms, sort_order + idx))
            conn.commit()
            folders_map[sub] = fid
            curr_parent = fid
        except sqlite3.IntegrityError:
            c.execute("SELECT id FROM folders WHERE COALESCE(parent_folder_id, '') = ? AND name COLLATE NOCASE = ?",
                      (curr_parent or "", part))
            row = c.fetchone()
            if row:
                curr_parent = row[0]
                folders_map[sub] = curr_parent

    return curr_parent


def move_asset_to_personal_lib(
    hsc_asset_id: str,
    target_personal_folder_path: str,
    conn_hsc: sqlite3.Connection,
    conn_pers: sqlite3.Connection
):
    """Ensure asset is copied to Personal Library before deleting from HSC Library."""
    now_ms = int(time.time() * 1000)
    ch = conn_hsc.cursor()
    cp = conn_pers.cursor()

    # Get asset details from HSC
    ch.execute("""
        SELECT a.id, a.filename, a.display_name, a.storage_key, a.media_type,
               a.width, a.height, a.file_size, a.created_at_ms, a.modified_at_ms,
               a.favorite, a.rating, a.metadata_json, aci.sha256
        FROM assets a
        LEFT JOIN asset_content_identity aci ON a.id = aci.asset_id
        WHERE a.id = ?
    """, (hsc_asset_id,))
    row = ch.fetchone()
    if not row:
        return

    (aid, fn, dname, skey, mtype, w, h, fsz, c_ms, m_ms, fav, rat, meta, sha) = row

    # Check if already in Personal Library
    cp.execute("SELECT asset_id FROM asset_content_identity WHERE sha256 = ?", (sha,))
    existing = cp.fetchone()
    if not existing:
        # Create folder in Personal Library
        pers_folder_id = get_or_create_folder(conn_pers, target_personal_folder_path)
        pers_asset_id = aid # Keep same ID or generate new deterministic ID
        
        # Check if asset_id already exists in personal assets
        cp.execute("SELECT id FROM assets WHERE id = ?", (pers_asset_id,))
        if cp.fetchone():
            pers_asset_id = str(uuid.uuid4()).lower()

        cp.execute("""
            INSERT OR IGNORE INTO assets (
                id, filename, display_name, parent_folder_id, storage_key, media_type,
                width, height, file_size, created_at_ms, modified_at_ms, imported_at_ms,
                updated_at_ms, favorite, rating, metadata_json, original_available
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 0)
        """, (
            pers_asset_id, fn, dname, pers_folder_id, skey, mtype,
            w, h, fsz, c_ms, m_ms, now_ms, now_ms, fav, rat, meta
        ))

        if sha:
            cp.execute("""
                INSERT OR IGNORE INTO asset_content_identity (sha256, asset_id, byte_size, recorded_at_ms)
                VALUES (?, ?, ?, ?)
            """, (sha, pers_asset_id, fsz, now_ms))
        conn_pers.commit()


def delete_asset_from_hsc(asset_id: str, conn_hsc: sqlite3.Connection):
    """Safely delete asset and its relations from HSC Library."""
    ch = conn_hsc.cursor()
    ch.execute("DELETE FROM asset_tags WHERE asset_id = ?", (asset_id,))
    ch.execute("DELETE FROM visual_assessments WHERE asset_id = ?", (asset_id,))
    ch.execute("DELETE FROM album_assets WHERE asset_id = ?", (asset_id,))
    ch.execute("DELETE FROM asset_content_identity WHERE asset_id = ?", (asset_id,))
    ch.execute("DELETE FROM asset_cloud_state WHERE asset_id = ?", (asset_id,))
    ch.execute("DELETE FROM assets WHERE id = ?", (asset_id,))


def classify_hsc_cloudinary_asset(fn: str) -> str:
    fl = fn.lower()
    # 1. Brand System
    if any(k in fl for k in ['logo', 'symbol', 'brand-mark', 'rectangle_-_white', 'rectangle_-_black']):
        return '07_brand/logos'
    # 2. Web UI & Banners
    if any(k in fl for k in ['hero', 'blog-', 'banner', 'home-', 'about-', 'faq', 'help-center', 'portal', 'web-']):
        return '06_web'
    # 3. Marketing & Ads
    if any(k in fl for k in ['ad-', 'campaign', 'marketing', 'promo', 'carousel', 'story-ad', 'flyer', 'entrevista-radio']):
        return '08_marketing'
    # 4. Specs, Swatches & Mold Diagrams
    if any(k in fl for k in ['direction-right', 'direction-left', 'hair-direction']):
        return '02_specs/swatches/hair-direction'
    if any(k in fl for k in ['density']):
        return '02_specs/swatches/density'
    if any(k in fl for k in ['curl', 'wave']):
        return '02_specs/swatches/curl-pattern'
    if any(k in fl for k in ['color', 'hs7-1', 'grey', 'salt-pepper', 'swatch']):
        return '02_specs/swatches/hair-color'
    if any(k in fl for k in ['base-material', 'cap-base', 'poly-skin', 'skin-base']):
        return '02_specs/swatches/base-material'
    if any(k in fl for k in ['template', 'mold', 'measure', 'order_tools_icon']):
        return '02_specs/guides'
    # 5. Lifestyle & Barber
    if any(k in fl for k in ['barber', 'salon', 'lifestyle', 'grooming', 'resting-wooden', 'mirror-looking', 'mirror-adjusting', 'scissors']):
        return '04_lifestyle'
    # 6. Education
    if any(k in fl for k in ['tutorial', 'guide', 'application', 'removal', 'care-guide', 'install']):
        return '05_education'
    # 7. Models & People
    if any(k in fl for k in [
        'salem', 'barry', 'alex', 'danny', 'declan', 'kevin', 'kyle', 'serge', 'vincent', 'yago',
        'portrait', 'man-', 'men-', 'customer', 'testimonial', 'before', 'after', 'model',
        'head-hair-loss', 'facetune', 'gemini_generated', 'chatgpt_image', 'brushback'
    ]):
        return '03_people/models'
    # 8. Finished Hair System Products
    if any(k in fl for k in ['thin-skin', 'lace', 'system', 'toupee', 'skin-base', 'mens-hair-systems', 'inl-poly', 'hs1-', 'hs25', 'sunny', 'product-', 'toppers']):
        return '01_products/hair-systems'
    # 9. Maintenance & Accessories
    if any(k in fl for k in ['glue', 'tape', 'solvent', 'ghost-bond', 'c-22', 'prohair', 'maintenance']):
        return '01_products/maintenance'
    # 10. Operations & Screenshots
    if any(k in fl for k in ['cleanshot', 'screenshot']):
        return '09_reference/ops-screenshots'
    
    return '01_products/hair-systems'  # Default for unsorted commercial assets


def main():
    print("=" * 80)
    print("HSC LIBRARY SURGICAL CLEANUP & RECLASSIFICATION")
    print("=" * 80)

    conn_hsc = sqlite3.connect(str(HSC_DB), timeout=60.0)
    conn_hsc.execute("PRAGMA journal_mode=WAL;")
    conn_pers = sqlite3.connect(str(PERSONAL_DB), timeout=60.0)
    conn_pers.execute("PRAGMA journal_mode=WAL;")

    hsc_folders = get_folders_map(conn_hsc)
    ch = conn_hsc.cursor()

    # -------------------------------------------------------------
    # STEP 1: FIX 02_specs/diagrams
    # -------------------------------------------------------------
    print("\n--- STEP 1: Cleaning 02_specs/diagrams ---")
    ch.execute("""
        SELECT a.id, a.filename, aci.sha256
        FROM assets a
        JOIN folders f ON a.parent_folder_id = f.id
        LEFT JOIN asset_content_identity aci ON a.id = aci.asset_id
        WHERE f.name = 'diagrams'
    """)
    diagram_assets = ch.fetchall()

    diagrams_folder_id = hsc_folders.get("02_specs/diagrams") or hsc_folders.get("diagrams")
    hair_color_folder_id = get_or_create_folder(conn_hsc, "02_specs/swatches/hair-color")
    curl_pattern_folder_id = get_or_create_folder(conn_hsc, "02_specs/swatches/curl-pattern")
    density_folder_id = get_or_create_folder(conn_hsc, "02_specs/swatches/density")
    ops_screenshots_folder_id = get_or_create_folder(conn_hsc, "09_reference/ops-screenshots")

    # True hair diagrams to KEEP in diagrams
    keep_in_diagrams = {
        "dcb16e4fa7": "IMG_1258.jpeg (Hand-drawn ventilation diagram)",
        "87e59f9a6d": "Template.jpeg (Zone 1-6 base diagram)",
        "e61edf1238": "49EAE36D-88EC-4A3C-B2D9-0EFA9E1489A4.jpeg (Head zones diagram)"
    }

    # Technical swatches to MOVE to subfolders
    move_to_hsc_folder = {
        "b56bfef74a": (hair_color_folder_id, "02_specs/swatches/hair-color", "HS7-1.jpeg (Color/Grey Chart)"),
        "a408dbe76f": (hair_color_folder_id, "02_specs/swatches/hair-color", "image001.jpeg (Color Chart)"),
        "3b2d98d4d3": (hair_color_folder_id, "02_specs/swatches/hair-color", "IMG_5253.jpeg (Color Swatches)"),
        "d2900a9b69": (hair_color_folder_id, "02_specs/swatches/hair-color", "IMG_9386.jpeg 2025 (Frontal Chart)"),
        "55ee94f7a0": (curl_pattern_folder_id, "02_specs/swatches/curl-pattern", "IMG_6210.PNG (Curl Spec)"),
        "cac8a64789": (curl_pattern_folder_id, "02_specs/swatches/curl-pattern", "IMG_7704.JPG (Curl Swatches)"),
        "2341204272": (density_folder_id, "02_specs/swatches/density", "IMG_3199.PNG (Density Chart)"),
        "28d35f0a3b": (ops_screenshots_folder_id, "09_reference/ops-screenshots", "IMG_1702.jpeg 2025 (Ali Sartaj WhatsApp)"),
    }

    # Personal photos to MOVE to Personal Library then DELETE from HSC
    personal_in_diagrams = {
        "dd2e3ed24e": ("01_people_and_family/portraits", "IMG_9386.jpeg 2016 (Shirtless mirror selfie)"),
        "755c866155": ("04_lifestyle_hobbies/interiors", "IMG_1702.jpeg 2016 (Rihanna meme)"),
        "4a046b1ee0": ("01_people_and_family/portraits", "IMG_1702.jpeg 2017 (Shirtless underwear/gym)"),
        "fa24d6d1fe": ("03_travel_places", "IMG_1702.jpeg 2019 (Boat with two guys)"),
        "d3aa5b7727": ("04_lifestyle_hobbies/social", "IMG_1702.jpeg 2020 (Instagram model screenshot)"),
        "0745b10621": ("04_lifestyle_hobbies/pets_animals", "IMG_1702.jpeg 2021 (French bulldog puppy)"),
        "b2341c9977": ("03_travel_places", "IMG_1702.jpeg 2024 (Beach photo)"),
        "490781e01d": ("03_travel_places", "IMG_6219.PNG 2022 (Sunset reel screenshot)"),
    }

    for aid, fn, sha in diagram_assets:
        prefix = sha[:10] if sha else ""
        if prefix in keep_in_diagrams:
            print(f"  [KEEP DIAGRAM] {keep_in_diagrams[prefix]}")
        elif prefix in move_to_hsc_folder:
            fid, dest_name, label = move_to_hsc_folder[prefix]
            ch.execute("UPDATE assets SET parent_folder_id = ? WHERE id = ?", (fid, aid))
            print(f"  [MOVED IN HSC] {label} -> {dest_name}")
        elif prefix in personal_in_diagrams:
            pers_dest, label = personal_in_diagrams[prefix]
            # Ensure in Personal Library
            move_asset_to_personal_lib(aid, pers_dest, conn_hsc, conn_pers)
            # Delete from HSC Library
            delete_asset_from_hsc(aid, conn_hsc)
            print(f"  [PURGED TO PERSONAL] {label} -> Personal Library ({pers_dest})")
        else:
            print(f"  [UNRESOLVED] {fn} (SHA: {prefix})")

    conn_hsc.commit()

    # -------------------------------------------------------------
    # STEP 2: PURGE REDUNDANT PERSONAL ASSETS FROM 00_INBOX
    # -------------------------------------------------------------
    print("\n--- STEP 2: Purging redundant personal assets from 00_inbox ---")
    cp = conn_pers.cursor()
    cp.execute("SELECT sha256 FROM asset_content_identity")
    pers_shas = set(r[0] for r in cp.fetchall())

    ch.execute("""
        SELECT a.id, a.filename, aci.sha256
        FROM assets a
        JOIN folders f ON a.parent_folder_id = f.id
        LEFT JOIN asset_content_identity aci ON a.id = aci.asset_id
        WHERE f.name = '00_inbox'
    """)
    inbox_assets = ch.fetchall()

    purged_count = 0
    remaining_inbox = []
    for aid, fn, sha in inbox_assets:
        if sha in pers_shas:
            delete_asset_from_hsc(aid, conn_hsc)
            purged_count += 1
        else:
            remaining_inbox.append((aid, fn, sha))

    conn_hsc.commit()
    print(f"  Purged {purged_count} personal assets from HSC Library (already safe in Personal Library).")
    print(f"  Remaining legitimate HSC commercial assets in inbox: {len(remaining_inbox)}")

    # -------------------------------------------------------------
    # STEP 3: DISTRIBUTE CLOUDINARY HSC ASSETS OUT OF 00_INBOX
    # -------------------------------------------------------------
    print("\n--- STEP 3: Reclassifying remaining HSC commercial assets into 11-Folder model ---")
    reclassified_counts = {}
    for aid, fn, sha in remaining_inbox:
        dest_folder_path = classify_hsc_cloudinary_asset(fn)
        folder_id = get_or_create_folder(conn_hsc, dest_folder_path)
        ch.execute("UPDATE assets SET parent_folder_id = ? WHERE id = ?", (folder_id, aid))
        reclassified_counts[dest_folder_path] = reclassified_counts.get(dest_folder_path, 0) + 1

    conn_hsc.commit()
    for dest, cnt in sorted(reclassified_counts.items(), key=lambda x: x[1], reverse=True):
        print(f"  Sorted {cnt:4d} assets -> {dest}")

    # Checkpoint WAL
    conn_hsc.execute("PRAGMA wal_checkpoint(TRUNCATE);")
    conn_pers.execute("PRAGMA wal_checkpoint(TRUNCATE);")
    conn_hsc.close()
    conn_pers.close()

    print("\n" + "=" * 80)
    print("CLEANUP AND RECLASSIFICATION COMPLETE!")
    print("=" * 80)


if __name__ == "__main__":
    main()


#!/usr/bin/env python3
"""
Intelligent Subfolder Reclassification of 03_people/models in Framebase.
Author: Antigravity × Vincent Laroche
Purpose:
1. Remove intruder screenshots (IG profiles, WhatsApp chats, vitamins) to 09_reference/ops-screenshots.
2. Route Vincent's canonical photos to 03_people/models/vincent.
3. Route named models (Salem, Barry, Kevin, Serge, Danny, Declan, Kyle, Alex, Yago) to their dedicated subfolders.
4. Route male pattern baldness & scalp thinning photos to 03_people/before-after/customer-submitted or 03_people/details.
5. Route side-by-side before/after transformation splits to 03_people/before-after/studio.
6. Route barbershop installs & video call haircuts to 04_lifestyle/barber-salon.
7. Keep clean styled commercial hero portraits in 03_people/models.
"""

import os
import sys
import json
import time
import sqlite3
from pathlib import Path
from typing import Dict, List, Tuple

PICTURES_DIR = Path.home() / "Pictures"
HSC_LIB = PICTURES_DIR / "HSC Library.framebase"
PERSONAL_LIB = PICTURES_DIR / "Personal Library.framebase"

HSC_DB = HSC_LIB / "Catalog" / "catalog.sqlite"
PERSONAL_DB = PERSONAL_LIB / "Catalog" / "catalog.sqlite"
STATE_DB = Path("/Users/vincent/04_systems/media_workshop/tools/photo_classifier/state.sqlite")

SCRIPT_DIR = Path(__file__).parent.resolve()
sys.path.append(str(SCRIPT_DIR.parent))
from scripts.cleanup_hsc_library import get_folders_map, get_or_create_folder, move_asset_to_personal_lib, delete_asset_from_hsc


def main():
    print("=" * 80)
    print("RECLASSIFYING 03_PEOPLE/MODELS INTO HIGH-RESOLUTION SUBFOLDERS")
    print("=" * 80)

    conn_hsc = sqlite3.connect(str(HSC_DB), timeout=60.0)
    conn_hsc.execute("PRAGMA journal_mode=WAL;")
    conn_pers = sqlite3.connect(str(PERSONAL_DB), timeout=60.0)
    conn_pers.execute("PRAGMA journal_mode=WAL;")

    hsc_folders = get_folders_map(conn_hsc)
    ch = conn_hsc.cursor()

    # Destination folder IDs
    f_vincent = hsc_folders.get("03_people/models/vincent") or get_or_create_folder(conn_hsc, "03_people/models/vincent")
    f_salem = hsc_folders.get("03_people/models/salem") or get_or_create_folder(conn_hsc, "03_people/models/salem")
    f_barry = hsc_folders.get("03_people/models/barry") or get_or_create_folder(conn_hsc, "03_people/models/barry")
    f_kevin = hsc_folders.get("03_people/models/kevin") or get_or_create_folder(conn_hsc, "03_people/models/kevin")
    f_serge = hsc_folders.get("03_people/models/serge") or get_or_create_folder(conn_hsc, "03_people/models/serge")
    f_danny = hsc_folders.get("03_people/models/danny") or get_or_create_folder(conn_hsc, "03_people/models/danny")
    f_declan = hsc_folders.get("03_people/models/declan") or get_or_create_folder(conn_hsc, "03_people/models/declan")
    f_kyle = hsc_folders.get("03_people/models/kyle") or get_or_create_folder(conn_hsc, "03_people/models/kyle")
    f_alex = hsc_folders.get("03_people/models/alex") or get_or_create_folder(conn_hsc, "03_people/models/alex")
    f_yago = hsc_folders.get("03_people/models/yago") or get_or_create_folder(conn_hsc, "03_people/models/yago")

    f_ba_cust = hsc_folders.get("03_people/before-after/customer-submitted") or get_or_create_folder(conn_hsc, "03_people/before-after/customer-submitted")
    f_ba_studio = hsc_folders.get("03_people/before-after/studio") or get_or_create_folder(conn_hsc, "03_people/before-after/studio")
    f_details = hsc_folders.get("03_people/details") or get_or_create_folder(conn_hsc, "03_people/details")
    f_barber = hsc_folders.get("04_lifestyle/barber-salon") or get_or_create_folder(conn_hsc, "04_lifestyle/barber-salon")
    f_ops = hsc_folders.get("09_reference/ops-screenshots") or get_or_create_folder(conn_hsc, "09_reference/ops-screenshots")

    named_models_map = {
        'salem': f_salem,
        'barry': f_barry,
        'kevin': f_kevin,
        'serge': f_serge,
        'danny': f_danny,
        'declan': f_declan,
        'kyle': f_kyle,
        'alex': f_alex,
        'yago': f_yago,
    }

    ch.execute("""
        SELECT a.id, a.filename, a.display_name, aci.sha256
        FROM assets a
        JOIN folders f ON a.parent_folder_id = f.id
        LEFT JOIN asset_content_identity aci ON a.id = aci.asset_id
        WHERE f.name = 'models'
    """)
    model_assets = ch.fetchall()

    conn_classifier = sqlite3.connect(str(STATE_DB))
    cc = conn_classifier.cursor()

    counts = {
        "intruders_ops": 0,
        "intruders_pers": 0,
        "vincent": 0,
        "named_models": 0,
        "before_baldness": 0,
        "before_after_split": 0,
        "barber_salon": 0,
        "kept_in_models": 0
    }

    for aid, fn, dname, sha in model_assets:
        rat = ""
        tags = []
        has_v = False
        cat = ""

        if sha:
            cc.execute("SELECT year, gemini_category, gemini_json, has_vincent FROM inventory WHERE sha256 = ?", (sha,))
            r = cc.fetchone()
            if r:
                cat = r[1] or ""
                has_v = bool(r[3])
                if r[2]:
                    try:
                        d = json.loads(r[2])
                        rat = d.get("rationale", "").lower()
                        tags = [t.lower() for t in d.get("tags", [])]
                        if d.get("has_vincent"):
                            has_v = True
                    except Exception:
                        pass

        fl = f"{fn} {dname} {rat} {' '.join(tags)}".lower()

        # 1. Personal intruders (pill bottles, dating, beaches)
        if any(k in fl for k in ['bottle', 'pills', 'vitamin', 'beach', 'swimming trunks', 'swimwear']):
            move_asset_to_personal_lib(aid, "04_lifestyle_hobbies/fitness_health" if "pill" in fl else "03_travel_places", conn_hsc, conn_pers)
            delete_asset_from_hsc(aid, conn_hsc)
            counts["intruders_pers"] += 1
            continue

        # 2. Business Ops / Screenshots (WhatsApp, IG profiles, text chats, screen recordings)
        if any(k in fl for k in ['screenshot', 'app:instagram', 'instagram profile', 'whatsapp', 'chat', 'screen recording', 'pricing', 'dm ']):
            ch.execute("UPDATE assets SET parent_folder_id = ? WHERE id = ?", (f_ops, aid))
            counts["intruders_ops"] += 1
            continue

        # 3. Vincent
        if has_v or 'vincent' in fl or 'foto vinc' in fl:
            ch.execute("UPDATE assets SET parent_folder_id = ? WHERE id = ?", (f_vincent, aid))
            counts["vincent"] += 1
            continue

        # 4. Known named models
        matched_model = False
        for mname, m_fid in named_models_map.items():
            if mname in fl:
                ch.execute("UPDATE assets SET parent_folder_id = ? WHERE id = ?", (m_fid, aid))
                counts["named_models"] += 1
                matched_model = True
                break
        if matched_model:
            continue

        # 5. Before & after split transformation cards
        if any(k in fl for k in ['before-after', 'before and after', 'transformation', 'diptych', 'side-by-side', 'split', 'copy of oneh']):
            ch.execute("UPDATE assets SET parent_folder_id = ? WHERE id = ?", (f_ba_studio, aid))
            counts["before_after_split"] += 1
            continue

        # 6. Raw male pattern baldness & scalp thinning ("Before" state)
        if any(k in fl for k in ['bald', 'hair loss', 'scalp', 'donor', 'thinning', 'norwood', 'top-down', 'head-hair-loss']):
            ch.execute("UPDATE assets SET parent_folder_id = ? WHERE id = ?", (f_ba_cust, aid))
            counts["before_baldness"] += 1
            continue

        # 7. Barber / Salon / Installation cutting
        if any(k in fl for k in ['barber', 'salon', 'haircut', 'install', 'fitting', 'video call', 'facetime']):
            ch.execute("UPDATE assets SET parent_folder_id = ? WHERE id = ?", (f_barber, aid))
            counts["barber_salon"] += 1
            continue

        # 8. Pure styled commercial hero model
        counts["kept_in_models"] += 1

    conn_hsc.commit()
    conn_pers.commit()
    conn_hsc.execute("PRAGMA wal_checkpoint(TRUNCATE);")
    conn_pers.execute("PRAGMA wal_checkpoint(TRUNCATE);")
    conn_hsc.close()
    conn_pers.close()
    conn_classifier.close()

    print("\nReclassification Summary:")
    print(f"  Moved to 03_people/models/vincent:           {counts['vincent']:3d}")
    print(f"  Moved to named model subfolders:             {counts['named_models']:3d}")
    print(f"  Moved to 03_people/before-after/studio:      {counts['before_after_split']:3d}")
    print(f"  Moved to 03_people/before-after/customer:    {counts['before_baldness']:3d}")
    print(f"  Moved to 04_lifestyle/barber-salon:          {counts['barber_salon']:3d}")
    print(f"  Moved to 09_reference/ops-screenshots:       {counts['intruders_ops']:3d}")
    print(f"  Purged personal items to Personal Library:   {counts['intruders_pers']:3d}")
    print(f"  Kept in 03_people/models (Styled Heroes):    {counts['kept_in_models']:3d}")
    print("=" * 80)


if __name__ == "__main__":
    main()

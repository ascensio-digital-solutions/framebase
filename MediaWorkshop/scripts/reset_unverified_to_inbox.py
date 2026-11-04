#!/usr/bin/env python3
"""
Track 1: Immediate Catalog Purification for HSC Library.framebase.

1. Purges all unscreened `source:google-drive-export` heuristic rows from catalog.sqlite
   (leaving local files on disk untouched).
2. Moves all remaining unverified catalog assets (those without a `gemini-3.8-flash`
   row in `visual_assessments`) to `00_inbox`.
3. Cross-checks verified assets in `03_people/models/*` and `08_marketing/*` against
   `MediaWorkshop/classifier/state.sqlite` to ensure domain is business/hair_solutions_co
   and privacy/sensitivity is safe/none.
4. Cleans up empty non-template heuristic folders and checkpoints the SQLite WAL.
"""

import json
import sqlite3
import time
from pathlib import Path

CATALOG_DB = Path.home() / "Pictures/HSC Library.framebase/Catalog/catalog.sqlite"
STATE_DB = Path("/Users/vincent/06_code/framebase/MediaWorkshop/classifier/state.sqlite")


def build_folder_paths(cursor: sqlite3.Cursor) -> dict[str, str]:
    cursor.execute("SELECT id, name, parent_folder_id FROM folders")
    rows = cursor.fetchall()
    id_to_row = {r[0]: r for r in rows}
    id_to_path = {}
    for fid, name, parent_id in rows:
        parts = [name]
        curr = parent_id
        while curr and curr in id_to_row:
            p_row = id_to_row[curr]
            parts.append(p_row[1])
            curr = p_row[2]
        parts.reverse()
        id_to_path[fid] = "/".join(parts)
    return id_to_path


def main() -> None:
    print(f"Connecting to {CATALOG_DB}...")
    conn = sqlite3.connect(str(CATALOG_DB), timeout=60.0)
    conn.execute("PRAGMA busy_timeout=60000;")
    conn.execute("PRAGMA foreign_keys=ON;")
    c = conn.cursor()

    total_before = c.execute("SELECT COUNT(*) FROM assets").fetchone()[0]
    print(f"Total assets before purification: {total_before}")

    # -------------------------------------------------------------------------
    # Step A: Purge the 12,302 unscreened `source:google-drive-export` rows
    # -------------------------------------------------------------------------
    c.execute(
        """
        SELECT DISTINCT at.asset_id
        FROM asset_tags at
        JOIN tags t ON at.tag_id = t.id
        WHERE t.name = 'source:google-drive-export'
          AND at.asset_id NOT IN (
              SELECT asset_id FROM visual_assessments WHERE model_identifier = 'gemini-3.8-flash'
          )
        """
    )
    purge_ids = [r[0] for r in c.fetchall()]
    print(f"Step A: Found {len(purge_ids)} unscreened 'source:google-drive-export' assets to purge.")

    if purge_ids:
        c.execute("CREATE TEMP TABLE purge_targets (asset_id TEXT PRIMARY KEY)")
        c.executemany("INSERT INTO purge_targets (asset_id) VALUES (?)", [(aid,) for aid in purge_ids])

        # Delete from all dependent tables (explicitly + CASCADE)
        c.execute(
            """
            DELETE FROM analysis_text_lines
            WHERE result_id IN (
                SELECT id FROM analysis_results WHERE asset_id IN (SELECT asset_id FROM purge_targets)
            )
            """
        )
        c.execute("DELETE FROM analysis_results WHERE asset_id IN (SELECT asset_id FROM purge_targets)")
        c.execute(
            """
            DELETE FROM visual_assessment_feedback_events
            WHERE assessment_id IN (
                SELECT id FROM visual_assessments WHERE asset_id IN (SELECT asset_id FROM purge_targets)
            )
            """
        )
        c.execute("DELETE FROM visual_assessment_reviews WHERE asset_id IN (SELECT asset_id FROM purge_targets)")
        c.execute("DELETE FROM visual_assessments WHERE asset_id IN (SELECT asset_id FROM purge_targets)")
        c.execute("DELETE FROM asset_tags WHERE asset_id IN (SELECT asset_id FROM purge_targets)")
        c.execute("DELETE FROM album_assets WHERE asset_id IN (SELECT asset_id FROM purge_targets)")
        c.execute("DELETE FROM asset_cloud_state WHERE asset_id IN (SELECT asset_id FROM purge_targets)")
        c.execute("DELETE FROM asset_trash WHERE asset_id IN (SELECT asset_id FROM purge_targets)")
        c.execute(
            """
            DELETE FROM before_after_relationships
            WHERE before_asset_id IN (SELECT asset_id FROM purge_targets)
               OR after_asset_id IN (SELECT asset_id FROM purge_targets)
            """
        )
        c.execute("DELETE FROM migration_manifest WHERE asset_id IN (SELECT asset_id FROM purge_targets)")
        c.execute("DELETE FROM asset_content_identity WHERE asset_id IN (SELECT asset_id FROM purge_targets)")
        c.execute("DELETE FROM assets WHERE id IN (SELECT asset_id FROM purge_targets)")
        c.execute("DROP TABLE purge_targets")

    # Clean up any orphaned asset_content_identity rows
    c.execute("DELETE FROM asset_content_identity WHERE asset_id NOT IN (SELECT id FROM assets)")
    print(f"Step A complete. Remaining assets in catalog: {c.execute('SELECT COUNT(*) FROM assets').fetchone()[0]}")

    # -------------------------------------------------------------------------
    # Step B: Move all remaining unverified catalog items to `00_inbox`
    # -------------------------------------------------------------------------
    inbox_row = c.execute("SELECT id FROM folders WHERE name = '00_inbox'").fetchone()
    if not inbox_row:
        raise RuntimeError("Could not find '00_inbox' folder in folders table!")
    inbox_id = inbox_row[0]
    now_ms = int(time.time() * 1000)

    c.execute(
        """
        UPDATE assets
        SET parent_folder_id = ?, updated_at_ms = ?
        WHERE id NOT IN (
            SELECT asset_id FROM visual_assessments WHERE model_identifier = 'gemini-3.8-flash'
        )
        """,
        (inbox_id, now_ms),
    )
    moved_unverified = c.rowcount
    print(f"Step B1: Moved {moved_unverified} unverified assets to '00_inbox' ({inbox_id}).")

    # Cross-check verified assets in 03_people/models/* or 08_marketing/* against state.sqlite
    id_to_path = build_folder_paths(c)
    flagged_verified_ids = []
    if STATE_DB.exists():
        sconn = sqlite3.connect(str(STATE_DB))
        sc = sconn.cursor()
        c.execute(
            """
            SELECT a.id, a.filename, a.parent_folder_id, aci.sha256
            FROM assets a
            JOIN visual_assessments va ON a.id = va.asset_id
            LEFT JOIN asset_content_identity aci ON a.id = aci.asset_id
            WHERE va.model_identifier = 'gemini-3.8-flash'
            """
        )
        for aid, fn, fid, sha in c.fetchall():
            fpath = id_to_path.get(fid, "")
            if fpath.startswith("03_people/models") or fpath.startswith("08_marketing"):
                srow = None
                if sha:
                    srow = sc.execute(
                        "SELECT final_domain, gemini_json, qwen_json, local_only FROM inventory WHERE sha256 = ?",
                        (sha,),
                    ).fetchone()
                if not srow:
                    srow = sc.execute(
                        "SELECT final_domain, gemini_json, qwen_json, local_only FROM inventory WHERE filename = ?",
                        (fn,),
                    ).fetchone()
                if srow:
                    gjson = json.loads(srow[1]) if srow[1] else {}
                    qjson = json.loads(srow[2]) if srow[2] else {}
                    dom = srow[0] or gjson.get("domain") or qjson.get("domain")
                    sens = (
                        gjson.get("privacy_flag")
                        or gjson.get("sensitivity")
                        or qjson.get("privacy_flag")
                        or qjson.get("sensitivity")
                    )
                    if (
                        dom not in ("business", "hair_solutions_co", None)
                        or sens not in ("safe", "none", None)
                        or bool(srow[3])
                    ):
                        flagged_verified_ids.append(aid)
        sconn.close()

    if flagged_verified_ids:
        c.executemany(
            "UPDATE assets SET parent_folder_id = ?, updated_at_ms = ? WHERE id = ?",
            [(inbox_id, now_ms, aid) for aid in flagged_verified_ids],
        )
    print(f"Step B2: Moved {len(flagged_verified_ids)} flagged verified assets in models/marketing to '00_inbox'.")

    # -------------------------------------------------------------------------
    # Step C: Clean up empty non-template heuristic folders & checkpoint WAL
    # -------------------------------------------------------------------------
    # Non-template heuristic folders were created with sort_order = 10 after initial template creation (1793178936481)
    c.execute(
        """
        DELETE FROM folders
        WHERE created_at_ms > 1793178936481
          AND id NOT IN (SELECT DISTINCT parent_folder_id FROM assets)
          AND id NOT IN (SELECT DISTINCT parent_folder_id FROM folders WHERE parent_folder_id IS NOT NULL)
        """
    )
    deleted_folders = c.rowcount
    print(f"Step C: Deleted {deleted_folders} empty non-template heuristic folders.")

    # Remove unused `source:google-drive-export` tag if no assets reference it
    c.execute(
        """
        DELETE FROM tags
        WHERE name = 'source:google-drive-export'
          AND id NOT IN (SELECT DISTINCT tag_id FROM asset_tags)
        """
    )

    conn.commit()
    print("Checkpointing SQLite WAL (TRUNCATE)...")
    conn.execute("PRAGMA wal_checkpoint(TRUNCATE);")
    conn.close()
    print("Purification complete.")


if __name__ == "__main__":
    main()

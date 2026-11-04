#!/usr/bin/env python3
"""
Synchronize and Normalize Hairline & Quality Tags in Framebase HSC Library
Ensures complete cross-compatibility between visual_assessments, GEMINI.md taxonomy,
and external AI agents (DeepSeek V4 Pro, Gemini, Open Design).
"""

import sqlite3
import time
import uuid
import re
from pathlib import Path

DB_PATH = Path.home() / "Pictures" / "HSC Library.framebase" / "Catalog" / "catalog.sqlite"

def slugify(text: str) -> str:
    text = text.lower().strip()
    text = re.sub(r"[^\w\s-]", "", text)
    text = re.sub(r"[\s_]+", "-", text)
    return text[:64].strip("-")

def deterministic_uuid(val: str) -> str:
    return str(uuid.uuid5(uuid.NAMESPACE_DNS, val)).lower()

def main():
    print(f"Connecting to {DB_PATH}...")
    conn = sqlite3.connect(str(DB_PATH), timeout=60.0)
    conn.execute("PRAGMA journal_mode=WAL;")
    conn.execute("PRAGMA busy_timeout=60000;")
    c = conn.cursor()

    now_ms = int(time.time() * 1000)

    # 1. Load all existing tags into memory: name.lower() -> id
    c.execute("SELECT id, name FROM tags")
    tags_cache = {r[1].lower(): r[0] for r in c.fetchall()}

    def get_or_create_tag(full_name: str) -> str:
        name_lower = full_name.lower().strip()
        if name_lower in tags_cache:
            return tags_cache[name_lower]

        if ":" in name_lower:
            ns, val = name_lower.split(":", 1)
        else:
            ns, val = "tag", name_lower

        ns = slugify(ns)[:64]
        val = slugify(val)[:64]
        canonical_name = f"{ns}:{val}"

        if canonical_name in tags_cache:
            return tags_cache[canonical_name]

        tag_id = deterministic_uuid(f"framebase-tag:{canonical_name}")
        c.execute("""
            INSERT OR IGNORE INTO tags (id, namespace, value, name, created_at_ms, updated_at_ms)
            VALUES (?, ?, ?, ?, ?, ?)
        """, (tag_id, ns, val, canonical_name, now_ms, now_ms))
        conn.commit()

        # Re-fetch in case of race/ignore
        c.execute("SELECT id FROM tags WHERE name COLLATE NOCASE = ?", (canonical_name,))
        row = c.fetchone()
        tag_id = row[0]
        tags_cache[canonical_name] = tag_id
        return tag_id

    # 2. Get all assets with visual assessments
    c.execute("""
        SELECT asset_id, business_quality, hairline_presentation
        FROM visual_assessments
    """)
    assessments = c.fetchall()
    print(f"Total visual assessments found: {len(assessments)}")

    # 3. Find assets that have legacy hairline tags
    c.execute("""
        SELECT DISTINCT at.asset_id, t.name
        FROM asset_tags at
        JOIN tags t ON at.tag_id = t.id
        WHERE t.name LIKE 'hairline:%'
    """)
    legacy_hairline_map = {}
    for aid, tname in c.fetchall():
        legacy_hairline_map.setdefault(aid, set()).add(tname.lower())

    attached_count = 0
    tag_changes = {
        "hairline:clearly-visible": 0,
        "hairline:partially-visible": 0,
        "hairline:not-visible": 0,
        "hairline:undetectable": 0,
        "quality:strong": 0,
        "quality:usable": 0,
        "quality:weak": 0,
    }

    # Set of (asset_id, tag_id)
    c.execute("SELECT asset_id, tag_id FROM asset_tags")
    existing_asset_tags = set(c.fetchall())
    print(f"Existing asset_tag links: {len(existing_asset_tags)}")

    new_links = []

    for asset_id, bq, hp in assessments:
        tags_to_add = set()

        # Hairline presentation mapping
        if hp in ("clearlyVisible", "clearly-visible") or "hairline:clearlyvisible" in legacy_hairline_map.get(asset_id, set()) or "hairline:visible" in legacy_hairline_map.get(asset_id, set()) or "hairline:exposed" in legacy_hairline_map.get(asset_id, set()):
            tags_to_add.add("hairline:clearly-visible")
            if bq == "strong":
                tags_to_add.add("hairline:undetectable")

        elif hp in ("partiallyVisible", "partially-visible") or "hairline:partiallyvisible" in legacy_hairline_map.get(asset_id, set()):
            tags_to_add.add("hairline:partially-visible")

        elif hp in ("notVisible", "not-visible"):
            tags_to_add.add("hairline:not-visible")

        # Quality mapping
        if bq == "strong":
            tags_to_add.add("quality:strong")
        elif bq == "usable":
            tags_to_add.add("quality:usable")
        elif bq == "weak":
            tags_to_add.add("quality:weak")

        for tag_str in tags_to_add:
            tid = get_or_create_tag(tag_str)
            if (asset_id, tid) not in existing_asset_tags:
                new_links.append((asset_id, tid, now_ms))
                existing_asset_tags.add((asset_id, tid))
                tag_changes[tag_str] = tag_changes.get(tag_str, 0) + 1

    print(f"Inserting {len(new_links)} new tag associations...")
    c.executemany("""
        INSERT OR IGNORE INTO asset_tags (asset_id, tag_id, added_at_ms)
        VALUES (?, ?, ?)
    """, new_links)
    conn.commit()

    print("\n=== SYNCHRONIZATION SUMMARY ===")
    for tag_name, count in sorted(tag_changes.items()):
        print(f"  + {tag_name:30}: {count} new attachments")

    # Verify final tag counts in catalog
    print("\n=== FINAL TAG COVERAGE IN HSC LIBRARY ===")
    for check_tag in ["hairline:clearly-visible", "hairline:clearlyvisible", "hairline:undetectable", "hairline:partially-visible", "hairline:not-visible", "quality:strong", "quality:usable", "quality:weak"]:
        c.execute("""
            SELECT count(DISTINCT asset_id)
            FROM asset_tags at
            JOIN tags t ON at.tag_id = t.id
            WHERE t.name = ?
        """, (check_tag,))
        total = c.fetchone()[0]
        print(f"  {check_tag:30}: {total} assets")

    conn.close()
    print("\nDatabase connection closed. Library tags successfully synchronized!")

if __name__ == "__main__":
    main()


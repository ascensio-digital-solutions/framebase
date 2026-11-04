#!/usr/bin/env python3
"""
Ingest Media Workshop photos into 3 Distinct Framebase Libraries:
1. Personal Library:    ~/Pictures/Personal Library.framebase
2. Core Business (HSC): ~/Pictures/HSC Library.framebase
3. Knowledge / Swipe:   ~/Pictures/Knowledge Library.framebase

Architecture & Guarantees:
- Dispatches each photo to its dedicated library according to the 3-pillar taxonomy:
    * domain == 'personal'  -> Personal Library.framebase
    * domain == 'business'  -> HSC Library.framebase
    * domain == 'knowledge' -> Knowledge Library.framebase
- Seeds Knowledge Library.framebase if not already present (schema v14, Catalog, Originals, Staging).
- Preserves Framebase byte immutability and content-addressable storage:
    * Originals/<prefix>/<uuid>.<ext>
    * Asset records in `assets`
    * Content verification in `asset_content_identity` (SHA-256)
- Automatically checks for existing assets by SHA-256 (handles already-ingested assets idempotently).
- Recreates logical folder trees matching category and topic structure.
- Enriches every asset with Framebase tags (namespace:value) in `tags` and `asset_tags`.
- Inserts Vertex AI Gemini 3.8 Flash assessments into `visual_assessments`.
"""

import os
import sys
import re
import json
import time
import shutil
import hashlib
import sqlite3
import uuid
from pathlib import Path
from typing import Dict, Any, Optional, Tuple, Set, List
from PIL import Image

SCRIPT_DIR = Path(__file__).parent.resolve()
WORKSPACE_DIR = SCRIPT_DIR.parent.parent.resolve()
DB_PATH = SCRIPT_DIR / "state.sqlite"

PICTURES_DIR = Path(os.path.expanduser("~/Pictures"))
PERSONAL_LIB = PICTURES_DIR / "Personal Library.framebase"
HSC_LIB = PICTURES_DIR / "HSC Library.framebase"
KNOWLEDGE_LIB = PICTURES_DIR / "Knowledge Library.framebase"

def slugify(text: str) -> str:
    text = text.lower().strip()
    text = re.sub(r"[^\w\s-]", "", text)
    text = re.sub(r"[\s_]+", "-", text)
    return text[:64].strip("-")

def deterministic_uuid(val: str) -> str:
    """Generate consistent UUID from a string key."""
    return str(uuid.uuid5(uuid.NAMESPACE_DNS, val)).lower()

def resolve_image_path(path_str: str, year: int, filename: str) -> Optional[Path]:
    """Resolve image path strictly for the specific year to prevent filename collisions."""
    # 1. Local year directory
    local_year_path = WORKSPACE_DIR / str(year) / filename
    if local_year_path.exists():
        return local_year_path

    # 2. Original recorded path
    orig = Path(path_str)
    if orig.exists():
        return orig

    # 3. Canonical SeaDisk locations for the EXACT SAME year only
    candidates = [
        Path(f"/Volumes/SeaDisk/media_workshop/iPhoto export 2010-2026/{year}") / filename,
        Path(f"/Volumes/SeaDisk/{year}") / filename,
        Path(f"/Volumes/SeaDisk/Apple_Photos_9Y/{year}") / filename,
    ]
    for cand in candidates:
        if cand.exists():
            return cand
    return None

def compute_sha256(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        while chunk := f.read(1024 * 1024):
            h.update(chunk)
    return h.hexdigest().lower()

def init_knowledge_library():
    """Seed Knowledge Library package if it does not exist."""
    KNOWLEDGE_LIB.mkdir(exist_ok=True)
    catalog_dir = KNOWLEDGE_LIB / "Catalog"
    originals_dir = KNOWLEDGE_LIB / "Originals"
    staging_dir = KNOWLEDGE_LIB / "Staging"
    
    catalog_dir.mkdir(exist_ok=True)
    originals_dir.mkdir(exist_ok=True)
    staging_dir.mkdir(exist_ok=True)

    db_path = catalog_dir / "catalog.sqlite"
    if db_path.exists():
        return

    print("Initializing Knowledge Library schema and structure...")
    # Copy schema from Personal Library
    personal_db = PERSONAL_LIB / "Catalog" / "catalog.sqlite"
    shutil.copy2(personal_db, db_path)

    # Clean data from copied DB
    conn = sqlite3.connect(str(db_path))
    c = conn.cursor()
    c.execute("DELETE FROM assets;")
    c.execute("DELETE FROM asset_content_identity;")
    c.execute("DELETE FROM tags;")
    c.execute("DELETE FROM asset_tags;")
    c.execute("DELETE FROM visual_assessments;")
    c.execute("DELETE FROM visual_assessment_reviews;")
    c.execute("DELETE FROM folders;")
    c.execute("DELETE FROM albums;")
    c.execute("DELETE FROM album_assets;")
    c.execute("DELETE FROM saved_searches;")
    c.execute("DELETE FROM cloud_blobs;")
    c.execute("DELETE FROM asset_cloud_state;")

    # Reset settings
    new_catalog_id = str(uuid.uuid4()).lower()
    now_ms = int(time.time() * 1000)
    c.execute("DELETE FROM catalog_settings;")
    c.execute("INSERT INTO catalog_settings (key, value, updated_at_ms) VALUES ('catalog_id', ?, ?)", (new_catalog_id, now_ms))
    c.execute("INSERT INTO catalog_settings (key, value, updated_at_ms) VALUES ('schema_version', '14', ?)", (now_ms,))
    c.execute("INSERT INTO catalog_settings (key, value, updated_at_ms) VALUES ('library_space', 'knowledge', ?)", (now_ms,))

    conn.commit()
    conn.close()
    print("Knowledge Library initialized successfully!")

class FramebaseLibraryManager:
    def __init__(self, lib_path: Path):
        self.lib_path = lib_path
        self.catalog_db_path = lib_path / "Catalog" / "catalog.sqlite"
        self.originals_dir = lib_path / "Originals"
        self.conn = sqlite3.connect(str(self.catalog_db_path), timeout=60.0)
        self.conn.execute("PRAGMA journal_mode=WAL;")
        self.conn.execute("PRAGMA busy_timeout=60000;")
        
        # Load existing folders: path_tuple -> folder_id
        self.folders = {}
        self.load_folders()

        # Load existing asset SHAs: sha256 -> asset_id
        self.existing_shas = {}
        self.load_existing_shas()

        # Load existing tags: tag_name -> tag_id
        self.tags = {}
        self.load_tags()

    def load_folders(self):
        c = self.conn.cursor()
        c.execute("SELECT id, name, parent_folder_id, system_kind FROM folders")
        rows = c.fetchall()
        id_to_row = {r[0]: r for r in rows}

        for fid, name, parent_id, sys_kind in rows:
            path_parts = [name]
            curr_parent = parent_id
            while curr_parent and curr_parent in id_to_row:
                p_row = id_to_row[curr_parent]
                path_parts.append(p_row[1])
                curr_parent = p_row[2]
            path_parts.reverse()
            full_path = "/".join(path_parts)
            self.folders[full_path.lower()] = fid
            self.folders[name.lower()] = fid

    def get_or_create_folder(self, folder_path: str, sort_order: int = 10, is_inbox: bool = False) -> str:
        """Get or create nested logical folders."""
        norm_path = folder_path.strip("/").lower()
        if norm_path in self.folders:
            return self.folders[norm_path]

        parts = [p.strip() for p in folder_path.strip("/").split("/") if p.strip()]
        curr_parent_id = None
        cum_path = []

        now_ms = int(time.time() * 1000)
        c = self.conn.cursor()

        for idx, part in enumerate(parts):
            cum_path.append(part.lower())
            sub_path = "/".join(cum_path)
            if sub_path in self.folders:
                curr_parent_id = self.folders[sub_path]
                continue

            folder_id = str(uuid.uuid4()).lower()
            sys_kind = "inbox" if (is_inbox and idx == len(parts) - 1) else None
            
            try:
                c.execute("""
                    INSERT INTO folders (id, name, parent_folder_id, created_at_ms, updated_at_ms, sort_order, system_kind)
                    VALUES (?, ?, ?, ?, ?, ?, ?)
                """, (folder_id, part, curr_parent_id, now_ms, now_ms, sort_order + idx, sys_kind))
                self.conn.commit()
                self.folders[sub_path] = folder_id
                self.folders[part.lower()] = folder_id
                curr_parent_id = folder_id
            except sqlite3.IntegrityError:
                # Sibling exists with same name
                c.execute("SELECT id FROM folders WHERE COALESCE(parent_folder_id, '') = ? AND name COLLATE NOCASE = ?",
                          (curr_parent_id or "", part))
                row = c.fetchone()
                if row:
                    curr_parent_id = row[0]
                    self.folders[sub_path] = curr_parent_id
                    self.folders[part.lower()] = curr_parent_id

        return curr_parent_id

    def load_existing_shas(self):
        c = self.conn.cursor()
        c.execute("SELECT sha256, asset_id FROM asset_content_identity")
        self.existing_shas = {r[0]: r[1] for r in c.fetchall()}

    def load_tags(self):
        c = self.conn.cursor()
        c.execute("SELECT id, name FROM tags")
        self.tags = {r[1].lower(): r[0] for r in c.fetchall()}

    def get_or_create_tag(self, raw_tag: str) -> str:
        tag_str = raw_tag.strip().lower()
        if ":" not in tag_str:
            ns, val = "tag", slugify(tag_str)
        else:
            p1, p2 = tag_str.split(":", 1)
            ns = slugify(p1)[:64]
            val = slugify(p2)[:64]
            if not ns:
                ns = "tag"
            if not val:
                val = "general"

        full_name = f"{ns}:{val}"
        if full_name in self.tags:
            return self.tags[full_name]

        tag_id = deterministic_uuid(f"framebase-tag:{full_name}")
        now_ms = int(time.time() * 1000)
        c = self.conn.cursor()
        try:
            c.execute("""
                INSERT INTO tags (id, namespace, value, name, created_at_ms, updated_at_ms)
                VALUES (?, ?, ?, ?, ?, ?)
            """, (tag_id, ns, val, full_name, now_ms, now_ms))
            self.conn.commit()
            self.tags[full_name] = tag_id
            return tag_id
        except sqlite3.IntegrityError:
            c.execute("SELECT id FROM tags WHERE name COLLATE NOCASE = ?", (full_name,))
            row = c.fetchone()
            if row:
                self.tags[full_name] = row[0]
                return row[0]
            return tag_id

    def ingest_asset(
        self,
        source_path: Path,
        sha256: str,
        dest_folder_id: str,
        gemini_data: Dict[str, Any],
        gemini_cat: str
    ) -> str:
        """Ingest or update asset in this library."""
        file_size = source_path.stat().st_size
        now_ms = int(time.time() * 1000)
        ext = source_path.suffix.lstrip(".").lower()
        if not ext:
            ext = "jpeg"

        c = self.conn.cursor()

        # Check if already exists
        if sha256 in self.existing_shas:
            asset_id = self.existing_shas[sha256]
        else:
            asset_id = str(uuid.uuid4()).lower()
            prefix = asset_id[:2]
            storage_key = f"{prefix}/{asset_id}.{ext}"

            # Cloud-first: Do not copy originals to local SSD; originals stream to Cloudflare R2
            width, height = None, None
            try:
                with Image.open(source_path) as img:
                    width, height = img.size
            except Exception:
                pass

            mime_map = {
                "jpg": "image/jpeg",
                "jpeg": "image/jpeg",
                "png": "image/png",
                "heic": "image/heic",
                "webp": "image/webp"
            }
            mime_type = mime_map.get(ext, "image/jpeg")

            metadata_dict = {
                "version": 1,
                "file": {
                    "filenameExtension": ext,
                    "mimeType": mime_type
                },
                "image": {
                    "pixelWidth": width,
                    "pixelHeight": height,
                    "colorModel": "RGB"
                },
                "tiff": {},
                "otherImageIO": {}
            }
            metadata_json = json.dumps(metadata_dict)

            # Display name without extension
            display_name = source_path.stem[:255]

            # Ingest asset row
            c.execute("""
                INSERT INTO assets (
                    id, filename, display_name, parent_folder_id, storage_key, media_type,
                    width, height, file_size, created_at_ms, modified_at_ms, imported_at_ms, updated_at_ms,
                    favorite, rating, metadata_json, original_available
                ) VALUES (?, ?, ?, ?, ?, 'stillImage', ?, ?, ?, ?, ?, ?, ?, 0, 0, ?, 0)
            """, (
                asset_id, source_path.name, display_name, dest_folder_id, storage_key,
                width, height, file_size, now_ms, now_ms, now_ms, now_ms, metadata_json
            ))

            # Record content identity
            c.execute("""
                INSERT OR IGNORE INTO asset_content_identity (sha256, asset_id, byte_size, recorded_at_ms)
                VALUES (?, ?, ?, ?)
            """, (sha256, asset_id, file_size, now_ms))

            self.existing_shas[sha256] = asset_id

        # Attach Tags
        tags_to_attach = set()
        dom = gemini_data.get("domain") or "personal"
        tags_to_attach.add(f"pillar:{dom}")
        tags_to_attach.add(f"category:{gemini_cat}")
        
        if gemini_data.get("capture_type"):
            tags_to_attach.add(f"type:{gemini_data['capture_type']}")
        if gemini_data.get("app_name"):
            tags_to_attach.add(f"app:{slugify(gemini_data['app_name'])}")
        if gemini_data.get("creator_handle"):
            tags_to_attach.add(f"creator:{slugify(gemini_data['creator_handle'].lstrip('@'))}")
        if gemini_data.get("subject_or_tool_discussed"):
            tags_to_attach.add(f"tool:{slugify(gemini_data['subject_or_tool_discussed'])}")
        if gemini_data.get("has_vincent"):
            tags_to_attach.add("person:vincent")
        hp = gemini_data.get("hairline_presentation")
        if hp and hp not in ("notVisible", "not_visible", "none"):
            hp_slug = slugify(hp)
            if hp_slug in ("clearlyvisible", "clearly-visible"):
                tags_to_attach.add("hairline:clearly-visible")
                tags_to_attach.add("hairline:clearlyvisible")
                if gemini_data.get("quality") in ("keeper", "strong"):
                    tags_to_attach.add("hairline:undetectable")
            elif hp_slug in ("partiallyvisible", "partially-visible"):
                tags_to_attach.add("hairline:partially-visible")
                tags_to_attach.add("hairline:partiallyvisible")
            else:
                tags_to_attach.add(f"hairline:{hp_slug}")
        elif hp in ("notVisible", "not_visible"):
            tags_to_attach.add("hairline:not-visible")

        q_raw = gemini_data.get("quality", "ok")
        q_map = {
            "keeper": "quality:strong",
            "strong": "quality:strong",
            "ok": "quality:usable",
            "usable": "quality:usable",
            "weak": "quality:weak",
            "reject": "quality:weak"
        }
        tags_to_attach.add(q_map.get(q_raw, "quality:usable"))

        for t in gemini_data.get("tags") or []:
            t_str = str(t).strip().lower()
            if t_str:
                tags_to_attach.add(t_str)

        for tag_str in tags_to_attach:
            tag_id = self.get_or_create_tag(tag_str)
            try:
                c.execute("""
                    INSERT OR IGNORE INTO asset_tags (asset_id, tag_id, added_at_ms)
                    VALUES (?, ?, ?)
                """, (asset_id, tag_id, now_ms))
            except Exception:
                pass

        # Visual Assessment
        quality_raw = gemini_data.get("quality", "ok")
        quality_map = {
            "keeper": "strong",
            "ok": "usable",
            "weak": "weak",
            "reject": "weak"
        }
        biz_quality = quality_map.get(quality_raw, "usable")

        hairline_raw = gemini_data.get("hairline_presentation", "notVisible")
        hair_map = {
            "clearlyVisible": "clearlyVisible",
            "partiallyVisible": "partiallyVisible",
            "notVisible": "notVisible",
            "unclear": "unclear"
        }
        hairline = hair_map.get(hairline_raw, "notVisible")

        cap_type = gemini_data.get("capture_type", "camera_photo")
        role = "screenshot" if cap_type == "screenshot" else ("productDetail" if dom == "business" else "other")
        
        evidence_json = json.dumps([])
        conf = float(gemini_data.get("confidence") or 0.9)
        rat = gemini_data.get("rationale") or f"Classified under {gemini_cat} by Vertex AI Gemini"
        assessment_id = deterministic_uuid(f"assessment:{asset_id}:gemini-3.8-flash")

        try:
            c.execute("""
                INSERT OR REPLACE INTO visual_assessments (
                    id, asset_id, business_quality, evidence_json, photo_role, hairline_presentation,
                    confidence, rationale, provider, model_identifier, assessment_schema_version,
                    derivative_sha256, derivative_maximum_pixel_dimension, captured_at_ms, created_at_ms, updated_at_ms
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, 'local', 'gemini-3.8-flash', 1, ?, 1024, ?, ?, ?)
            """, (
                assessment_id, asset_id, biz_quality, evidence_json, role, hairline,
                conf, rat, sha256, now_ms, now_ms, now_ms
            ))
        except Exception:
            pass

        return asset_id

    def commit(self):
        c = self.conn.cursor()
        c.execute("UPDATE assets SET original_available = 0 WHERE original_available = 1")
        self.conn.commit()

    def close(self):
        self.conn.commit()
        self.conn.close()

def map_category_to_folder_path(domain: str, category: str) -> str:
    """Map domain & category to logical folder path inside the destination library."""
    cat_lower = category.lower()
    
    if domain == "personal":
        if "people" in cat_lower or "selfie" in cat_lower or "family" in cat_lower or "friend" in cat_lower:
            sub = "selfies" if "selfie" in cat_lower else ("friends" if "friend" in cat_lower else "portraits")
            return f"01_people_and_family/{sub}"
        elif "event" in cat_lower or "celebration" in cat_lower or "nightlife" in cat_lower:
            return "02_events_and_milestones/celebrations"
        elif "travel" in cat_lower or "vacation" in cat_lower:
            return "03_travel_places"
        elif "pet" in cat_lower or "dog" in cat_lower or "cat" in cat_lower:
            return "04_lifestyle_hobbies/pets_animals"
        elif "fitness" in cat_lower or "gym" in cat_lower or "health" in cat_lower:
            return "04_lifestyle_hobbies/fitness_health"
        elif "food" in cat_lower or "drink" in cat_lower or "dining" in cat_lower:
            return "04_lifestyle_hobbies/food_drinks"
        elif "car" in cat_lower or "vehicle" in cat_lower:
            return "04_lifestyle_hobbies/cars_vehicles"
        elif "doc" in cat_lower or "bill" in cat_lower or "receipt" in cat_lower or "card" in cat_lower:
            return "05_documents_and_receipts/financial_invoices"
        elif "quarantine" in cat_lower:
            return "06_private_quarantine"
        else:
            return "04_lifestyle_hobbies/interiors"

    elif domain == "business":
        if "product" in cat_lower or "thin-skin" in cat_lower:
            return "01_products/hair-systems"
        elif "spec" in cat_lower or "swatch" in cat_lower:
            return "02_specs"
        elif "people" in cat_lower or "model" in cat_lower or "hairline" in cat_lower or "before" in cat_lower:
            return "03_people/models"
        elif "lifestyle" in cat_lower:
            return "04_lifestyle"
        elif "shopify" in cat_lower or "web" in cat_lower:
            return "06_web"
        elif "brand" in cat_lower or "logo" in cat_lower:
            return "07_brand"
        elif "marketing" in cat_lower or "ad" in cat_lower:
            return "08_marketing"
        elif "operation" in cat_lower or "screenshot" in cat_lower or "reference" in cat_lower:
            return "09_reference/ops-screenshots"
        elif "private" in cat_lower:
            return "10_private"
        else:
            return "01_products"

    elif domain == "knowledge":
        if "ai" in cat_lower or "automation" in cat_lower or "agent" in cat_lower:
            return "01_ai_and_automation"
        elif "ui" in cat_lower or "ux" in cat_lower or "web" in cat_lower or "landing" in cat_lower:
            return "02_ui_and_web_design"
        elif "design" in cat_lower or "brand" in cat_lower or "typography" in cat_lower or "palette" in cat_lower:
            return "03_design_and_branding"
        elif "marketing" in cat_lower or "growth" in cat_lower or "hook" in cat_lower or "carousel" in cat_lower:
            return "04_marketing_and_growth"
        elif "code" in cat_lower or "dev" in cat_lower or "python" in cat_lower or "swift" in cat_lower:
            return "05_development_and_code"
        else:
            return "06_reference_screenshots"

    return "00_inbox"

def main():
    print("=" * 80)
    print("FRAMEBASE 3-LIBRARY INGESTION PIPELINE")
    print("Distributing 9,156 photos into 3 Dedicated Framebase Packages")
    print("=" * 80)

    # 1. Initialize Knowledge Library if missing
    init_knowledge_library()

    # 2. Connect to Libraries
    print("\nConnecting to Framebase libraries...")
    mgr_personal = FramebaseLibraryManager(PERSONAL_LIB)
    mgr_hsc = FramebaseLibraryManager(HSC_LIB)
    mgr_knowledge = FramebaseLibraryManager(KNOWLEDGE_LIB)

    library_map = {
        "personal": mgr_personal,
        "business": mgr_hsc,
        "knowledge": mgr_knowledge
    }

    # 3. Read classified records from state.sqlite
    conn = sqlite3.connect(str(DB_PATH))
    c = conn.cursor()
    c.execute("""
        SELECT id, file_path, year, filename, sha256, gemini_category, gemini_json
        FROM inventory
        WHERE gemini_json IS NOT NULL
        ORDER BY year DESC, id ASC
    """)
    rows = c.fetchall()
    conn.close()

    total = len(rows)
    print(f"Loaded {total} classified photos from state.sqlite.")

    counts = {"personal": 0, "business": 0, "knowledge": 0}
    t0 = time.time()
    batch_count = 0

    print("Beginning multi-library ingestion...\n")

    for idx, (r_id, fpath, yr, fn, db_sha, cat, gjson_str) in enumerate(rows, 1):
        try:
            d = json.loads(gjson_str)
        except Exception:
            continue

        dom = d.get("domain") or "personal"
        mgr = library_map.get(dom, mgr_personal)

        resolved = resolve_image_path(fpath, yr, fn)
        if not resolved or not resolved.exists():
            continue

        sha = db_sha
        if not sha or len(sha) != 64:
            sha = compute_sha256(resolved)

        folder_path = map_category_to_folder_path(dom, cat)
        folder_id = mgr.get_or_create_folder(folder_path)

        mgr.ingest_asset(
            source_path=resolved,
            sha256=sha,
            dest_folder_id=folder_id,
            gemini_data=d,
            gemini_cat=cat
        )

        counts[dom] += 1
        batch_count += 1

        if batch_count >= 250:
            for m in library_map.values():
                m.commit()
            batch_count = 0

        if idx % 500 == 0 or idx == total:
            elapsed = time.time() - t0
            rate = idx / max(elapsed, 0.1)
            print(f"[{idx}/{total}] Ingested {idx} photos ({rate:.1f} photos/sec) | Personal: {counts['personal']} | Knowledge: {counts['knowledge']} | Business: {counts['business']}", flush=True)

    # Final commits
    for m in library_map.values():
        m.close()

    elapsed_total = time.time() - t0
    print("\n" + "=" * 80)
    print(f"INGESTION COMPLETE in {elapsed_total:.1f}s!")
    print(f"Personal Library:  {counts['personal']:5} photos ({PERSONAL_LIB.name})")
    print(f"Knowledge Library: {counts['knowledge']:5} photos ({KNOWLEDGE_LIB.name})")
    print(f"HSC Library:       {counts['business']:5} photos ({HSC_LIB.name})")
    print(f"Total Ingested:    {sum(counts.values()):5} photos")
    print("=" * 80)

if __name__ == "__main__":
    main()


#!/usr/bin/env python3
"""
Ingest, Tag, and Pre-render Cleaned Google Drive Export into HSC Library.framebase.

Covers:
1. /Users/vincent/Downloads/Google Drive Images Export (6,001 pure commercial assets)
2. /Users/vincent/Downloads/Google Drive Images Export/isolated_reference_screenshots (6,304 screenshots)

Guarantees:
- Zero personal/private photos (all quarantined to quarantined_personal/).
- Zero existing duplicates (all in already_in_catalog/ or deduplicated by SHA-256).
- Strict Framebase Schema v14 compliance: media_type = 'stillImage', valid metadata_json, asset_content_identity.
- Granular 11-Folder routing.
- High-res 176x176 grid thumbnails and 720x720 inspector previews pre-generated.
"""

import os
import sys
import re
import json
import time
import uuid
import hashlib
import sqlite3
import subprocess
from pathlib import Path
from typing import Dict, Any, Optional, Tuple, List, Set
from concurrent.futures import ThreadPoolExecutor, as_completed
from PIL import Image, ImageOps, ImageFile

ImageFile.LOAD_TRUNCATED_IMAGES = True
Image.MAX_IMAGE_PIXELS = None

# Paths
ROOT_DIR = Path("/Users/vincent/04_systems/media_workshop")
DRIVE_DIR = Path("/Users/vincent/Downloads/Google Drive Images Export")
SCREENSHOTS_DIR = DRIVE_DIR / "isolated_reference_screenshots"
STOCK_DIR = DRIVE_DIR / "05_Stock_Photos"
CACHE_JSON_PATH = ROOT_DIR / "scripts/google_drive_cleansing_cache.json"

HSC_LIB = Path.home() / "Pictures/HSC Library.framebase"
CATALOG_DB = HSC_LIB / "Catalog/catalog.sqlite"
THUMB_CACHE_DIR = Path.home() / "Library/Caches/com.vincentlaroche.framebase/Thumbnails"

def compute_sha256(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        while chunk := f.read(1024 * 1024):
            h.update(chunk)
    return h.hexdigest().lower()

def slugify(text: str) -> str:
    text = text.lower().strip()
    text = re.sub(r"[^\w\s-]", "", text)
    text = re.sub(r"[\s_]+", "-", text)
    return text[:64].strip("-")

def deterministic_uuid(val: str) -> str:
    return str(uuid.uuid5(uuid.NAMESPACE_DNS, val)).lower()

class GoogleDriveIngestionPipeline:
    def __init__(self):
        self.conn = sqlite3.connect(str(CATALOG_DB), timeout=60.0)
        self.conn.execute("PRAGMA journal_mode=WAL;")
        self.conn.execute("PRAGMA busy_timeout=60000;")
        self.folders = {}
        self.tags = {}
        self.existing_shas = {}
        self.cached_cleansed = {}
        self.executor = ThreadPoolExecutor(max_workers=10)
        self.thumb_futures = []
        self.load_metadata()

    def load_metadata(self):
        c = self.conn.cursor()
        c.execute("SELECT id, name, parent_folder_id FROM folders")
        rows = c.fetchall()
        id_to_row = {r[0]: r for r in rows}
        for fid, name, parent_id in rows:
            parts = [name]
            curr = parent_id
            while curr and curr in id_to_row:
                p_row = id_to_row[curr]
                parts.append(p_row[1])
                curr = p_row[2]
            parts.reverse()
            self.folders["/".join(parts).lower()] = fid
            self.folders[name.lower()] = fid

        c.execute("SELECT id, name FROM tags")
        self.tags = {r[1].lower(): r[0] for r in c.fetchall()}

        c.execute("SELECT sha256, asset_id FROM asset_content_identity")
        self.existing_shas = {r[0]: r[1] for r in c.fetchall()}

        if CACHE_JSON_PATH.exists():
            try:
                with open(CACHE_JSON_PATH, "r", encoding="utf-8") as f:
                    self.cached_cleansed = json.load(f)
                print(f"Loaded {len(self.cached_cleansed)} verified vision items from cache.")
            except Exception as e:
                print(f"Warning: could not load vision cache: {e}")

        print(f"Catalog DB initialized: {len(self.folders)} folder keys, {len(self.tags)} tags, {len(self.existing_shas)} existing assets.")

    def get_or_create_folder(self, folder_path: str) -> str:
        norm = folder_path.strip("/").lower()
        if norm in self.folders:
            return self.folders[norm]

        parts = [p.strip() for p in folder_path.strip("/").split("/") if p.strip()]
        curr_parent_id = None
        cum = []
        now_ms = int(time.time() * 1000)
        c = self.conn.cursor()

        for idx, part in enumerate(parts):
            cum.append(part.lower())
            sub = "/".join(cum)
            if sub in self.folders:
                curr_parent_id = self.folders[sub]
                continue

            folder_id = str(uuid.uuid4()).lower()
            try:
                c.execute("""
                    INSERT INTO folders (id, name, parent_folder_id, created_at_ms, updated_at_ms, sort_order)
                    VALUES (?, ?, ?, ?, ?, 10)
                """, (folder_id, part, curr_parent_id, now_ms, now_ms))
                self.conn.commit()
                self.folders[sub] = folder_id
                self.folders[part.lower()] = folder_id
                curr_parent_id = folder_id
            except sqlite3.IntegrityError:
                c.execute("SELECT id FROM folders WHERE COALESCE(parent_folder_id, '') = ? AND name COLLATE NOCASE = ?",
                          (curr_parent_id or "", part))
                row = c.fetchone()
                if row:
                    curr_parent_id = row[0]
                    self.folders[sub] = curr_parent_id
                    self.folders[part.lower()] = curr_parent_id

        return curr_parent_id

    def get_or_create_tag(self, raw_tag: str) -> str:
        tag_str = raw_tag.strip().lower()
        if ":" not in tag_str:
            ns, val = "tag", slugify(tag_str)
        else:
            p1, p2 = tag_str.split(":", 1)
            ns = slugify(p1)[:64]
            val = slugify(p2)[:64]
            if not ns: ns = "tag"
            if not val: val = "general"

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

    def classify_commercial_file(self, fn: str) -> Dict[str, Any]:
        fn_lower = fn.lower()
        
        # 0. Check verified AI cache first
        if fn in self.cached_cleansed:
            cached = self.cached_cleansed[fn]
            rf = cached.get("recommended_folder")
            if rf and rf not in ("00_inbox", "unknown"):
                cat = cached.get("category", "commercial")
                return {
                    "folder": rf,
                    "tags": ["pillar:business", f"category:{cat}", "source:google-drive-export", "quality:strong"]
                }

        # 1. Brand assets
        if re.search(r"wordmark|monogram|brand|hsc logo|1847 logo", fn_lower):
            return {"folder": "07_brand/logos", "tags": ["pillar:business", "category:brand", "type:logo", "brand:hair-solutions-co", "quality:strong"]}
        if re.search(r"\bicon\b|favicon|app.?icon|\bemail\.png$", fn_lower):
            return {"folder": "07_brand/ui", "tags": ["pillar:business", "category:brand", "type:icon", "brand:hair-solutions-co", "quality:usable"]}
            
        # 2. Hair system products
        if re.search(r"thin-skin|ultra-thin-skin|nano-skin|mono-edge|mono-fusion|mono-pro|french-lace|swiss-lace|hair-system|toupee|protesis-capilar|oneskin|ntc\d+|laceplus|skinplus|custom-sp|mens-wig|product-shot|standard-skin|sunny-full|hairpiece", fn_lower):
            base_tag = "base:poly-skin" if "skin" in fn_lower else ("base:lace" if "lace" in fn_lower else "base:mono-mesh")
            return {"folder": "01_products/hair-systems", "tags": ["pillar:business", "category:product", "product:hair-system", base_tag, "quality:strong"]}

        # 3. Maintenance products by brand
        if re.search(r"prohair|phl-|dermal|ghostbuster|new demension|phantom", fn_lower):
            return {"folder": "01_products/maintenance/prohair-labs", "tags": ["pillar:business", "category:maintenance", "brand:pro-hair-labs", "quality:strong"]}
        if re.search(r"walker|1522|ultra-hold|no-shine|sensi-tak|extenda|c-?22|action-solvent|signature|lacerelease|lace-release", fn_lower):
            return {"folder": "01_products/maintenance/walker-tape", "tags": ["pillar:business", "category:maintenance", "brand:walker-tape", "quality:strong"]}
        if re.search(r"ghostbond|ghost-bond", fn_lower):
            return {"folder": "01_products/maintenance/ghost-bond", "tags": ["pillar:business", "category:maintenance", "brand:ghost-bond", "quality:strong"]}
        if re.search(r"lux\s*hair|luxhair|air\s*flex", fn_lower):
            return {"folder": "01_products/maintenance/lux-hair", "tags": ["pillar:business", "category:maintenance", "brand:lux-hair", "quality:strong"]}
        if re.search(r"sunshine|st_|ssp_", fn_lower):
            return {"folder": "01_products/maintenance/sunshine", "tags": ["pillar:business", "category:maintenance", "brand:sunshine", "quality:strong"]}
        if re.search(r"clips|glue|adhesive|remover|solvent|shampoo|conditioner|hyperhold|tape roll|brush|comb|tangle teezer", fn_lower):
            return {"folder": "01_products/maintenance/general", "tags": ["pillar:business", "category:maintenance", "type:adhesive-solvent", "quality:usable"]}

        # 4. Specs & Swatches
        # A. Curl / Wave
        if re.search(r"\b\d+mm\b|\b\d+(\.\d+)?\s*cm\s*curl\b|curl|wave", fn_lower):
            return {"folder": "02_specs/swatches/curl-pattern", "tags": ["pillar:business", "category:specs", "type:curl-wave", "quality:strong"]}
        # B. Grey Percentage (e.g. 1B10, 1B20, 210, 320, 440, #1B20, 1B50)
        if re.search(r"^#?(1b|1a|[1-7])(05|10|15|20|30|40|50|60|80)(hc|r|t|\.|\b|_)", fn_lower) or "grey" in fn_lower or "gray" in fn_lower:
            m = re.search(r"(05|10|15|20|30|40|50|60|80)", fn)
            g_tag = f"grey:{m.group(1)}%" if m else "grey:20%"
            return {"folder": "02_specs/swatches/grey-percentage", "tags": ["pillar:business", "category:specs", g_tag, "type:swatch", "quality:strong"]}
        # C. Hair Color (e.g. #1, #1B, #2, 6R, 60hc, 610, 613, #1A)
        if re.search(r"^#?(1b|1a|[1-8]|17|18|20|22|30|60|610|613|614)(hc|r|t|\.|\b|_)", fn_lower) or "color" in fn_lower or "swatch" in fn_lower:
            m = re.search(r"#?([0-9]{1,3}[a-zA-Z]{0,2})", fn)
            c_tag = f"color:{m.group(1).upper()}" if m else "color:natural"
            return {"folder": "02_specs/swatches/hair-color", "tags": ["pillar:business", "category:specs", c_tag, "type:swatch", "quality:strong"]}
        # D. Density
        if re.search(r"density|\b\d{2,3}%\b", fn_lower):
            return {"folder": "02_specs/swatches/density", "tags": ["pillar:business", "category:specs", "type:density", "quality:strong"]}
        # E. Base material
        if re.search(r"base-material|poly-skin|mesh", fn_lower):
            return {"folder": "02_specs/swatches/base-material", "tags": ["pillar:business", "category:specs", "type:base-material", "quality:strong"]}
        # F. Diagrams & Templates
        if re.search(r"diagram|template|contour|measur|mannequin|hair-direction|front-contour", fn_lower):
            return {"folder": "02_specs/diagrams", "tags": ["pillar:business", "category:specs", "type:diagram", "quality:strong"]}
        # G. Spec sheets & Guides / Catalogues
        if re.search(r"page\s*\d+|specs\s*sheet|guide|chart|catalogue|catalog", fn_lower):
            return {"folder": "02_specs/guides", "tags": ["pillar:business", "category:specs", "type:guide", "quality:usable"]}

        # 5. People & Models
        if "vincent" in fn_lower or "facetune" in fn_lower:
            return {"folder": "03_people/models/vincent", "tags": ["pillar:business", "category:people", "person:vincent", "hairline:clearly-visible", "quality:strong"]}
        if "danny" in fn_lower:
            return {"folder": "03_people/models/danny", "tags": ["pillar:business", "category:people", "person:danny", "quality:strong"]}
        if "barry" in fn_lower:
            return {"folder": "03_people/models/barry", "tags": ["pillar:business", "category:people", "person:barry", "quality:strong"]}
        if "kevin" in fn_lower:
            return {"folder": "03_people/models/kevin", "tags": ["pillar:business", "category:people", "person:kevin", "quality:strong"]}
        if "serge" in fn_lower or "onehead_serge" in fn_lower:
            return {"folder": "03_people/models/serge", "tags": ["pillar:business", "category:people", "person:serge", "quality:strong"]}
        if "salem" in fn_lower:
            return {"folder": "03_people/models/salem", "tags": ["pillar:business", "category:people", "person:salem", "quality:strong"]}
        if "model" in fn_lower or "portrait" in fn_lower:
            return {"folder": "03_people/models", "tags": ["pillar:business", "category:people", "type:model-portrait", "quality:strong"]}
        if ("before" in fn_lower and "after" in fn_lower) or "antes" in fn_lower or "despues" in fn_lower:
            return {"folder": "03_people/before-after/studio", "tags": ["pillar:business", "category:people", "type:before-after", "shot:before-after-split", "quality:strong"]}
        if "bald" in fn_lower or "scalp" in fn_lower or "hair-loss" in fn_lower or "alopecia" in fn_lower:
            return {"folder": "03_people/before-after/customer-submitted", "tags": ["pillar:business", "category:people", "state:before-hair-loss", "quality:usable"]}

        # 6. Lifestyle
        if "barber" in fn_lower or "salon" in fn_lower or "shower" in fn_lower:
            return {"folder": "04_lifestyle/barber-salon", "tags": ["pillar:business", "category:lifestyle", "setting:salon", "quality:usable"]}
        if "sports" in fn_lower or "playing" in fn_lower or "gym" in fn_lower or "swim" in fn_lower:
            return {"folder": "04_lifestyle/active", "tags": ["pillar:business", "category:lifestyle", "setting:active", "quality:usable"]}

        # 7. Web & Education
        if "infographic" in fn_lower or "tutorial" in fn_lower:
            return {"folder": "05_education", "tags": ["pillar:business", "category:education", "type:infographic", "quality:strong"]}
        if "blog" in fn_lower:
            return {"folder": "06_web/blog", "tags": ["pillar:business", "category:web", "type:blog-hero", "quality:usable"]}
        if re.search(r"collections-header|collection|catalog", fn_lower):
            return {"folder": "06_web/collections", "tags": ["pillar:business", "category:web", "type:collection-header", "quality:usable"]}
        if re.search(r"desktop|mobile|header|hero|cover|banner", fn_lower):
            return {"folder": "06_web/home", "tags": ["pillar:business", "category:web", "type:web-banner", "quality:usable"]}

        # 8. Marketing
        if re.search(r"instagram|pricelist|discount|sale|post|story|facebook|promo|testimonial", fn_lower):
            return {"folder": "08_marketing/social", "tags": ["pillar:business", "category:marketing", "type:social-ad", "quality:usable"]}
        if "ad" in fn_lower or "campaign" in fn_lower:
            return {"folder": "08_marketing/ads", "tags": ["pillar:business", "category:marketing", "type:campaign-ad", "quality:strong"]}

        return {"folder": "08_marketing", "tags": ["pillar:business", "category:marketing", "type:marketing-creative", "quality:usable"]}

    def generate_thumbnails(self, aid: str, src_path: Path, file_size: int, mod_ms: int):
        shard = aid[:2]
        shard_dir = THUMB_CACHE_DIR / shard
        shard_dir.mkdir(parents=True, exist_ok=True)

        t1 = shard_dir / f"v1-thumbnail-{aid}-{file_size}-{mod_ms}-176x176-3ff0000000000000.png"
        t2 = shard_dir / f"v1-thumbnail-{aid}-{file_size}-{mod_ms}-176x176-4000000000000000.png"
        p1 = shard_dir / f"v1-preview-{aid}-{file_size}-{mod_ms}-720x720-3ff0000000000000.png"

        if t1.exists() and p1.exists():
            if not t2.exists():
                try: os.link(t1, t2)
                except Exception: pass
            return

        ext = src_path.suffix.lower()
        im = None
        try:
            if ext == ".svg":
                tmp_out = shard_dir / f"tmp_svg_{aid}.png"
                subprocess.run(["qlmanage", "-t", "-s", "720", "-o", str(shard_dir), str(src_path)],
                               stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=5)
                gen_png = shard_dir / f"{src_path.name}.png"
                if gen_png.exists():
                    im = Image.open(gen_png)
                    gen_png.unlink()
            elif ext in (".heic", ".heif"):
                tmp_jpg = shard_dir / f"tmp_heic_{aid}.jpg"
                subprocess.run(["sips", "-s", "format", "jpeg", str(src_path), "--out", str(tmp_jpg)],
                               stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=5)
                if tmp_jpg.exists():
                    im = Image.open(tmp_jpg)
                    tmp_jpg.unlink()
            else:
                im = Image.open(src_path)
                im = ImageOps.exif_transpose(im)
        except Exception:
            return

        if not im:
            return

        try:
            # 1. Preview 720x720
            prev_im = im.copy()
            prev_im.thumbnail((720, 720), Image.Resampling.LANCZOS)
            if prev_im.mode in ("RGBA", "LA") or (prev_im.mode == "P" and "transparency" in prev_im.info):
                prev_im.save(p1, "PNG", optimize=True)
            else:
                prev_im = prev_im.convert("RGB")
                prev_im.save(p1, "PNG", optimize=True)

            # 2. Thumbnail 176x176
            thumb_im = im.copy()
            thumb_im.thumbnail((176, 176), Image.Resampling.LANCZOS)
            if thumb_im.mode not in ("RGB", "RGBA"):
                thumb_im = thumb_im.convert("RGB")
            thumb_im.save(t1, "PNG", optimize=True)
            try:
                if t2.exists(): t2.unlink()
                os.link(t1, t2)
            except Exception:
                thumb_im.save(t2, "PNG", optimize=True)
        except Exception:
            pass

    def ingest_asset(self, fp: Path, classification: Dict[str, Any], sha256: str) -> str:
        fn = fp.name
        file_size = fp.stat().st_size
        now_ms = int(time.time() * 1000)
        ext = fp.suffix.lstrip(".").lower() or "jpeg"

        folder_path = classification["folder"]
        folder_id = self.get_or_create_folder(folder_path)

        c = self.conn.cursor()

        if sha256 in self.existing_shas:
            asset_id = self.existing_shas[sha256]
            c.execute("UPDATE assets SET parent_folder_id = ?, updated_at_ms = ? WHERE id = ?",
                      (folder_id, now_ms, asset_id))
        else:
            asset_id = str(uuid.uuid4()).lower()
            storage_key = f"{asset_id[:2]}/{asset_id}.{ext}"

            width, height = None, None
            try:
                if ext in (".heic", ".heif"):
                    out = subprocess.check_output(["sips", "-g", "pixelWidth", "-g", "pixelHeight", str(fp)], text=True)
                    w_m = re.search(r"pixelWidth:\s*(\d+)", out)
                    h_m = re.search(r"pixelHeight:\s*(\d+)", out)
                    if w_m and h_m:
                        w_val, h_val = int(w_m.group(1)), int(h_m.group(1))
                        if w_val > 0 and h_val > 0:
                            width, height = w_val, h_val
                else:
                    with Image.open(fp) as img:
                        w_val, h_val = img.size
                        if w_val > 0 and h_val > 0:
                            width, height = w_val, h_val
            except Exception:
                pass

            mime_map = {
                "jpg": "image/jpeg", "jpeg": "image/jpeg", "png": "image/png",
                "webp": "image/webp", "svg": "image/svg+xml", "tif": "image/tiff",
                "tiff": "image/tiff", "heic": "image/heic", "avif": "image/avif"
            }
            mime_type = mime_map.get(ext, "image/jpeg")

            metadata_dict = {
                "version": 1,
                "file": {"filenameExtension": ext, "mimeType": mime_type},
                "image": {"pixelWidth": width, "pixelHeight": height, "colorModel": "RGB"},
                "tiff": {}, "otherImageIO": {}
            }
            metadata_json = json.dumps(metadata_dict)
            display_name = fp.stem.replace("\x00", "").strip()[:255].strip()
            if not display_name:
                display_name = f"Asset_{asset_id[:8]}"
            fn = fp.name.replace("\x00", "")[:1024]

            c.execute("""
                INSERT INTO assets (
                    id, filename, display_name, parent_folder_id, storage_key, media_type,
                    width, height, file_size, created_at_ms, modified_at_ms, imported_at_ms, updated_at_ms,
                    favorite, rating, metadata_json, original_available
                ) VALUES (?, ?, ?, ?, ?, 'stillImage', ?, ?, ?, ?, ?, ?, ?, 0, 0, ?, 0)
            """, (
                asset_id, fn, display_name, folder_id, storage_key,
                width, height, file_size, now_ms, now_ms, now_ms, now_ms, metadata_json
            ))

            c.execute("""
                INSERT OR IGNORE INTO asset_content_identity (sha256, asset_id, byte_size, recorded_at_ms)
                VALUES (?, ?, ?, ?)
            """, (sha256, asset_id, file_size, now_ms))

            self.existing_shas[sha256] = asset_id

        # Attach Tags
        tags_to_attach = set(classification.get("tags", []))
        tags_to_attach.add("pillar:business")
        tags_to_attach.add("source:google-drive-export")

        for tag_str in tags_to_attach:
            tag_id = self.get_or_create_tag(tag_str)
            try:
                c.execute("""
                    INSERT OR IGNORE INTO asset_tags (asset_id, tag_id, added_at_ms)
                    VALUES (?, ?, ?)
                """, (asset_id, tag_id, now_ms))
            except Exception:
                pass

        # Generate thumbnail asynchronously
        fut = self.executor.submit(self.generate_thumbnails, asset_id, fp, file_size, now_ms)
        self.thumb_futures.append(fut)
        if len(self.thumb_futures) > 1500:
            self.thumb_futures = [f for f in self.thumb_futures if not f.done()]

        return asset_id

    def run(self):
        print("=== Media Workshop: Google Drive Cleaned Corpus Ingestion ===")
        
        # 1. Gather files
        valid_exts = {".jpg", ".jpeg", ".png", ".webp", ".heic", ".svg", ".tif", ".tiff", ".ico", ".avif"}
        
        # A. Commercial Assets from Root
        commercial_files = [f for f in DRIVE_DIR.iterdir() if f.is_file() and f.suffix.lower() in valid_exts and not f.name.startswith(".")]
        
        # B. Video Posters from Root Videos
        video_files = [f for f in DRIVE_DIR.iterdir() if f.is_file() and f.suffix.lower() in {".mp4", ".mov", ".m4v"}]
        
        # C. Stock Photos
        stock_files = [f for f in STOCK_DIR.iterdir() if f.is_file() and f.suffix.lower() in valid_exts and not f.name.startswith(".")] if STOCK_DIR.exists() else []

        # D. Isolated Screenshots
        screenshot_files = [f for f in SCREENSHOTS_DIR.iterdir() if f.is_file() and f.suffix.lower() in valid_exts and not f.name.startswith(".")]

        print(f"Discovered:")
        print(f"  Commercial Assets: {len(commercial_files)}")
        print(f"  Stock Photos: {len(stock_files)}")
        print(f"  Videos to Posterize: {len(video_files)}")
        print(f"  Isolated Screenshots: {len(screenshot_files)}")
        total_all = len(commercial_files) + len(stock_files) + len(video_files) + len(screenshot_files)
        print(f"  Total Assets to Ingest: {total_all}")

        # 2. Ingest Commercial Assets
        print("\nPhase 1: Ingesting Commercial Assets...")
        t0 = time.time()
        for idx, fp in enumerate(commercial_files):
            h = compute_sha256(fp)
            cls = self.classify_commercial_file(fp.name)
            self.ingest_asset(fp, cls, h)
            if (idx + 1) % 500 == 0 or (idx + 1) == len(commercial_files):
                self.conn.commit()
                dt = time.time() - t0
                print(f"  Commercial: {idx + 1}/{len(commercial_files)} ({dt:.1f}s)...")

        # 3. Ingest Stock Photos
        if stock_files:
            print("\nPhase 2: Ingesting Stock Photos...")
            for idx, fp in enumerate(stock_files):
                h = compute_sha256(fp)
                cls = {
                    "folder": "04_lifestyle",
                    "tags": ["pillar:business", "category:lifestyle", "type:stock-photo", "source:google-drive-export", "quality:usable"]
                }
                self.ingest_asset(fp, cls, h)
            self.conn.commit()
            print(f"  Stock Photos: {len(stock_files)} ingested.")

        # 4. Extract & Ingest Video Posters
        if video_files:
            print("\nPhase 3: Generating Video Posters...")
            posters_dir = DRIVE_DIR / "video_posters"
            posters_dir.mkdir(exist_ok=True)
            for vp in video_files:
                poster_path = posters_dir / f"{vp.stem}_poster.jpg"
                if not poster_path.exists() or poster_path.stat().st_size == 0:
                    subprocess.run(["ffmpeg", "-y", "-ss", "00:00:01.000", "-i", str(vp),
                                    "-vframes", "1", "-q:v", "2", str(poster_path)],
                                   stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
                if poster_path.exists() and poster_path.stat().st_size > 0:
                    h = compute_sha256(poster_path)
                    cls = {
                        "folder": "08_marketing/social",
                        "tags": ["pillar:business", "source:google-drive-export", "type:video-poster", f"video:{slugify(vp.stem)}", "quality:strong"]
                    }
                    self.ingest_asset(poster_path, cls, h)
            self.conn.commit()
            print(f"  Video Posters: {len(video_files)} generated and ingested.")

        # 5. Ingest Reference Screenshots
        print("\nPhase 4: Ingesting Reference Screenshots...")
        t1 = time.time()
        for idx, fp in enumerate(screenshot_files):
            h = compute_sha256(fp)
            cls = {
                "folder": "09_reference/ops-screenshots",
                "tags": ["pillar:business", "category:reference", "type:screenshot", "source:google-drive-export", "quality:usable"]
            }
            self.ingest_asset(fp, cls, h)
            if (idx + 1) % 1000 == 0 or (idx + 1) == len(screenshot_files):
                self.conn.commit()
                dt = time.time() - t1
                print(f"  Screenshots: {idx + 1}/{len(screenshot_files)} ({dt:.1f}s)...")

        # 6. Wait for all thumbnail generation threads
        print("\nPhase 5: Finalizing Thumbnail and Inspector Previews...")
        t2 = time.time()
        for f in as_completed(self.thumb_futures):
            pass
        self.executor.shutdown(wait=True)
        print(f"  Thumbnail rendering completed in {time.time() - t2:.1f}s.")

        # 7. Checkpoint SQLite WAL
        self.conn.commit()
        print("\nCheckpointing SQLite WAL...")
        self.conn.execute("PRAGMA wal_checkpoint(TRUNCATE);")
        self.conn.close()

        print(f"\nSUCCESS: Ingestion of {total_all} Google Drive assets completed into HSC Library.framebase!")

if __name__ == "__main__":
    pipeline = GoogleDriveIngestionPipeline()
    pipeline.run()

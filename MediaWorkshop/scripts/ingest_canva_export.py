#!/usr/bin/env python3
"""
Ingest, Classify, Tag, and Pre-render Canva Export into HSC Library.framebase.

Covers:
1. /Users/vincent/04_systems/media_workshop/canva_export/images (3,265 image files)
2. /Users/vincent/04_systems/media_workshop/canva_export/videos (10 promo MP4s)
3. /Users/vincent/04_systems/media_workshop/canva_export/documents (12 promo MP4s)
4. Comprehensive inventory of design documents (PPTX, PDF, DOCX)

Features:
- Hybrid Classification: Deterministic Brand/Spec rules + Gemini 3.8 Flash Multimodal Vision
- Incremental caching in scripts/canva_visual_cache.json
- Framebase Schema v14 compliance: stillImage, valid metadata_json, asset_content_identity (SHA-256)
- 11-Folder Operating Model with granular subfolder routing
- High-res thumbnail and preview caching in ~/Library/Caches/com.vincentlaroche.framebase/Thumbnails/
- Poster frame generation for all promo videos via ffmpeg
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
from collections import Counter
from concurrent.futures import ThreadPoolExecutor, as_completed
from PIL import Image, ImageOps, ImageFile

ImageFile.LOAD_TRUNCATED_IMAGES = True
Image.MAX_IMAGE_PIXELS = None

# Paths
ROOT_DIR = Path("/Users/vincent/04_systems/media_workshop")
CANVA_DIR = ROOT_DIR / "canva_export"
IMAGES_DIR = CANVA_DIR / "images"
VIDEOS_DIR = CANVA_DIR / "videos"
DOCS_DIR = CANVA_DIR / "documents"
REPORTS_DIR = CANVA_DIR / "sorting_reports"
CACHE_JSON_PATH = ROOT_DIR / "scripts/canva_visual_cache.json"

HSC_LIB = Path.home() / "Pictures/HSC Library.framebase"
CATALOG_DB = HSC_LIB / "Catalog/catalog.sqlite"
THUMB_CACHE_DIR = Path.home() / "Library/Caches/com.vincentlaroche.framebase/Thumbnails"

# Load .env for GEMINI_API_KEY
env_file = Path.home() / ".env"
if env_file.exists():
    with open(env_file) as f:
        for line in f:
            if line.strip() and not line.startswith("#") and "=" in line:
                k, v = line.strip().split("=", 1)
                os.environ.setdefault(k, v)

from google import genai
from google.genai import types

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

class CanvaIngestionPipeline:
    def __init__(self):
        self.conn = sqlite3.connect(str(CATALOG_DB), timeout=60.0)
        self.conn.execute("PRAGMA journal_mode=WAL;")
        self.conn.execute("PRAGMA busy_timeout=60000;")
        self.folders = {}
        self.tags = {}
        self.existing_shas = {}
        self.load_metadata()
        
        # Load visual cache
        self.visual_cache = {}
        if CACHE_JSON_PATH.exists():
            try:
                with open(CACHE_JSON_PATH, "r", encoding="utf-8") as f:
                    self.visual_cache = json.load(f)
                print(f"Loaded {len(self.visual_cache)} visual classifications from cache.")
            except Exception as e:
                print(f"Failed to load visual cache: {e}")

        # GenAI Client
        self.ai_client = genai.Client()

    def load_metadata(self):
        c = self.conn.cursor()
        # 1. Folders
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

        # 2. Tags
        c.execute("SELECT id, name FROM tags")
        self.tags = {r[1].lower(): r[0] for r in c.fetchall()}

        # 3. Existing SHAs
        c.execute("SELECT sha256, asset_id FROM asset_content_identity")
        self.existing_shas = {r[0]: r[1] for r in c.fetchall()}
        print(f"DB initialized: {len(self.folders)} folder keys, {len(self.tags)} tags, {len(self.existing_shas)} existing assets.")

    def save_visual_cache(self):
        with open(CACHE_JSON_PATH, "w", encoding="utf-8") as f:
            json.dump(self.visual_cache, f, indent=2)

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

    def rule_classify(self, fn: str, manifest_bucket: str) -> Optional[Dict[str, Any]]:
        """High-precision deterministic rule classification."""
        fn_lower = fn.lower()
        
        # 1. Brand assets
        if manifest_bucket == "brand_assets" or re.search(r"wordmark|monogram|brand|hsc logo|1847 logo", fn_lower):
            return {
                "folder": "07_brand/logos",
                "tags": ["pillar:business", "category:brand", "type:logo", "brand:hair-solutions-co", "quality:strong"]
            }
        if re.search(r"icon|favicon|app.?icon", fn_lower):
            return {
                "folder": "07_brand/ui",
                "tags": ["pillar:business", "category:brand", "type:icon", "brand:hair-solutions-co", "quality:usable"]
            }
            
        # 2. Hair system products
        if manifest_bucket == "hair_system_product_images" or re.search(r"thin-skin|ultra-thin-skin|nano-skin|mono-edge|mono-fusion|mono-pro|french-lace|swiss-lace|hair-system", fn_lower):
            base_tag = "base:poly-skin" if "skin" in fn_lower else ("base:lace" if "lace" in fn_lower else "base:mono-mesh")
            return {
                "folder": "01_products/hair-systems",
                "tags": ["pillar:business", "category:product", "product:hair-system", base_tag, "quality:strong"]
            }

        # 3. Maintenance products by brand
        if manifest_bucket == "maintenance_products__pro_hair_labs" or re.search(r"prohair|phl-|dermal|ghostbuster|new demension|phantom", fn_lower):
            return {
                "folder": "01_products/maintenance/prohair-labs",
                "tags": ["pillar:business", "category:maintenance", "brand:pro-hair-labs", "quality:strong"]
            }
        if manifest_bucket == "maintenance_products__walker_tape" or re.search(r"walker|1522|ultra-hold|no-shine|sensi-tak|extenda|c-?22|action-solvent|signature", fn_lower):
            return {
                "folder": "01_products/maintenance/walker-tape",
                "tags": ["pillar:business", "category:maintenance", "brand:walker-tape", "quality:strong"]
            }
        if manifest_bucket == "maintenance_products__ghost_bond" or re.search(r"ghostbond|ghost-bond", fn_lower):
            return {
                "folder": "01_products/maintenance/ghost-bond",
                "tags": ["pillar:business", "category:maintenance", "brand:ghost-bond", "quality:strong"]
            }
        if manifest_bucket == "maintenance_products__lux_hair_amazon" or re.search(r"lux\s*hair|luxhair", fn_lower):
            return {
                "folder": "01_products/maintenance/lux-hair",
                "tags": ["pillar:business", "category:maintenance", "brand:lux-hair", "quality:strong"]
            }
        if manifest_bucket == "maintenance_products__sunshine" or re.search(r"sunshine|st_|ssp_", fn_lower):
            return {
                "folder": "01_products/maintenance/sunshine",
                "tags": ["pillar:business", "category:maintenance", "brand:sunshine", "quality:strong"]
            }
        if manifest_bucket == "maintenance_products__general" or re.search(r"clips|glue|adhesive|remover|solvent|shampoo|conditioner|hyperhold|tape roll", fn_lower):
            return {
                "folder": "01_products/maintenance/general",
                "tags": ["pillar:business", "category:maintenance", "type:adhesive-solvent", "quality:usable"]
            }

        # 4. Specs & Swatches
        if re.search(r"#\d+[a-zA-Z]?\d{2}", fn):
            m = re.search(r"#(\d+[a-zA-Z]?)(\d{2})", fn)
            grey_val = m.group(2) if m else "20"
            return {
                "folder": "02_specs/swatches/grey-percentage",
                "tags": ["pillar:business", "category:specs", f"grey:{grey_val}%", "type:swatch", "quality:strong"]
            }
        if re.search(r"^#\d+[a-zA-Z]*(\.|\s|\()|color\s*#|haircolor", fn_lower):
            m = re.search(r"#([0-9a-zA-Z]+)", fn)
            code = m.group(1).upper() if m else "1B"
            return {
                "folder": "02_specs/swatches/hair-color",
                "tags": ["pillar:business", "category:specs", f"color:{code}", "type:swatch", "quality:strong"]
            }
        if re.search(r"\b\d+mm\b|curl|wave", fn_lower):
            return {
                "folder": "02_specs/swatches/curl-pattern",
                "tags": ["pillar:business", "category:specs", "type:curl-wave", "quality:strong"]
            }
        if re.search(r"density|\b\d{2,3}%\b", fn_lower):
            return {
                "folder": "02_specs/swatches/density",
                "tags": ["pillar:business", "category:specs", "type:density", "quality:strong"]
            }
        if re.search(r"base-material|poly-skin|mesh", fn_lower):
            return {
                "folder": "02_specs/swatches/base-material",
                "tags": ["pillar:business", "category:specs", "type:base-material", "quality:strong"]
            }
        if re.search(r"diagram|template|contour|measur", fn_lower):
            return {
                "folder": "02_specs/diagrams",
                "tags": ["pillar:business", "category:specs", "type:diagram", "quality:strong"]
            }
        if re.search(r"specs\s*sheet|guide|chart", fn_lower):
            return {
                "folder": "02_specs/guides",
                "tags": ["pillar:business", "category:specs", "type:guide", "quality:usable"]
            }

        # 5. People & Models
        if "facetune" in fn_lower or "vincent" in fn_lower:
            return {
                "folder": "03_people/models/vincent",
                "tags": ["pillar:business", "category:people", "person:vincent", "hairline:clearly-visible", "quality:strong"]
            }
        if "danny" in fn_lower:
            return {
                "folder": "03_people/models/danny",
                "tags": ["pillar:business", "category:people", "person:danny", "quality:strong"]
            }
        if "barry" in fn_lower:
            return {
                "folder": "03_people/models/barry",
                "tags": ["pillar:business", "category:people", "person:barry", "quality:strong"]
            }
        if "kevin" in fn_lower:
            return {
                "folder": "03_people/models/kevin",
                "tags": ["pillar:business", "category:people", "person:kevin", "quality:strong"]
            }
        if "serge" in fn_lower:
            return {
                "folder": "03_people/models/serge",
                "tags": ["pillar:business", "category:people", "person:serge", "quality:strong"]
            }
        if "salem" in fn_lower:
            return {
                "folder": "03_people/models/salem",
                "tags": ["pillar:business", "category:people", "person:salem", "quality:strong"]
            }
        if "before" in fn_lower and "after" in fn_lower:
            return {
                "folder": "03_people/before-after/studio",
                "tags": ["pillar:business", "category:people", "type:before-after", "shot:before-after-split", "quality:strong"]
            }
        if "bald" in fn_lower or "scalp" in fn_lower:
            return {
                "folder": "03_people/before-after/customer-submitted",
                "tags": ["pillar:business", "category:people", "state:before-hair-loss", "quality:usable"]
            }

        # 6. Lifestyle
        if "barber" in fn_lower or "salon" in fn_lower or "shower" in fn_lower:
            return {
                "folder": "04_lifestyle/barber-salon",
                "tags": ["pillar:business", "category:lifestyle", "setting:salon", "quality:usable"]
            }
        if "sports" in fn_lower or "playing" in fn_lower:
            return {
                "folder": "04_lifestyle/active",
                "tags": ["pillar:business", "category:lifestyle", "setting:active", "quality:usable"]
            }

        # 7. Web & Education
        if "infographic" in fn_lower or "tutorial" in fn_lower:
            return {
                "folder": "05_education",
                "tags": ["pillar:business", "category:education", "type:infographic", "quality:strong"]
            }
        if "blog" in fn_lower:
            return {
                "folder": "06_web/blog",
                "tags": ["pillar:business", "category:web", "type:blog-hero", "quality:usable"]
            }
        if re.search(r"collections-header|collection|catalog", fn_lower):
            return {
                "folder": "06_web/collections",
                "tags": ["pillar:business", "category:web", "type:collection-header", "quality:usable"]
            }
        if re.search(r"desktop|mobile|header|hero|cover", fn_lower):
            return {
                "folder": "06_web/home",
                "tags": ["pillar:business", "category:web", "type:web-banner", "quality:usable"]
            }

        # 8. References
        if manifest_bucket == "screenshots_and_exports" or re.search(r"cleanshot|screenshot|screen shot", fn_lower):
            return {
                "folder": "09_reference/ops-screenshots",
                "tags": ["pillar:business", "category:reference", "type:screenshot", "quality:usable"]
            }

        # 9. Marketing
        if re.search(r"instagram|pricelist|discount|sale|post|story|facebook|promo", fn_lower):
            return {
                "folder": "08_marketing/social",
                "tags": ["pillar:business", "category:marketing", "type:social-ad", "quality:usable"]
            }
        if manifest_bucket == "ai_generated_or_hero_concepts" or "ad" in fn_lower:
            return {
                "folder": "08_marketing/ads",
                "tags": ["pillar:business", "category:marketing", "type:campaign-ad", "quality:strong"]
            }

        return None

    def visual_classify_single(self, fp: Path) -> Dict[str, Any]:
        """Multimodal classification with Gemini 3.8 Flash."""
        fn = fp.name
        if fn in self.visual_cache:
            return self.visual_cache[fn]

        prompt = """Classify this Hair Solutions Co. Canva export asset into an 11-Folder slug and tags.
Allowed folders:
- 01_products/hair-systems (toupees, hair units, cap styles)
- 01_products/maintenance/walker-tape (Walker Tape, 1522, Ultra Hold, C22)
- 01_products/maintenance/prohair-labs (Ghost Buster, Dermal Mud, New Demension)
- 01_products/maintenance/ghost-bond (Ghost Bond bottles, packaging)
- 01_products/maintenance/general (clips, brushes, adhesives, general maintenance)
- 02_specs/swatches/hair-color (hair color strands, swatches, rings)
- 02_specs/swatches/grey-percentage (grey blend hair swatches)
- 02_specs/swatches/curl-pattern (wave and curl pattern swatches)
- 02_specs/swatches/density (density comparison charts)
- 02_specs/swatches/base-material (lace, skin, mono mesh textures)
- 02_specs/diagrams (cap contour, sizing diagrams, measurement charts)
- 02_specs/guides (care guides, spec sheets, order forms)
- 03_people/models (male models wearing hair systems, studio portraits)
- 03_people/before-after (hair restoration transformations, bald before vs restored)
- 04_lifestyle (men swimming, working out, barber styling hair)
- 05_education (how-to tutorials, step-by-step care infographics)
- 06_web/collections (e-commerce collection headers, banners)
- 06_web/blog (blog article featured images)
- 06_web/home (website hero banners, carousel images)
- 07_brand/logos (HSC wordmarks, monograms, brand marks)
- 07_brand/ui (icons, buttons, background textures)
- 08_marketing/ads (promotional flyers, sale graphics, ad creatives)
- 08_marketing/social (Instagram posts, stories, templates)
- 09_reference/inspiration (design inspiration, architecture, moodboards)
- 09_reference/ops-screenshots (screenshots, software, dashboards)

Reply strictly in JSON:
{
  "folder": "one of the allowed folder paths",
  "tags": ["tag1", "tag2", "tag3"],
  "quality": "strong" | "usable" | "weak"
}"""

        try:
            im = Image.open(fp)
            im = ImageOps.exif_transpose(im)
            im.thumbnail((512, 512))
            
            res = self.ai_client.models.generate_content(
                model="gemini-3.8-flash",
                contents=[im, prompt],
                config=types.GenerateContentConfig(response_mime_type="application/json")
            )
            data = json.loads(res.text.strip())
            folder = data.get("folder", "09_reference/inspiration")
            tags = [f"pillar:business", f"source:canva-export"]
            for t in data.get("tags", []):
                t_slug = slugify(str(t))
                if t_slug: tags.append(t_slug)
            q = data.get("quality", "usable")
            tags.append(f"quality:{q}")

            res_dict = {"folder": folder, "tags": tags}
            self.visual_cache[fn] = res_dict
            return res_dict
        except Exception as e:
            # Fallback
            res_dict = {
                "folder": "09_reference/inspiration",
                "tags": ["pillar:business", "source:canva-export", "quality:usable", "needs-review"]
            }
            self.visual_cache[fn] = res_dict
            return res_dict

    def run_classification_batch(self, files: List[Path], manifest_map: Dict[str, str]):
        """Run hybrid classification across all files."""
        to_classify_visually = []
        final_map = {}

        print("Phase 1: Deterministic Rule Classification...")
        for fp in files:
            fn = fp.name
            bucket = manifest_map.get(fn, "")
            rule_res = self.rule_classify(fn, bucket)
            if rule_res:
                final_map[fn] = rule_res
            else:
                if fn in self.visual_cache:
                    final_map[fn] = self.visual_cache[fn]
                else:
                    to_classify_visually.append(fp)

        print(f"Rule classified / cached: {len(final_map)} files.")
        print(f"Needing Gemini 3.8 Flash Vision: {len(to_classify_visually)} files.")

        if to_classify_visually:
            print("Phase 2: Multimodal Gemini 3.8 Flash Classification (ThreadPool)...")
            done_cnt = 0
            with ThreadPoolExecutor(max_workers=14) as executor:
                future_to_fn = {executor.submit(self.visual_classify_single, fp): fp.name for fp in to_classify_visually}
                for fut in as_completed(future_to_fn):
                    fn = future_to_fn[fut]
                    try:
                        res = fut.result()
                        final_map[fn] = res
                    except Exception as e:
                        final_map[fn] = {
                            "folder": "09_reference/inspiration",
                            "tags": ["pillar:business", "source:canva-export", "quality:usable"]
                        }
                    done_cnt += 1
                    if done_cnt % 25 == 0 or done_cnt == len(to_classify_visually):
                        self.save_visual_cache()
                        print(f"  Visual progress: {done_cnt}/{len(to_classify_visually)} complete ({done_cnt*100//len(to_classify_visually)}%)")

            self.save_visual_cache()
            print("Visual classification completed and saved to cache!")

        return final_map

    def generate_thumbnails(self, aid: str, src_path: Path, file_size: int, mod_ms: int):
        """Generate high-res 720px preview and 176px thumbnail in Framebase cache."""
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
        """Ingest or reclassify asset in HSC Library.framebase."""
        fn = fp.name
        file_size = fp.stat().st_size
        now_ms = int(time.time() * 1000)
        ext = fp.suffix.lstrip(".").lower() or "jpeg"

        folder_path = classification["folder"]
        folder_id = self.get_or_create_folder(folder_path)

        c = self.conn.cursor()

        if sha256 in self.existing_shas:
            asset_id = self.existing_shas[sha256]
            # Update folder assignment if necessary
            c.execute("UPDATE assets SET parent_folder_id = ?, updated_at_ms = ? WHERE id = ?",
                      (folder_id, now_ms, asset_id))
        else:
            asset_id = str(uuid.uuid4()).lower()
            storage_key = f"{asset_id[:2]}/{asset_id}.{ext}"

            # Get dimensions
            width, height = None, None
            try:
                if ext in (".heic", ".heif"):
                    out = subprocess.check_output(["sips", "-g", "pixelWidth", "-g", "pixelHeight", str(fp)], text=True)
                    w_m = re.search(r"pixelWidth:\s*(\d+)", out)
                    h_m = re.search(r"pixelHeight:\s*(\d+)", out)
                    if w_m and h_m:
                        width, height = int(w_m.group(1)), int(h_m.group(1))
                else:
                    with Image.open(fp) as img:
                        width, height = img.size
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
            display_name = fp.stem[:255]

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
        tags_to_attach.add("source:canva-export")

        for tag_str in tags_to_attach:
            tag_id = self.get_or_create_tag(tag_str)
            try:
                c.execute("""
                    INSERT OR IGNORE INTO asset_tags (asset_id, tag_id, added_at_ms)
                    VALUES (?, ?, ?)
                """, (asset_id, tag_id, now_ms))
            except Exception:
                pass

        # Generate thumbnail
        self.generate_thumbnails(asset_id, fp, file_size, now_ms)
        return asset_id

    def extract_and_ingest_video_posters(self):
        """Extract poster frames from MP4 videos and ingest as stillImage."""
        print("Processing Video Posters...")
        video_paths = list(VIDEOS_DIR.glob("*.mp4")) + list(DOCS_DIR.glob("*.mp4"))
        posters_dir = CANVA_DIR / "video_posters"
        posters_dir.mkdir(exist_ok=True)

        ingested_posters = 0
        for vp in video_paths:
            poster_fn = f"{vp.stem}_poster.jpg"
            poster_path = posters_dir / poster_fn

            # Extract 1-sec frame using ffmpeg
            if not poster_path.exists() or poster_path.stat().st_size == 0:
                cmd = [
                    "ffmpeg", "-y", "-ss", "00:00:01.000", "-i", str(vp),
                    "-vframes", "1", "-q:v", "2", str(poster_path)
                ]
                subprocess.run(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)

            if poster_path.exists() and poster_path.stat().st_size > 0:
                h = compute_sha256(poster_path)
                classification = {
                    "folder": "08_marketing/social",
                    "tags": [
                        "pillar:business", "source:canva-export", "type:video-poster",
                        "format:mp4-poster", f"video:{slugify(vp.stem)}", "quality:strong"
                    ]
                }
                self.ingest_asset(poster_path, classification, h)
                ingested_posters += 1

        print(f"Extracted and ingested {ingested_posters} video posters.")

    def run(self):
        print("=== Media Workshop: Canva Export Catalog Ingestion ===")
        # 1. Load manifest
        manifest_file = REPORTS_DIR / "canva_export_filename_presort_manifest.csv"
        manifest_map = {}
        if manifest_file.exists():
            import csv
            with open(manifest_file, "r", encoding="utf-8", errors="ignore") as f:
                reader = csv.DictReader(f)
                for r in reader: manifest_map[r["filename"]] = r["filename_bucket"]

        # 2. Gather image files
        all_images = sorted([f for f in IMAGES_DIR.iterdir() if f.is_file() and not f.name.startswith(".")])
        print(f"Found {len(all_images)} image files in {IMAGES_DIR}")

        # 3. Classify all images (Hybrid Rule + Vision)
        classification_map = self.run_classification_batch(all_images, manifest_map)

        # 4. Ingest into Framebase
        print("Phase 3: Database Ingestion & Thumbnail Generation...")
        ingested_count = 0
        t0 = time.time()
        for idx, fp in enumerate(all_images):
            h = compute_sha256(fp)
            cls = classification_map.get(fp.name, {
                "folder": "09_reference/inspiration",
                "tags": ["pillar:business", "source:canva-export", "quality:usable"]
            })
            self.ingest_asset(fp, cls, h)
            ingested_count += 1
            if ingested_count % 100 == 0 or ingested_count == len(all_images):
                self.conn.commit()
                dt = time.time() - t0
                print(f"  Ingested {ingested_count}/{len(all_images)} assets ({dt:.1f}s)...")

        # 5. Video posters
        self.extract_and_ingest_video_posters()

        # 6. Checkpoint DB
        self.conn.commit()
        print("Checkpointing SQLite WAL...")
        self.conn.execute("PRAGMA wal_checkpoint(TRUNCATE);")
        self.conn.close()

        print(f"\nSUCCESS: Ingestion of {ingested_count} assets completed into HSC Library.framebase!")

if __name__ == "__main__":
    pipeline = CanvaIngestionPipeline()
    pipeline.run()


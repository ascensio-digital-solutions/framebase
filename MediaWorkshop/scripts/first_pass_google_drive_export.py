#!/usr/bin/env python3
"""
First-Pass Cleansing & Visual Inspection for Google Drive Images Export.

Target: /Users/vincent/Downloads/Google Drive Images Export (14,286 files)
Vision Engine: OpenRouter API (nvidia/nemotron-3.5-super-vl:free with openrouter/free fallback)

Objectives:
1. Exact SHA-256 Deduplication & Cross-Catalog Reconciliation (HSC vs Personal vs Knowledge).
2. Deep Visual Cleansing focused on High-Risk Batches (camera files, WhatsApp, selfies, sensitive screenshots).
3. Separation of Personal/Private photos from Commercial Hair Solutions Co. assets.
4. Incremental caching to scripts/google_drive_cleansing_cache.json.
5. Production of a comprehensive cleansing report and CSV manifest.
"""

import os
import sys
import io
import re
import json
import time
import base64
import hashlib
import sqlite3
import requests
import threading
from pathlib import Path
from typing import Dict, Any, Optional, Tuple, List
from collections import defaultdict, Counter
from concurrent.futures import ThreadPoolExecutor, as_completed
from PIL import Image, ImageOps, ImageFile

ImageFile.LOAD_TRUNCATED_IMAGES = True
Image.MAX_IMAGE_PIXELS = None

# Directories
WORKSPACE_DIR = Path("/Users/vincent/04_systems/media_workshop")
DRIVE_EXPORT_DIR = Path("/Users/vincent/Downloads/Google Drive Images Export")
OUTPUTS_DIR = WORKSPACE_DIR / "outputs"
OUTPUTS_DIR.mkdir(exist_ok=True)

CACHE_FILE = WORKSPACE_DIR / "scripts/google_drive_cleansing_cache.json"
MANIFEST_CSV = OUTPUTS_DIR / "google_drive_cleansing_manifest.csv"
DUPLICATES_CSV = OUTPUTS_DIR / "google_drive_duplicates.csv"

# Load OpenRouter API Key
API_KEY = None
env_path = Path.home() / ".env"
if env_path.exists():
    with open(env_path) as f:
        for line in f:
            line = line.strip()
            if line.startswith("OPENROUTER_API_KEY="):
                API_KEY = line.split("=", 1)[1].strip("\"'\''")
                break

if not API_KEY:
    raise ValueError("OPENROUTER_API_KEY not found in ~/.env")

OPENROUTER_URL = "https://openrouter.ai/api/v1/chat/completions"
HEADERS = {
    "Authorization": f"Bearer {API_KEY}",
    "Content-Type": "application/json",
    "HTTP-Referer": "https://hairsolutions.co",
    "X-Title": "Media Workshop Cleansing"
}

PRIMARY_MODEL = "nvidia/nemotron-3.5-super-vl:free"
FALLBACK_MODEL = "openrouter/free"

class GoogleDriveCleanser:
    def __init__(self):
        self.lock = threading.Lock()
        self.libraries = {
            "hsc": Path.home() / "Pictures/HSC Library.framebase/Catalog/catalog.sqlite",
            "personal": Path.home() / "Pictures/Personal Library.framebase/Catalog/catalog.sqlite",
            "knowledge": Path.home() / "Pictures/Knowledge Library.framebase/Catalog/catalog.sqlite",
        }
        self.catalog_hashes = self.load_catalog_hashes()
        self.cache = self.load_cache()

    def load_catalog_hashes(self) -> Dict[str, List[str]]:
        hashes = defaultdict(list)
        for lib_name, db_path in self.libraries.items():
            if db_path.exists():
                try:
                    conn = sqlite3.connect(db_path)
                    c = conn.cursor()
                    c.execute("SELECT sha256 FROM asset_content_identity WHERE sha256 IS NOT NULL")
                    for r in c.fetchall():
                        hashes[r[0]].append(lib_name)
                    conn.close()
                except Exception as e:
                    print(f"Warning: Could not read {lib_name} catalog: {e}")
        print(f"Loaded {len(hashes)} unique hashes across existing Framebase catalogs.")
        return hashes

    def load_cache(self) -> Dict[str, Any]:
        if CACHE_FILE.exists():
            try:
                with open(CACHE_FILE, "r", encoding="utf-8") as f:
                    data = json.load(f)
                print(f"Loaded {len(data)} cached classifications from {CACHE_FILE.name}")
                return data
            except Exception as e:
                print(f"Could not load cache: {e}")
        return {}

    def save_cache(self):
        with self.lock:
            cache_copy = dict(self.cache)
        tmp = CACHE_FILE.with_suffix(".tmp")
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(cache_copy, f, indent=2)
        tmp.replace(CACHE_FILE)

    def hash_all_files(self, file_paths: List[Path]) -> Dict[str, Dict[str, Any]]:
        """Fast multi-threaded SHA-256 calculation."""
        print(f"Computing SHA-256 for {len(file_paths)} files...")
        file_data = {}

        def _hash_one(fp):
            h = hashlib.sha256()
            try:
                sz = fp.stat().st_size
                with open(fp, "rb") as f:
                    while chunk := f.read(1024 * 1024):
                        h.update(chunk)
                return fp.name, h.hexdigest(), sz, None
            except Exception as e:
                return fp.name, None, 0, str(e)

        t0 = time.time()
        with ThreadPoolExecutor(max_workers=10) as executor:
            for fn, sha, sz, err in executor.map(_hash_one, file_paths):
                if sha:
                    file_data[fn] = {"sha256": sha, "size_bytes": sz}
                else:
                    file_data[fn] = {"sha256": None, "size_bytes": sz, "error": err}

        dt = time.time() - t0
        print(f"Hashing completed in {dt:.2f}s ({len(file_data)} files).")
        return file_data

    def classify_visually_openrouter(self, fp: Path, retry_with_fallback: bool = True) -> Dict[str, Any]:
        """Classify single image using OpenRouter free vision model."""
        fn = fp.name
        with self.lock:
            if fn in self.cache:
                return self.cache[fn]

        prompt = """You are an expert image classifier distinguishing Business assets from Personal/Private photos.
Context:
- Business: Hair Solutions Co. hair systems (toupees, lace bases, hair swatches, styling products, models, marketing ads, technical diagrams).
- Personal/Private: Selfies, gym/beach/vacation photos, personal memories, intimate/private photos, personal documents/receipts.
- Reference Ops: Software screenshots, API dashboards, code, administrative screenshots.

Analyze the image and return strictly valid JSON:
{
  "pillar": "business" | "personal" | "reference_ops",
  "privacy_tier": "public_commercial" | "internal_ops" | "personal_private" | "sensitive_private",
  "is_private_or_personal": true | false,
  "category": "hair_system" | "maintenance_product" | "hair_spec_swatch" | "technical_diagram" | "commercial_model" | "lifestyle_salon" | "marketing_ad" | "system_screenshot" | "personal_photo" | "sensitive_private",
  "target_library": "HSC Library" | "Personal Library" | "Knowledge Library",
  "recommended_folder": "e.g. 01_products/hair-systems, 02_specs/diagrams, 03_people/models, 09_reference/ops-screenshots, 10_private/personal",
  "brief_description": "1 sentence describing what is visually shown"
}"""

        try:
            im = Image.open(fp)
            im = ImageOps.exif_transpose(im)
            im.thumbnail((512, 512))
            im = im.convert("RGB")
            buf = io.BytesIO()
            im.save(buf, format="JPEG", quality=85)
            b64 = base64.b64encode(buf.getvalue()).decode("utf-8")
        except Exception as e:
            res = {
                "pillar": "unknown",
                "privacy_tier": "unknown",
                "is_private_or_personal": False,
                "category": "unreadable",
                "target_library": "HSC Library",
                "recommended_folder": "00_inbox",
                "brief_description": f"Unreadable image: {e}"
            }
            with self.lock:
                self.cache[fn] = res
            return res

        models_to_try = [PRIMARY_MODEL]
        if retry_with_fallback:
            models_to_try.append(FALLBACK_MODEL)

        for model in models_to_try:
            payload = {
                "model": model,
                "messages": [
                    {
                        "role": "user",
                        "content": [
                            {"type": "text", "text": prompt},
                            {"type": "image_url", "image_url": {"url": f"data:image/jpeg;base64,{b64}"}}
                        ]
                    }
                ],
                "response_format": {"type": "json_object"}
            }

            try:
                resp = requests.post(OPENROUTER_URL, headers=HEADERS, json=payload, timeout=25)
                if resp.status_code == 200:
                    content = resp.json()["choices"][0]["message"]["content"].strip()
                    # Parse JSON
                    if content.startswith("```"):
                        content = re.sub(r"^```(?:json)?\n?", "", content)
                        content = re.sub(r"\n?```$", "", content)
                    data = json.loads(content)
                    with self.lock:
                        self.cache[fn] = data
                    return data
                elif resp.status_code == 429:
                    time.sleep(1.0)
                    continue
            except Exception:
                time.sleep(1.0)

        # Fallback default
        res = {
            "pillar": "business",
            "privacy_tier": "public_commercial",
            "is_private_or_personal": False,
            "category": "unclassified",
            "target_library": "HSC Library",
            "recommended_folder": "00_inbox",
            "brief_description": "Auto-fallback due to API timeout"
        }
        with self.lock:
            self.cache[fn] = res
        return res

    def run_first_pass(self, sample_size: Optional[int] = None):
        print("=== Media Workshop: Google Drive Export First-Pass Cleansing ===")
        all_files = sorted([f for f in DRIVE_EXPORT_DIR.iterdir() if f.is_file() and not f.name.startswith(".")])
        print(f"Total files in Google Drive Export: {len(all_files)}")

        # 1. Hashing & Deduplication
        file_info = self.hash_all_files(all_files)

        # Build duplicate & overlap map
        sha_to_files = defaultdict(list)
        for fn, info in file_info.items():
            if info.get("sha256"):
                sha_to_files[info["sha256"]].append(fn)

        # Write duplicates CSV
        with open(DUPLICATES_CSV, "w", encoding="utf-8") as f:
            f.write("sha256,count,filenames,catalog_matches\n")
            for sha, fns in sha_to_files.items():
                cat_matches = "|".join(self.catalog_hashes.get(sha, []))
                if len(fns) > 1 or cat_matches:
                    f.write(f'"{sha}",{len(fns)},"{"|".join(fns)}","{cat_matches}"\n')

        # 2. Identify High-Risk Personal/Private Candidates & Rule Buckets
        high_risk_files = []
        rule_classified = {}

        for fp in all_files:
            fn = fp.name
            fn_lower = fn.lower()
            sha = file_info[fn].get("sha256")

            # Check existing catalog presence first
            if sha in self.catalog_hashes:
                libs = self.catalog_hashes[sha]
                if "personal" in libs:
                    rule_classified[fn] = {
                        "pillar": "personal", "privacy_tier": "personal_private",
                        "is_private_or_personal": True, "category": "personal_photo",
                        "target_library": "Personal Library", "recommended_folder": "10_private/personal",
                        "brief_description": "Exact match already in Personal Library"
                    }
                    continue
                elif "hsc" in libs:
                    rule_classified[fn] = {
                        "pillar": "business", "privacy_tier": "public_commercial",
                        "is_private_or_personal": False, "category": "existing_hsc_asset",
                        "target_library": "HSC Library", "recommended_folder": "01_products/hair-systems",
                        "brief_description": "Exact match already in HSC Library"
                    }
                    continue

            # High risk pattern checks
            is_camera = bool(re.search(r"^IMG_\d+|^DSC_?\d+|^PHOTO|Facetune|selfie", fn, re.IGNORECASE))
            is_whatsapp = bool(re.search(r"WhatsApp\s*Image|WA\d+", fn, re.IGNORECASE))
            is_personal_name = bool(re.search(r"passport|license|id_card|carte_identite|tax|bank|statement|facture", fn_lower))

            if is_camera or is_whatsapp or is_personal_name:
                high_risk_files.append(fp)
            elif re.search(r"cleanshot|screenshot|screen\s*shot", fn_lower):
                # Deterministic screenshot rule
                rule_classified[fn] = {
                    "pillar": "reference_ops", "privacy_tier": "internal_ops",
                    "is_private_or_personal": False, "category": "system_screenshot",
                    "target_library": "HSC Library", "recommended_folder": "09_reference/ops-screenshots",
                    "brief_description": "CleanShot / Desktop screenshot"
                }
            elif re.search(r"^#\d+[a-zA-Z]*|color\s*#", fn_lower):
                rule_classified[fn] = {
                    "pillar": "business", "privacy_tier": "public_commercial",
                    "is_private_or_personal": False, "category": "hair_spec_swatch",
                    "target_library": "HSC Library", "recommended_folder": "02_specs/swatches/hair-color",
                    "brief_description": "Hair color swatch specification"
                }
            elif re.search(r"walker|prohair|phl-|ghostbond|ghost-bond|sunshine|lux\s*hair", fn_lower):
                rule_classified[fn] = {
                    "pillar": "business", "privacy_tier": "public_commercial",
                    "is_private_or_personal": False, "category": "maintenance_product",
                    "target_library": "HSC Library", "recommended_folder": "01_products/maintenance",
                    "brief_description": "Hair system maintenance product"
                }

        print(f"\nRule Classified / Pre-matched: {len(rule_classified)} files.")
        print(f"High-Risk Files flagged for Deep Vision Inspection: {len(high_risk_files)} files.")

        # 3. Deep Vision Inspection on High-Risk Candidates using OpenRouter
        targets_to_inspect = high_risk_files
        if sample_size and len(targets_to_inspect) > sample_size:
            targets_to_inspect = targets_to_inspect[:sample_size]

        print(f"\nRunning OpenRouter Vision ({PRIMARY_MODEL}) on {len(targets_to_inspect)} high-risk files...")
        uncached = [fp for fp in targets_to_inspect if fp.name not in self.cache]
        print(f"  Already in cache: {len(targets_to_inspect) - len(uncached)}, To query: {len(uncached)}")

        t0 = time.time()
        completed = 0
        with ThreadPoolExecutor(max_workers=10) as executor:
            future_to_fn = {executor.submit(self.classify_visually_openrouter, fp): fp.name for fp in uncached}
            for fut in as_completed(future_to_fn):
                fn = future_to_fn[fut]
                try:
                    res = fut.result()
                except Exception as e:
                    res = {"error": str(e)}
                completed += 1
                if completed % 20 == 0 or completed == len(uncached):
                    self.save_cache()
                    dt = time.time() - t0
                    print(f"  Vision progress: {completed}/{len(uncached)} ({completed*100//len(uncached)}%) - {dt:.1f}s")

        self.save_cache()

        # 4. Compile Cleansing Results & Write Manifest
        print("\nCompiling Master Cleansing Manifest...")
        private_personal_detected = 0
        business_detected = 0
        ops_detected = 0

        with open(MANIFEST_CSV, "w", encoding="utf-8") as f:
            f.write("filename,sha256,size_bytes,pillar,privacy_tier,is_private_or_personal,category,target_library,recommended_folder,description\n")
            
            for fp in all_files:
                fn = fp.name
                sha = file_info[fn].get("sha256", "")
                sz = file_info[fn].get("size_bytes", 0)
                
                # Check cache first, then rule
                if fn in self.cache:
                    meta = self.cache[fn]
                elif fn in rule_classified:
                    meta = rule_classified[fn]
                else:
                    meta = {
                        "pillar": "business", "privacy_tier": "public_commercial",
                        "is_private_or_personal": False, "category": "canva_graphic",
                        "target_library": "HSC Library", "recommended_folder": "08_marketing",
                        "brief_description": "Canva / Drive graphic export"
                    }

                is_priv = meta.get("is_private_or_personal", False)
                pillar = meta.get("pillar", "business")
                if is_priv or pillar == "personal":
                    private_personal_detected += 1
                elif pillar == "reference_ops":
                    ops_detected += 1
                else:
                    business_detected += 1

                desc = meta.get("brief_description", "").replace('"', '""')
                f.write(f'"{fn}","{sha}",{sz},"{pillar}","{meta.get("privacy_tier")}","{is_priv}","{meta.get("category")}","{meta.get("target_library")}","{meta.get("recommended_folder")}","{desc}"\n')

        print(f"\nCleansing First Pass Completed!")
        print(f"  Manifest written: {MANIFEST_CSV}")
        print(f"  Duplicates list: {DUPLICATES_CSV}")
        print(f"  Personal / Private photos flagged: {private_personal_detected}")
        print(f"  Business commercial assets: {business_detected}")
        print(f"  Reference / Ops screenshots: {ops_detected}")

if __name__ == "__main__":
    cleanser = GoogleDriveCleanser()
    # Run full high-risk first pass (inspects all ~880 high risk camera/WhatsApp files)
    cleanser.run_first_pass()


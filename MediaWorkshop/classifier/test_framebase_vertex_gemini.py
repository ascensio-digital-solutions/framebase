#!/usr/bin/env python3
"""
Test Runner: Vertex AI Gemini 3.8 Flash on HSC Framebase Library.
Pulls a clean, curated slice of products and models from ~/Pictures/HSC Library.framebase,
runs inference via Google Cloud Vertex AI (project: ascensio-media-os),
and writes structured visual assessments and tags directly into Framebase's catalog.sqlite.
"""

import os
import sys
import time
import json
import base64
import io
import uuid
import hashlib
import sqlite3
from pathlib import Path
from typing import Dict, Any, List, Optional, Tuple
from PIL import Image, ImageFile
from pillow_heif import register_heif_opener
import httpx
import google.auth
import google.auth.transport.requests

register_heif_opener()
ImageFile.LOAD_TRUNCATED_IMAGES = True

SCRIPT_DIR = Path(__file__).parent.resolve()
PICTURES_DIR = Path(os.path.expanduser("~/Pictures"))
HSC_LIB = PICTURES_DIR / "HSC Library.framebase"
CATALOG_DB = HSC_LIB / "Catalog" / "catalog.sqlite"
ORIGINALS_DIR = HSC_LIB / "Originals"

PROJECT_ID = "ascensio-media-os"
LOCATION = "global"
MODEL_NAME = "gemini-3.8-flash"
ENDPOINT = f"https://aiplatform.googleapis.com/v1/projects/{PROJECT_ID}/locations/{LOCATION}/publishers/google/models/{MODEL_NAME}:generateContent"

PROMPT = """Analyze this Hair Solutions Co photo (men's non-surgical hair replacement systems, swatches, base construction, client before/afters, and model portraits).

Return strictly a JSON object conforming to:
{
  "business_quality": "strong" | "usable" | "weak",
  "photo_role": "beforeCandidate" | "afterCandidate" | "comparisonCandidate" | "productDetail" | "modelPortrait" | "heroImage" | "other",
  "hairline_presentation": "clearlyVisible" | "partiallyVisible" | "notVisible" | "unclear",
  "confidence": float between 0.0 and 1.0,
  "rationale": "Clear, concise rationale detailing the hair system, base type (lace, poly skin, mono), hairline visibility, lighting, and model presentation.",
  "tags": ["namespace:value", ...]
}

TAGGING GUIDELINES:
- Base materials: base:poly-skin, base:swiss-lace, base:french-lace, base:mono-mesh
- Products: product:hair-system, product:swatch, product:cap
- Hairline: hairline:clearly-visible, hairline:receding, hairline:undetectable, hairline:not-visible
- Shots: shot:macro-base, shot:front-portrait, shot:side-profile, shot:top-down
- Quality: quality:strong, quality:usable, quality:weak
"""

def deterministic_uuid(val: str) -> str:
    return str(uuid.uuid5(uuid.NAMESPACE_DNS, val)).lower()

def slugify(text: str) -> str:
    import re
    text = text.lower().strip()
    text = re.sub(r"[^\w\s-]", "", text)
    text = re.sub(r"[\s_]+", "-", text)
    return text[:64].strip("-")

class VertexGeminiClient:
    def __init__(self, project_id: str = PROJECT_ID):
        self.project_id = project_id
        self.creds, _ = google.auth.default(
            scopes=["https://www.googleapis.com/auth/cloud-platform"]
        )
        self.last_refresh = 0.0

    def refresh_token_if_needed(self):
        now = time.time()
        if not self.creds.token or (now - self.last_refresh) > 1500:
            req = google.auth.transport.requests.Request()
            self.creds.refresh(req)
            self.last_refresh = now

    def generate_assessment(self, b64_jpeg: str) -> Optional[Dict[str, Any]]:
        self.refresh_token_if_needed()
        headers = {
            "Authorization": f"Bearer {self.creds.token}",
            "Content-Type": "application/json",
            "x-goog-user-project": self.project_id,
        }
        payload = {
            "contents": [
                {
                    "role": "user",
                    "parts": [
                        {"text": PROMPT},
                        {"inlineData": {"mimeType": "image/jpeg", "data": b64_jpeg}},
                    ],
                }
            ],
            "generationConfig": {
                "responseMimeType": "application/json",
                "temperature": 0.1,
            },
        }

        with httpx.Client(timeout=30.0) as client:
            resp = client.post(ENDPOINT, headers=headers, json=payload)
            if resp.status_code != 200:
                print(f"Vertex AI Error {resp.status_code}: {resp.text}")
                return None
            data = resp.json()
            try:
                candidate = data["candidates"][0]["content"]["parts"][0]["text"]
                return json.loads(candidate)
            except Exception as e:
                print(f"Failed to parse model JSON: {e}")
                return None

def prepare_image(path: Path) -> Tuple[Optional[str], Optional[str]]:
    """Returns (b64_jpeg, derivative_sha256)."""
    try:
        with Image.open(path) as img:
            img.thumbnail((1024, 1024), Image.Resampling.LANCZOS)
            if img.mode != "RGB":
                img = img.convert("RGB")
            buf = io.BytesIO()
            img.save(buf, format="JPEG", quality=85)
            bytes_val = buf.getvalue()
            sha256 = hashlib.sha256(bytes_val).hexdigest().lower()
            b64_str = base64.b64encode(bytes_val).decode("utf-8")
            return b64_str, sha256
    except Exception as e:
        print(f"Could not load/process image {path.name}: {e}")
        return None, None

def get_or_create_tag(conn: sqlite3.Connection, raw_tag: str) -> str:
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
    c = conn.cursor()
    c.execute("SELECT id FROM tags WHERE name COLLATE NOCASE = ?", (full_name,))
    row = c.fetchone()
    if row:
        return row[0]

    tag_id = deterministic_uuid(f"framebase-tag:{full_name}")
    now_ms = int(time.time() * 1000)
    try:
        c.execute("""
            INSERT INTO tags (id, namespace, value, name, created_at_ms, updated_at_ms)
            VALUES (?, ?, ?, ?, ?, ?)
        """, (tag_id, ns, val, full_name, now_ms, now_ms))
        conn.commit()
    except sqlite3.IntegrityError:
        c.execute("SELECT id FROM tags WHERE name COLLATE NOCASE = ?", (full_name,))
        row = c.fetchone()
        if row:
            return row[0]
    return tag_id

def main():
    print("=" * 80)
    print("VERTEX AI GEMINI 3.8 FLASH — FRAMEBASE TEST RUNNER")
    print(f"Target Library:  {HSC_LIB.name}")
    print(f"GCP Project:     {PROJECT_ID} (Vertex AI Billing)")
    print(f"Model:           {MODEL_NAME}")
    print("=" * 80)

    conn = sqlite3.connect(str(CATALOG_DB), timeout=60.0)
    conn.execute("PRAGMA journal_mode=WAL;")
    c = conn.cursor()

    # Select 10 products and 10 models
    c.execute("""
        SELECT a.id, a.filename, a.storage_key, f.name as folder_name
        FROM assets a
        JOIN folders f ON a.parent_folder_id = f.id
        WHERE f.name = 'hair-systems'
        ORDER BY a.imported_at_ms DESC
        LIMIT 10
    """)
    product_rows = c.fetchall()

    c.execute("""
        SELECT a.id, a.filename, a.storage_key, f.name as folder_name
        FROM assets a
        JOIN folders f ON a.parent_folder_id = f.id
        WHERE f.name = 'models'
        ORDER BY a.imported_at_ms DESC
        LIMIT 10
    """)
    model_rows = c.fetchall()

    test_assets = product_rows + model_rows
    print(f"\nLoaded {len(test_assets)} target assets ({len(product_rows)} hair-systems + {len(model_rows)} models).\n")

    client = VertexGeminiClient(PROJECT_ID)
    results = []

    for idx, (asset_id, fn, storage_key, folder_name) in enumerate(test_assets, 1):
        img_path = ORIGINALS_DIR / storage_key
        if not img_path.exists():
            print(f"[{idx}/{len(test_assets)}] Skipped {fn} (file missing on disk)")
            continue

        t0 = time.time()
        b64_jpeg, deriv_sha = prepare_image(img_path)
        if not b64_jpeg or not deriv_sha:
            continue

        assessment = client.generate_assessment(b64_jpeg)
        elapsed = time.time() - t0

        if not assessment:
            print(f"[{idx}/{len(test_assets)}] {fn}: Vertex AI call failed")
            continue

        # Standardize fields
        biz_quality = assessment.get("business_quality", "usable")
        if biz_quality not in ("strong", "usable", "weak"):
            biz_quality = "usable"

        role = assessment.get("photo_role", "productDetail")
        hairline = assessment.get("hairline_presentation", "notVisible")
        conf = float(assessment.get("confidence") or 0.9)
        rat = assessment.get("rationale") or f"Assessed by Vertex AI {MODEL_NAME}"
        tags = assessment.get("tags") or []

        now_ms = int(time.time() * 1000)
        assessment_id = deterministic_uuid(f"assessment:{asset_id}:{MODEL_NAME}:vertex:v2")

        # Save assessment to catalog.sqlite
        c.execute("""
            INSERT OR REPLACE INTO visual_assessments (
                id, asset_id, business_quality, evidence_json, photo_role, hairline_presentation,
                confidence, rationale, provider, model_identifier, assessment_schema_version,
                derivative_sha256, derivative_maximum_pixel_dimension, captured_at_ms, created_at_ms, updated_at_ms
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, 'vertex', ?, 2, ?, 1024, ?, ?, ?)
        """, (
            assessment_id, asset_id, biz_quality, json.dumps([]), role, hairline,
            conf, rat, MODEL_NAME, deriv_sha, now_ms, now_ms, now_ms
        ))

        # Save tags to asset_tags
        tag_count = 0
        for t in tags:
            tag_id = get_or_create_tag(conn, str(t))
            try:
                c.execute("""
                    INSERT OR IGNORE INTO asset_tags (asset_id, tag_id, added_at_ms)
                    VALUES (?, ?, ?)
                """, (asset_id, tag_id, now_ms))
                tag_count += 1
            except Exception:
                pass

        conn.commit()

        print(f"[{idx:2d}/{len(test_assets)}] {folder_name:12} | {fn:14} | Quality: {biz_quality:6} | Hairline: {hairline:16} | Role: {role:14} | {elapsed:.2f}s")
        print(f"     Rationale: {rat[:100]}...")
        print(f"     Tags ({len(tags)}): {', '.join(tags[:5])}\n")

        results.append({
            "filename": fn,
            "folder": folder_name,
            "quality": biz_quality,
            "role": role,
            "hairline": hairline,
            "confidence": conf,
            "tags": tags,
            "rationale": rat,
            "latency": elapsed
        })

    conn.close()

    print("=" * 80)
    print(f"TEST RUN COMPLETE: Successfully processed {len(results)}/{len(test_assets)} assets!")
    print(f"All visual assessments & tags written to: {CATALOG_DB.name}")
    print("=" * 80)

if __name__ == "__main__":
    main()


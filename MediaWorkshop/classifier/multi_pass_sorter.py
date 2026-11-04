#!/usr/bin/env python3
"""
Multi-Pass Media Sorter & Screenshot Repo Scout (Track 2 — Framebase 2.0 Media Workshop).

Powered by Google Cloud Vertex AI (`ascensio-media-os`, location=`global`, model=`gemini-3.8-flash`)
authenticated via Application Default Credentials (`framebase-agent-sa@ascensio-media-os.iam.gserviceaccount.com`).

Architecture:
- Pass 1 (3-Pillar Gatekeeper):
    * Evaluates images from a local folder or Framebase `00_inbox`.
    * Hard rule: `privacy_flag` in ("intimate", "identity_document") -> quarantine (`06_private_quarantine`).
    * Hard rule: `subject_count == "multiple_people"` or `domain == "personal"` -> route to `Personal Library.framebase`
      (`01_people_and_family/friends`, `family`, `03_travel_and_places`, etc.) — NEVER into `03_people/models/<name>`!
    * Hard rule: `domain == "knowledge_and_tools"` -> route to Pass 2A (`Knowledge Library.framebase`).
    * Hard rule: `domain == "hair_solutions_co"` and `privacy_flag == "safe"` -> route to Pass 2B (`HSC Library.framebase`).
- Pass 2A (Screenshot & Repo Scout):
    * Inspects `knowledge_opportunity` on screenshots (`domain == "knowledge_and_tools"`).
    * Routes actionable open-source repos, CRMs, and AI tools into `Knowledge Library.framebase` under:
        - `ai_and_automation/open-source-repos`
        - `ai_and_automation/crm-and-sales`
        - `ai_and_automation/ai-agents-and-workflows`
        - `ai_and_automation/ui-ux-and-web`
        - `ai_and_automation/marketing-and-copy`
        - `ai_and_automation/general-reference`
    * Writes structured digests to:
        - `/Users/vincent/06_code/framebase/MediaWorkshop/reports/knowledge_repo_scout_digest.json`
        - `/Users/vincent/06_code/framebase/MediaWorkshop/reports/knowledge_repo_scout_digest.jsonl`
        - `/Users/vincent/06_code/framebase/MediaWorkshop/reports/knowledge_repo_scout_digest.md`
- Pass 2B (HSC Specialist Sub-Folder Sorter):
    * Enforces the Model Qualification Rule: A person only belongs in `03_people/models/<name>` if
      `subject_count == "single_person"` AND `model_shot_type != "not_model"`.
    * Routes qualified solo model shots into `03_people/models/<name>/<sub-folder>`:
        - `before-after` (`before_bald_thinning` or `before_after_split`)
        - `headshots` (`headshot_hairline`)
        - `editorial` (`editorial_lifestyle`)
        - `install-cut` (`install_cut_in`)
    * Sub-divides `02_specs/swatches` into:
        - `02_specs/swatches/hair-color/circle-swatches`
        - `02_specs/swatches/hair-color/ring-swatches`
        - `02_specs/swatches/hair-color/color-charts`
        - `02_specs/swatches/grey-percentage`
        - `02_specs/swatches/curl-pattern`
        - `02_specs/swatches/base-material`
"""

import argparse
import hashlib
import io
import json
import os
import re
import sqlite3
import sys
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import subprocess
import tempfile
from PIL import Image, ImageFile, ImageOps
from google import genai
from google.genai import types

try:
    from pillow_heif import register_heif_opener
    register_heif_opener()
except ImportError:
    pass
ImageFile.LOAD_TRUNCATED_IMAGES = True

SCRIPT_DIR = Path(__file__).parent.resolve()
MEDIA_WORKSHOP_DIR = SCRIPT_DIR.parent.resolve()
REPORTS_DIR = MEDIA_WORKSHOP_DIR / "reports"
STATE_DB = SCRIPT_DIR / "state.sqlite"

sys.path.insert(0, str(SCRIPT_DIR))
from taxonomy import (
    Category,
    Domain,
    KnowledgeOpportunity,
    PhotoClassification,
    Quality,
    Sensitivity,
)
try:
    from hair_concierge_brain import get_sorter_grounding_context, install_google_ipv4_dns_resolver
    install_google_ipv4_dns_resolver()
    HAIR_CONCIERGE_GROUNDING = "\n\n" + get_sorter_grounding_context(fetch_live_rag=True)
except Exception as _brain_err:
    print(f"[WARN] Could not load Hair Concierge Brain grounding: {_brain_err}", file=sys.stderr)
    HAIR_CONCIERGE_GROUNDING = ""

PROJECT_ID = "ascensio-media-os"
LOCATION = "global"
MODEL_NAME = "gemini-3.8-flash"

PICTURES_DIR = Path.home() / "Pictures"
HSC_LIB = PICTURES_DIR / "HSC Library.framebase"
PERSONAL_LIB = PICTURES_DIR / "Personal Library.framebase"
KNOWLEDGE_LIB = PICTURES_DIR / "Knowledge Library.framebase"
THUMB_CACHE_DIR = Path.home() / "Library/Caches/com.vincentlaroche.framebase/Thumbnails"

DEFAULT_SCREENSHOTS_DIR = Path("/Users/vincent/Downloads/Google Drive Images Export/reference_screenshots")
FALLBACK_SCREENSHOTS_DIR = Path("/Users/vincent/Downloads/Google Drive Images Export/isolated_reference_screenshots")
VINCENT_REF_DIR = MEDIA_WORKSHOP_DIR / "references/characters/vincent"

MODEL_SHOT_TO_SUBFOLDER = {
    "before_bald_thinning": "before-after",
    "before_after_split": "before-after",
    "headshot_hairline": "headshots",
    "editorial_lifestyle": "editorial",
    "install_cut_in": "install-cut",
}

SWATCH_SUBTYPE_TO_FOLDER = {
    "circle-swatches": "02_specs/swatches/hair-color/circle-swatches",
    "ring-swatches": "02_specs/swatches/hair-color/ring-swatches",
    "color-charts": "02_specs/swatches/hair-color/color-charts",
    "grey-percentage": "02_specs/swatches/grey-percentage",
    "curl-pattern": "02_specs/swatches/curl-pattern",
    "base-material": "02_specs/swatches/base-material",
}

SYSTEM_PROMPT = """You are the Framebase 2.0 Multi-Pass Vision Gatekeeper & Specialist Sorter for Hair Solutions Co. and Ascensio Digital.
Examine the provided image carefully (never rely on filename guesses alone) and return a structured `PhotoClassification` JSON object.

### STRICT 3-PILLAR GATEKEEPER RULES
1. `privacy_flag`:
   - Set to `"intimate"` if nudity, shirtless/intimate dating photo, or private bedroom content.
   - Set to `"identity_document"` if passport, driver's license, national ID, or credit card.
   - Set to `"financial_document"` if bank transfer, invoice, receipt, or tax slip.
   - Otherwise set to `"safe"`.
2. `domain`:
   - `"hair_solutions_co"`: Men's non-surgical hair replacement systems, hairpieces/toupees, lace/poly/mono base construction, hair color/curl/grey swatches, client or model hair replacement transformations (before bald/thinning, after hair system, side-by-side split, studio headshots showing hairline, salon install/cut-in).
   - `"knowledge_and_tools"`: Screenshots, slides, workflows, or diagrams of software tools, open-source GitHub repositories, CRM pipelines (HubSpot, Attio), AI agents/automations (n8n, Claude, Cursor, Gemini), UI/UX web design, or marketing swipe files.
   - `"personal"`: Personal life, group photos with friends/family, casual travel/vacations, pets, food, gym/sports, personal chats.
3. `subject_count`:
   - `"none"`: No human subjects (product macro, swatch, screenshot of software/code/UI, landscape).
   - `"single_person"`: Exactly one human subject is depicted (Note: a side-by-side before/after split of the SAME person counts as `"single_person"`!).
   - `"multiple_people"`: Two or more distinct people in the same scene (e.g., friends, group portrait, couple).
4. `model_shot_type` (STRICT MODEL QUALIFICATION RULE):
   - A photo ONLY qualifies for a model folder (`model_shot_type != "not_model"`) if `subject_count == "single_person"` AND the person is demonstrating men's hair replacement or scalp/hairline state:
     * `"before_bald_thinning"`: Solo shot showing male pattern baldness (Norwood 3-6), receding hairline, crown thinning, or bare scalp before system application.
     * `"before_after_split"`: Side-by-side diptych or composite showing the same man before (bald/thinning) and after (full hair system).
     * `"headshot_hairline"`: Close-up or studio portrait highlighting the hair system, front hairline graduation, temple blend, or hair density.
     * `"editorial_lifestyle"`: Solo commercial/editorial portrait of a model wearing a hair system in a styled studio or lifestyle setting.
     * `"install_cut_in"`: Salon chair application, scalp prep, bonding/taping, template measurement, or barber cut-in of a hair system.
     * `"not_model"`: Group photos (`multiple_people`), non-hair-system casual photos, pure product/swatch shots (`subject_count == "none"`), or screenshots.
5. `swatch_sub_type`, `hair_color_family`, `hair_color_code`:
   - When evaluating a hair swatch, color ring, or base spec chart:
     * `swatch_sub_type`:
       - `"circle-swatches"`: Circular/coiled hair color swatch discs or round color samples.
       - `"ring-swatches"`: Hair bundles attached to a swatch ring or stick.
       - `"color-charts"`: Multi-swatch comparison grid or full hair color chart.
       - `"grey-percentage"`: Swatches comparing synthetic/human grey blend percentages (e.g., 5%, 10%, 20%, 30%, 50% grey).
       - `"curl-pattern"`: Diagram or swatch demonstrating wave/curl diameter (32mm straight, 25mm slight wave, 20mm body wave, 15mm medium curl, 4mm-8mm afro curl).
       - `"base-material"`: Close-up of base cap construction (poly-skin, Swiss lace, French lace, monofilament mesh) without a human model.
       - `"none"`: Not a swatch or spec chart.
     * `hair_color_family`: `"black"`, `"dark_brown"`, `"medium_brown"`, `"light_brown"`, `"blonde"`, `"red_auburn"`, `"grey_silver"`, `"grey_blend"`, `"multiple_swatches"`, or `"not_applicable"`.
     * `hair_color_code`: Extract exact HSC/factory color code if visible or known (e.g. `"#1"`, `"#1B"`, `"#1B20"`, `"#2"`, `"#4"`, `"#22"`).
6. `knowledge_opportunity` (FOR SCREENSHOTS & TOOLS):
   - Always populate `knowledge_opportunity` when `capture_type == "screenshot"` or `domain == "knowledge_and_tools"`:
     * `is_actionable_repo_or_tool`: `true` if the screenshot shows an actionable open-source repo, CRM workflow/pipeline (HubSpot, Attio), AI agent/automation tool, or reusable e-commerce/engineering pattern.
     * `tool_or_repo_name`: Specific name (e.g. `"HubSpot Workflows"`, `"Attio CRM"`, `"n8n"`, `"Shopify Admin"`, etc.).
     * `github_or_url`: Visible URL or canonical domain/GitHub repo if known.
     * `license_type`: `"open_source_free"`, `"freemium"`, `"paid"`, or `"unknown"`.
     * `category_subfolder`: `"open-source-repos"`, `"crm-and-sales"`, `"ai-agents-and-workflows"`, `"ui-ux-and-web"`, `"marketing-and-copy"`, or `"general-reference"`.
     * `why_relevant_to_vincent`: 1 concise sentence explaining how Vincent can leverage this for Hair Solutions Co., Ascensio Digital, or his AI agent stack.
"""


def slugify(text: str) -> str:
    text = text.lower().strip()
    text = re.sub(r"[^\w\s-]", "", text)
    text = re.sub(r"[\s_]+", "-", text)
    return text[:64].strip("-")


def deterministic_uuid(val: str) -> str:
    return str(uuid.uuid5(uuid.NAMESPACE_DNS, val)).lower()


def compute_sha256(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        while chunk := f.read(1024 * 1024):
            h.update(chunk)
    return h.hexdigest().lower()


def load_image_jpeg_bytes(img_path: Path, max_dim: int = 1024) -> Optional[bytes]:
    """Load any supported image (JPEG, PNG, WEBP, HEIC) and encode as RGB JPEG bytes."""
    try:
        with Image.open(img_path) as img:
            try:
                img = ImageOps.exif_transpose(img)
            except Exception:
                pass
            img.thumbnail((max_dim, max_dim), Image.Resampling.LANCZOS)
            if img.mode != "RGB":
                img = img.convert("RGB")
            buf = io.BytesIO()
            img.save(buf, format="JPEG", quality=88)
            return buf.getvalue()
    except Exception:
        # Native macOS sips fallback for HEIC/RAW
        try:
            with tempfile.NamedTemporaryFile(suffix=".jpg", delete=False) as tmp:
                tmp_path = Path(tmp.name)
            subprocess.run(
                ["sips", "-Z", str(max_dim), str(img_path), "-s", "format", "jpeg", "--out", str(tmp_path)],
                capture_output=True,
                check=True,
            )
            data = tmp_path.read_bytes()
            tmp_path.unlink(missing_ok=True)
            return data
        except Exception as e:
            print(f"[WARN] Could not decode image {img_path}: {e}", file=sys.stderr)
            return None


class VertexVisionClassifier:
    """Strictly wraps Google Cloud Vertex AI (`ascensio-media-os`, `global`, `gemini-3.8-flash`)
    so 100% of calls are billed to GCP credits (zero fallback to GEMINI_API_KEY).
    """

    def __init__(self, project: str = PROJECT_ID, location: str = LOCATION, model: str = MODEL_NAME):
        self.project = project
        self.location = location
        self.model = model
        self.client = genai.Client(vertexai=True, project=self.project, location=self.location)

    def classify_image(self, img_path: Path, context_hint: str = "") -> Optional[PhotoClassification]:
        jpeg_bytes = load_image_jpeg_bytes(img_path)
        if not jpeg_bytes:
            return None

        user_prompt = f"{SYSTEM_PROMPT}{HAIR_CONCIERGE_GROUNDING}\n\nFilename hint (verify visually first!): `{img_path.name}`"
        if context_hint:
            user_prompt += f"\nContext: {context_hint}"

        for attempt in range(6):
            try:
                response = self.client.models.generate_content(
                    model=self.model,
                    contents=[
                        types.Part.from_bytes(data=jpeg_bytes, mime_type="image/jpeg"),
                        user_prompt,
                    ],
                    config=types.GenerateContentConfig(
                        response_mime_type="application/json",
                        response_schema=PhotoClassification,
                        temperature=0.0,
                    ),
                )
                if response.parsed and isinstance(response.parsed, PhotoClassification):
                    return response.parsed
                raw_text = response.text or "{}"
                if "```json" in raw_text:
                    raw_text = raw_text.split("```json")[1].split("```")[0].strip()
                data = json.loads(raw_text)
                return PhotoClassification(**data)
            except Exception as err:
                is_429 = "429" in str(err) or "RESOURCE_EXHAUSTED" in str(err)
                wait_s = (3.0 * (2 ** attempt)) if is_429 else (1.5 * (attempt + 1))
                print(
                    f"[WARN] Vertex AI ({self.project}/{self.location}/{self.model}) attempt {attempt + 1} failed on {img_path.name}: {err}. Retrying in {wait_s:.1f}s...",
                    file=sys.stderr,
                )
                time.sleep(wait_s)
        return None


class FramebaseCatalogRouter:
    """Manages folder creation, asset routing, tags, and visual assessments in a `.framebase` SQLite catalog."""

    def __init__(self, lib_path: Path):
        self.lib_path = lib_path
        self.db_path = lib_path / "Catalog" / "catalog.sqlite"

    def connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(str(self.db_path), timeout=60.0)
        conn.execute("PRAGMA journal_mode=WAL;")
        conn.execute("PRAGMA busy_timeout=60000;")
        return conn

    def get_folder_tree(self, conn: sqlite3.Connection) -> Dict[str, str]:
        """Return mapping of normalized `full/folder/path` -> `folder_id`."""
        c = conn.cursor()
        c.execute("SELECT id, name, parent_folder_id FROM folders")
        rows = c.fetchall()
        id_map = {r[0]: r for r in rows}
        tree: Dict[str, str] = {}
        for fid, name, pid in rows:
            parts = [name]
            curr = pid
            visited = {fid}
            while curr and curr in id_map and curr not in visited:
                visited.add(curr)
                parts.append(id_map[curr][1])
                curr = id_map[curr][2]
            parts.reverse()
            full_path = "/".join(parts).lower()
            tree[full_path] = fid
        return tree

    def ensure_folder_path(self, conn: sqlite3.Connection, folder_path: str) -> str:
        """Get or create a hierarchical folder path inside the Framebase catalog."""
        tree = self.get_folder_tree(conn)
        norm = folder_path.strip("/").lower()
        if norm in tree:
            return tree[norm]

        parts = [p.strip() for p in folder_path.strip("/").split("/") if p.strip()]
        curr_parent_id: Optional[str] = None
        cum_parts: List[str] = []
        now_ms = int(time.time() * 1000)
        c = conn.cursor()

        for idx, part in enumerate(parts):
            cum_parts.append(part.lower())
            sub_key = "/".join(cum_parts)
            if sub_key in tree:
                curr_parent_id = tree[sub_key]
                continue

            # Check case-insensitively under curr_parent_id
            if curr_parent_id is None:
                c.execute(
                    "SELECT id FROM folders WHERE parent_folder_id IS NULL AND LOWER(name) = LOWER(?)",
                    (part,),
                )
            else:
                c.execute(
                    "SELECT id FROM folders WHERE parent_folder_id = ? AND LOWER(name) = LOWER(?)",
                    (curr_parent_id, part),
                )
            existing = c.fetchone()
            if existing:
                curr_parent_id = existing[0]
                tree[sub_key] = curr_parent_id
                continue

            new_fid = str(uuid.uuid4()).lower()
            c.execute(
                """
                INSERT INTO folders (id, name, parent_folder_id, created_at_ms, updated_at_ms, sort_order, system_kind)
                VALUES (?, ?, ?, ?, ?, ?, NULL)
                """,
                (new_fid, part, curr_parent_id, now_ms, now_ms, 10 + idx),
            )
            curr_parent_id = new_fid
            tree[sub_key] = new_fid

        conn.commit()
        return curr_parent_id  # type: ignore[return-value]

    def attach_tags_and_assessment(
        self,
        conn: sqlite3.Connection,
        asset_id: str,
        classification: PhotoClassification,
        extra_tags: List[str],
    ) -> None:
        now_ms = int(time.time() * 1000)
        c = conn.cursor()
        all_tags = set(classification.tags or []) | set(extra_tags)

        if classification.hair_color_code:
            code_clean = classification.hair_color_code.lstrip("#").lower()
            all_tags.add(f"color:{code_clean}")
        if classification.hair_color_family != "not_applicable":
            all_tags.add(f"color-family:{slugify(classification.hair_color_family)}")
        if classification.swatch_sub_type != "none":
            all_tags.add(f"swatch:{classification.swatch_sub_type}")
        if classification.model_shot_type != "not_model":
            all_tags.add(f"shot:{slugify(classification.model_shot_type)}")

        for raw_tag in all_tags:
            tag_str = raw_tag.strip().lower()
            if not tag_str:
                continue
            if ":" not in tag_str:
                ns, val = "tag", slugify(tag_str)
            else:
                p1, p2 = tag_str.split(":", 1)
                ns, val = slugify(p1) or "tag", slugify(p2) or "general"
            full_name = f"{ns}:{val}"
            c.execute("SELECT id FROM tags WHERE LOWER(name) = LOWER(?)", (full_name,))
            row = c.fetchone()
            if row:
                tag_id = row[0]
            else:
                tag_id = deterministic_uuid(f"framebase-tag:{full_name}")
                c.execute(
                    """
                    INSERT OR IGNORE INTO tags (id, namespace, value, name, created_at_ms, updated_at_ms)
                    VALUES (?, ?, ?, ?, ?, ?)
                    """,
                    (tag_id, ns, val, full_name, now_ms, now_ms),
                )
            c.execute(
                "INSERT OR IGNORE INTO asset_tags (asset_id, tag_id, added_at_ms) VALUES (?, ?, ?)",
                (asset_id, tag_id, now_ms),
            )

        conn.commit()


def resolve_catalog_asset_image(
    lib_path: Path,
    asset_id: str,
    filename: str,
    storage_key: Optional[str],
    file_size: Optional[int] = None,
    modified_at_ms: Optional[int] = None,
) -> Optional[Path]:
    """Resolve an image path for an asset in a Framebase library without relying on filename heuristics."""
    # 1. Library Originals
    if storage_key:
        orig_path = lib_path / "Originals" / storage_key
        if orig_path.exists():
            return orig_path

    # 2. Framebase Local Thumbnail/Preview Cache (720x720 high-res preview first, then 352x352 retina thumb)
    shard_dir = THUMB_CACHE_DIR / asset_id[:2]
    if shard_dir.exists():
        if file_size is not None and modified_at_ms is not None:
            exact_prev = shard_dir / f"v1-preview-{asset_id}-{file_size}-{modified_at_ms}-720x720-3ff0000000000000.png"
            if exact_prev.exists():
                return exact_prev
        previews = sorted(shard_dir.glob(f"v1-preview-{asset_id}-*.png"))
        if previews:
            return previews[0]
        thumbs = sorted(shard_dir.glob(f"v1-thumbnail-{asset_id}-*.png"))
        if thumbs:
            return thumbs[0]

    # 3. Canonical Reference Vault & Local Exports
    candidate_dirs = [
        VINCENT_REF_DIR,
        Path("/Users/vincent/Downloads/Google Drive Images Export"),
        Path("/Users/vincent/Downloads/Google Drive Images Export/already_in_catalog"),
        Path("/Users/vincent/Downloads/Google Drive Images Export/isolated_reference_screenshots"),
    ]
    for d in candidate_dirs:
        cand = d / filename
        if cand.exists():
            return cand

    return None


def determine_pass1_route(cls: PhotoClassification, model_name: Optional[str] = None) -> Tuple[str, str, str]:
    """
    Pass 1 (3-Pillar Gatekeeper) + Pass 2A/2B routing decision.
    Returns (target_library_name, target_folder_path, routing_reason).
    """
    # Hard Rule 1: Privacy Gatekeeper -> Quarantine
    if cls.privacy_flag in ("intimate", "identity_document") or cls.sensitivity in (
        Sensitivity.intimate,
        Sensitivity.identity_document,
    ):
        sub = "intimate" if cls.privacy_flag == "intimate" or cls.sensitivity == Sensitivity.intimate else "identity_documents"
        return (
            PERSONAL_LIB.name,
            f"06_private_quarantine/{sub}",
            f"Hard Rule: privacy_flag={cls.privacy_flag} -> Quarantine",
        )

    # Hard Rule 2: Multi-person or Personal -> Personal Library (NEVER into 03_people/models/<name>!)
    if cls.subject_count == "multiple_people" or cls.domain == Domain.personal:
        if cls.subject_count == "multiple_people":
            return (
                PERSONAL_LIB.name,
                "01_people_and_family/friends",
                "Hard Rule: subject_count == 'multiple_people' -> Personal Library (friends), forbidden in solo model folder",
            )
        cat_val = cls.category.value if cls.category else ""
        if "travel" in cat_val or "nature" in cat_val:
            return (PERSONAL_LIB.name, "03_travel_and_places", "Hard Rule: domain == 'personal' (travel)")
        if "family" in cat_val:
            return (PERSONAL_LIB.name, "01_people_and_family/family", "Hard Rule: domain == 'personal' (family)")
        if "people" in cat_val:
            return (PERSONAL_LIB.name, "01_people_and_family/friends", "Hard Rule: domain == 'personal' (people)")
        return (PERSONAL_LIB.name, "04_home_and_lifestyle/interiors", "Hard Rule: domain == 'personal'")

    # Hard Rule 3: Knowledge & Tools -> Pass 2A (Knowledge Library)
    if cls.domain in (Domain.knowledge_and_tools, Domain.knowledge):
        sub = "general-reference"
        if cls.knowledge_opportunity and cls.knowledge_opportunity.category_subfolder:
            sub = cls.knowledge_opportunity.category_subfolder
        return (
            KNOWLEDGE_LIB.name,
            f"ai_and_automation/{sub}",
            f"Pass 2A (Screenshot & Repo Scout): domain={cls.domain.value} -> ai_and_automation/{sub}",
        )

    # Hard Rule 4: Hair Solutions Co. & safe -> Pass 2B (HSC Library)
    if cls.swatch_sub_type != "none":
        target_folder = SWATCH_SUBTYPE_TO_FOLDER.get(cls.swatch_sub_type, "02_specs/swatches")
        return (
            HSC_LIB.name,
            target_folder,
            f"Pass 2B (Swatch Sorter): swatch_sub_type={cls.swatch_sub_type} -> {target_folder}",
        )

    if cls.subject_count == "single_person" and cls.model_shot_type != "not_model":
        person_slug = slugify(model_name or ("vincent" if cls.has_vincent else "models"))
        sub_folder = MODEL_SHOT_TO_SUBFOLDER.get(cls.model_shot_type, "headshots")
        if person_slug and person_slug != "models":
            target_folder = f"03_people/models/{person_slug}/{sub_folder}"
        else:
            target_folder = f"03_people/models/{sub_folder}"
        return (
            HSC_LIB.name,
            target_folder,
            f"Pass 2B (Model Qualification Passed): single_person + {cls.model_shot_type} -> {target_folder}",
        )

    # Non-model HSC business photo (e.g. standalone hairpiece product, maintenance bottle, ops)
    if cls.subject_count == "single_person" and cls.model_shot_type == "not_model":
        return (
            PERSONAL_LIB.name,
            "01_people_and_family/portraits",
            "Model Qualification Rejected: single_person but model_shot_type == 'not_model' (no hair replacement demonstrated)",
        )

    return (
        HSC_LIB.name,
        "01_products/hair-systems",
        "Pass 2B (HSC Product/Spec): domain=hair_solutions_co, subject_count=none",
    )


def run_repo_scout(
    classifier: VertexVisionClassifier,
    source_dir: Optional[Path],
    limit: int,
    apply_changes: bool,
) -> List[Dict[str, Any]]:
    """
    Pass 2A: Screenshot & Repo Scout.
    Evaluates screenshots, extracts `knowledge_opportunity`, routes into `Knowledge Library.framebase`,
    and writes `/Users/vincent/06_code/framebase/MediaWorkshop/reports/knowledge_repo_scout_digest.json` + `.md`.
    """
    target_dir = source_dir or DEFAULT_SCREENSHOTS_DIR
    if not target_dir.exists() and FALLBACK_SCREENSHOTS_DIR.exists():
        print(
            f"[INFO] `{target_dir}` resolved to canonical export directory `{FALLBACK_SCREENSHOTS_DIR}`."
        )
        target_dir = FALLBACK_SCREENSHOTS_DIR

    if not target_dir.exists():
        raise FileNotFoundError(f"Screenshot source directory not found: {target_dir}")

    valid_exts = {".png", ".jpg", ".jpeg", ".webp", ".heic"}
    all_files = sorted(
        [p for p in target_dir.iterdir() if p.is_file() and p.suffix.lower() in valid_exts]
    )

    # Prioritize diverse screenshots (CRM pipelines, HubSpot, CleanShot tool captures, etc.)
    selected_files = all_files[:limit]
    print(f"\n{'=' * 88}")
    print(f"PASS 2A: SCREENSHOT & REPO SCOUT (Vertex AI {MODEL_NAME} @ {PROJECT_ID})")
    print(f"Source Directory: {target_dir} | Evaluating: {len(selected_files)} screenshots | Mode: {'APPLY' if apply_changes else 'DRY-RUN'}")
    print(f"{'=' * 88}\n")

    router = FramebaseCatalogRouter(KNOWLEDGE_LIB) if (apply_changes and KNOWLEDGE_LIB.exists()) else None
    conn = router.connect() if router else None

    results: List[Dict[str, Any]] = []
    for idx, img_path in enumerate(selected_files, 1):
        t0 = time.time()
        cls = classifier.classify_image(
            img_path,
            context_hint="Pass 2A Screenshot & Repo Scout: Identify any software tool, CRM workflow, open-source GitHub repo, AI agent workflow, or UI pattern and populate `knowledge_opportunity`.",
        )
        elapsed = time.time() - t0
        if not cls:
            print(f"[{idx}/{len(selected_files)}] FAILED to classify {img_path.name}")
            continue

        # Ensure knowledge_opportunity is populated for digest clarity
        ko = cls.knowledge_opportunity or KnowledgeOpportunity(
            is_actionable_repo_or_tool=bool(cls.subject_or_tool_discussed or cls.app_name),
            tool_or_repo_name=cls.subject_or_tool_discussed or cls.app_name or "Unknown Tool",
            github_or_url=None,
            license_type="unknown",
            category_subfolder="general-reference",
            why_relevant_to_vincent=cls.rationale,
        )
        cls.knowledge_opportunity = ko

        dest_folder = f"ai_and_automation/{ko.category_subfolder}"
        if apply_changes and router and conn:
            router.ensure_folder_path(conn, dest_folder)

        record = {
            "index": idx,
            "filename": img_path.name,
            "source_path": str(img_path),
            "target_library": KNOWLEDGE_LIB.name,
            "target_folder": dest_folder,
            "latency_sec": round(elapsed, 2),
            "classification": cls.model_dump(mode="json"),
        }
        results.append(record)

        print(
            f"[{idx}/{len(selected_files)}] {img_path.name}\n"
            f"  -> Route: {KNOWLEDGE_LIB.name} :: `{dest_folder}` ({elapsed:.2f}s)\n"
            f"  -> Actionable Tool/Repo: {ko.is_actionable_repo_or_tool} | Name: {ko.tool_or_repo_name} | License: {ko.license_type}\n"
            f"  -> Why Relevant: {ko.why_relevant_to_vincent}\n"
        )

    if conn:
        conn.close()

    if not results:
        print("[WARN] No screenshots classified; skipping digest file overwrite.", file=sys.stderr)
        return results

    # Write JSON, JSONL, and Markdown digests
    REPORTS_DIR.mkdir(parents=True, exist_ok=True)
    json_path = REPORTS_DIR / "knowledge_repo_scout_digest.json"
    jsonl_path = REPORTS_DIR / "knowledge_repo_scout_digest.jsonl"
    md_path = REPORTS_DIR / "knowledge_repo_scout_digest.md"

    digest_payload = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "project": PROJECT_ID,
        "location": LOCATION,
        "model": MODEL_NAME,
        "source_directory": str(target_dir),
        "total_evaluated": len(results),
        "actionable_count": sum(
            1 for r in results if r["classification"].get("knowledge_opportunity", {}).get("is_actionable_repo_or_tool")
        ),
        "items": results,
    }
    json_path.write_text(json.dumps(digest_payload, indent=2, ensure_ascii=False), encoding="utf-8")

    with open(jsonl_path, "w", encoding="utf-8") as jf:
        for r in results:
            jf.write(json.dumps(r, ensure_ascii=False) + "\n")

    md_lines = [
        "# Framebase 2.0 — Knowledge & Repo Scout Digest (Pass 2A)",
        "",
        f"- **Generated At**: `{digest_payload['generated_at']}`",
        f"- **Vertex AI Project**: `{PROJECT_ID}` (`{LOCATION}`, `{MODEL_NAME}`)",
        f"- **Source Folder**: `{target_dir}`",
        f"- **Total Evaluated**: `{digest_payload['total_evaluated']}` (`{digest_payload['actionable_count']}` actionable tools/workflows)",
        "",
        "## Discovered Tools, Workflows & Repositories",
        "",
        "| # | Screenshot | Tool / Repo | Category Subfolder | License | Actionable | Why Relevant to Vincent |",
        "|---|------------|-------------|--------------------|---------|------------|-------------------------|",
    ]
    for r in results:
        c_data = r["classification"]
        ko_data = c_data.get("knowledge_opportunity") or {}
        md_lines.append(
            f"| {r['index']} | `{r['filename']}` | **{ko_data.get('tool_or_repo_name') or 'N/A'}** "
            f"| `ai_and_automation/{ko_data.get('category_subfolder', 'general-reference')}` "
            f"| `{ko_data.get('license_type', 'unknown')}` "
            f"| `{'Yes' if ko_data.get('is_actionable_repo_or_tool') else 'No'}` "
            f"| {ko_data.get('why_relevant_to_vincent') or c_data.get('rationale', '')} |"
        )

    md_lines.append("\n## Full Structured Classifications (JSON)\n")
    for r in results:
        md_lines.append(f"### {r['index']}. `{r['filename']}`")
        md_lines.append("```json")
        md_lines.append(json.dumps(r["classification"], indent=2, ensure_ascii=False))
        md_lines.append("```\n")

    md_path.write_text("\n".join(md_lines), encoding="utf-8")
    print(f"[DIGEST SAVED] JSON:  {json_path}")
    print(f"[DIGEST SAVED] JSONL: {jsonl_path}")
    print(f"[DIGEST SAVED] MD:    {md_path}\n")
    return results


def run_refine_models(
    classifier: VertexVisionClassifier,
    model_name: str,
    source_dir: Optional[Path],
    limit: int,
    apply_changes: bool,
) -> List[Dict[str, Any]]:
    """
    Pass 2B (Model Sub-Folder Sorter):
    Enforces the strict Model Qualification Rule (`subject_count == "single_person"` AND `model_shot_type != "not_model"`)
    and routes into `03_people/models/<name>/{before-after,headshots,editorial,install-cut}`.
    """
    candidates: List[Tuple[Optional[str], str, Path, str]] = []

    if source_dir and source_dir.exists():
        valid_exts = {".png", ".jpg", ".jpeg", ".webp", ".heic"}
        for p in sorted(source_dir.iterdir()):
            if p.is_file() and p.suffix.lower() in valid_exts:
                candidates.append((None, p.name, p, str(source_dir)))
    else:
        # Query HSC Library.framebase `03_people/models/<model_name>` first
        if HSC_LIB.exists():
            router = FramebaseCatalogRouter(HSC_LIB)
            conn = router.connect()
            c = conn.cursor()
            c.execute(
                """
                SELECT a.id, a.filename, a.storage_key, a.file_size, a.modified_at_ms, f.name
                FROM assets a
                JOIN folders f ON a.parent_folder_id = f.id
                WHERE LOWER(f.name) = LOWER(?)
                ORDER BY a.filename ASC
                """,
                (model_name,),
            )
            rows = c.fetchall()
            conn.close()
            for aid, fn, sk, sz, mod_ms, fname in rows:
                resolved = resolve_catalog_asset_image(HSC_LIB, aid, fn, sk, sz, mod_ms)
                if resolved and resolved.exists():
                    candidates.append((aid, fn, resolved, f"03_people/models/{fname}"))

        # Supplement or fallback to canonical character reference folder if needed
        if len(candidates) < limit and model_name.lower() == "vincent" and VINCENT_REF_DIR.exists():
            existing_names = {c[1] for c in candidates}
            for p in sorted(VINCENT_REF_DIR.iterdir()):
                if p.is_file() and p.suffix.lower() in {".png", ".jpg", ".jpeg", ".webp"} and p.name not in existing_names:
                    candidates.append((None, p.name, p, "MediaWorkshop/references/characters/vincent"))

    selected = candidates[:limit]
    print(f"\n{'=' * 88}")
    print(f"PASS 2B: HSC MODEL SUB-FOLDER SORTER (Vertex AI {MODEL_NAME} @ {PROJECT_ID})")
    print(
        f"Target Model: `{model_name}` | Evaluating: {len(selected)} photos | Mode: {'APPLY' if apply_changes else 'DRY-RUN'}"
    )
    print(f"{'=' * 88}\n")

    hsc_router = FramebaseCatalogRouter(HSC_LIB) if (apply_changes and HSC_LIB.exists()) else None
    hsc_conn = hsc_router.connect() if hsc_router else None

    results: List[Dict[str, Any]] = []
    for idx, (asset_id, filename, img_path, current_folder) in enumerate(selected, 1):
        t0 = time.time()
        cls = classifier.classify_image(
            img_path,
            context_hint=(
                f"Pass 2B HSC Model Verification for model `{model_name}` (currently in `{current_folder}`). "
                "Verify `subject_count` ('single_person' vs 'multiple_people'), `has_vincent`, `model_shot_type` "
                "('before_bald_thinning', 'before_after_split', 'headshot_hairline', 'editorial_lifestyle', 'install_cut_in', or 'not_model'), "
                "`hairline_presentation`, `hair_color_family`, and `hair_color_code`."
            ),
        )
        elapsed = time.time() - t0
        if not cls:
            print(f"[{idx}/{len(selected)}] FAILED to classify {filename}")
            continue

        target_lib, target_folder, reason = determine_pass1_route(cls, model_name=model_name)
        qualified = cls.subject_count == "single_person" and cls.model_shot_type != "not_model" and cls.privacy_flag == "safe"

        if apply_changes and hsc_router and hsc_conn and asset_id:
            if target_lib == HSC_LIB.name:
                dest_fid = hsc_router.ensure_folder_path(hsc_conn, target_folder)
                hsc_conn.execute(
                    "UPDATE assets SET parent_folder_id = ?, updated_at_ms = ? WHERE id = ?",
                    (dest_fid, int(time.time() * 1000), asset_id),
                )
                hsc_router.attach_tags_and_assessment(
                    hsc_conn,
                    asset_id,
                    cls,
                    extra_tags=[f"model:{slugify(model_name)}", f"shot:{slugify(cls.model_shot_type)}"],
                )
                hsc_conn.commit()

        record = {
            "index": idx,
            "asset_id": asset_id,
            "filename": filename,
            "resolved_image_path": str(img_path),
            "current_folder": current_folder,
            "qualified_as_solo_model": qualified,
            "target_library": target_lib,
            "target_folder": target_folder,
            "routing_reason": reason,
            "latency_sec": round(elapsed, 2),
            "classification": cls.model_dump(mode="json"),
        }
        results.append(record)

        print(
            f"[{idx}/{len(selected)}] {filename} (from `{current_folder}`)\n"
            f"  -> Qualified Solo Model: {qualified} | subject_count={cls.subject_count} | model_shot_type={cls.model_shot_type}\n"
            f"  -> Hairline: {cls.hairline_presentation} | Color: {cls.hair_color_family} ({cls.hair_color_code or 'N/A'})\n"
            f"  -> Target Route: {target_lib} :: `{target_folder}` ({elapsed:.2f}s)\n"
            f"  -> Reason: {reason}\n"
        )

    if hsc_conn:
        hsc_conn.close()

    return results


def run_refine_swatches(
    classifier: VertexVisionClassifier,
    source_dir: Optional[Path],
    limit: int,
    apply_changes: bool,
) -> List[Dict[str, Any]]:
    """
    Pass 2B (Swatch Sub-Folder Sorter):
    Sub-divides `02_specs/swatches` into:
      - `02_specs/swatches/hair-color/circle-swatches`
      - `02_specs/swatches/hair-color/ring-swatches`
      - `02_specs/swatches/hair-color/color-charts`
      - `02_specs/swatches/grey-percentage`
      - `02_specs/swatches/curl-pattern`
      - `02_specs/swatches/base-material`
    """
    candidates: List[Tuple[Optional[str], str, Path, str]] = []
    if source_dir and source_dir.exists():
        valid_exts = {".png", ".jpg", ".jpeg", ".webp", ".heic"}
        for p in sorted(source_dir.iterdir()):
            if p.is_file() and p.suffix.lower() in valid_exts:
                candidates.append((None, p.name, p, str(source_dir)))
    elif HSC_LIB.exists():
        router = FramebaseCatalogRouter(HSC_LIB)
        conn = router.connect()
        c = conn.cursor()
        c.execute(
            """
            SELECT a.id, a.filename, a.storage_key, a.file_size, a.modified_at_ms, f.name
            FROM assets a
            JOIN folders f ON a.parent_folder_id = f.id
            WHERE f.name IN ('swatches', 'hair-color', 'grey-percentage', 'curl-pattern', 'base-material', 'hair-color-swatches', 'hair-swatches')
            ORDER BY a.filename ASC
            """
        )
        rows = c.fetchall()
        conn.close()
        for aid, fn, sk, sz, mod_ms, fname in rows:
            resolved = resolve_catalog_asset_image(HSC_LIB, aid, fn, sk, sz, mod_ms)
            if resolved and resolved.exists():
                candidates.append((aid, fn, resolved, f"02_specs/swatches/{fname}"))

    selected = candidates[:limit]
    print(f"\n{'=' * 88}")
    print(f"PASS 2B: HSC SWATCH SUB-FOLDER SORTER (Vertex AI {MODEL_NAME} @ {PROJECT_ID})")
    print(f"Evaluating: {len(selected)} swatches | Mode: {'APPLY' if apply_changes else 'DRY-RUN'}")
    print(f"{'=' * 88}\n")

    hsc_router = FramebaseCatalogRouter(HSC_LIB) if (apply_changes and HSC_LIB.exists()) else None
    hsc_conn = hsc_router.connect() if hsc_router else None

    results: List[Dict[str, Any]] = []
    for idx, (asset_id, filename, img_path, current_folder) in enumerate(selected, 1):
        t0 = time.time()
        cls = classifier.classify_image(
            img_path,
            context_hint=(
                "Pass 2B HSC Swatch Classification: Determine `swatch_sub_type` "
                "('circle-swatches', 'ring-swatches', 'color-charts', 'grey-percentage', 'curl-pattern', 'base-material'), "
                "`hair_color_family`, and `hair_color_code` (e.g. '#1B', '#22', '#1B20')."
            ),
        )
        elapsed = time.time() - t0
        if not cls:
            continue

        target_folder = SWATCH_SUBTYPE_TO_FOLDER.get(cls.swatch_sub_type, "02_specs/swatches/hair-color/circle-swatches")
        if apply_changes and hsc_router and hsc_conn and asset_id:
            dest_fid = hsc_router.ensure_folder_path(hsc_conn, target_folder)
            hsc_conn.execute(
                "UPDATE assets SET parent_folder_id = ?, updated_at_ms = ? WHERE id = ?",
                (dest_fid, int(time.time() * 1000), asset_id),
            )
            hsc_router.attach_tags_and_assessment(hsc_conn, asset_id, cls, extra_tags=["product:swatch"])
            hsc_conn.commit()

        record = {
            "index": idx,
            "asset_id": asset_id,
            "filename": filename,
            "current_folder": current_folder,
            "target_library": HSC_LIB.name,
            "target_folder": target_folder,
            "swatch_sub_type": cls.swatch_sub_type,
            "hair_color_family": cls.hair_color_family,
            "hair_color_code": cls.hair_color_code,
            "latency_sec": round(elapsed, 2),
            "classification": cls.model_dump(mode="json"),
        }
        results.append(record)
        print(
            f"[{idx}/{len(selected)}] {filename} -> `{target_folder}` "
            f"(sub_type={cls.swatch_sub_type}, color={cls.hair_color_family} / {cls.hair_color_code}) [{elapsed:.2f}s]"
        )

    if hsc_conn:
        hsc_conn.close()
    return results


def run_gatekeeper(
    classifier: VertexVisionClassifier,
    source_dir: Optional[Path],
    limit: int,
    apply_changes: bool,
) -> List[Dict[str, Any]]:
    """
    Pass 1 (3-Pillar Gatekeeper):
    Evaluates images from a local folder or Framebase `00_inbox` and routes them across
    Quarantine, Personal Library, Knowledge Library (Pass 2A), or HSC Library (Pass 2B).
    """
    candidates: List[Tuple[Optional[str], str, Path]] = []
    if source_dir and source_dir.exists():
        valid_exts = {".png", ".jpg", ".jpeg", ".webp", ".heic"}
        for p in sorted(source_dir.iterdir()):
            if p.is_file() and p.suffix.lower() in valid_exts:
                candidates.append((None, p.name, p))
    elif HSC_LIB.exists():
        router = FramebaseCatalogRouter(HSC_LIB)
        conn = router.connect()
        c = conn.cursor()
        c.execute(
            """
            SELECT a.id, a.filename, a.storage_key, a.file_size, a.modified_at_ms
            FROM assets a
            JOIN folders f ON a.parent_folder_id = f.id
            WHERE LOWER(f.name) IN ('00_inbox', 'inbox')
              AND a.id NOT IN (
                  SELECT at.asset_id FROM asset_tags at
                  JOIN tags t ON at.tag_id = t.id
                  WHERE t.name = 'verified:gemini-3.8-flash'
              )
            ORDER BY a.imported_at_ms DESC
            """
        )
        for aid, fn, sk, sz, mod_ms in c.fetchall():
            resolved = resolve_catalog_asset_image(HSC_LIB, aid, fn, sk, sz, mod_ms)
            if resolved and resolved.exists():
                candidates.append((aid, fn, resolved))
        conn.close()

    selected = candidates[:limit]
    print(f"\n{'=' * 88}")
    print(f"PASS 1: 3-PILLAR GATEKEEPER (Vertex AI {MODEL_NAME} @ {PROJECT_ID})")
    print(f"Evaluating: {len(selected)} assets | Mode: {'APPLY' if apply_changes else 'DRY-RUN'}")
    print(f"{'=' * 88}\n")

    hsc_router = FramebaseCatalogRouter(HSC_LIB) if (apply_changes and HSC_LIB.exists()) else None
    hsc_conn = hsc_router.connect() if hsc_router else None

    results: List[Dict[str, Any]] = []
    for idx, (asset_id, filename, img_path) in enumerate(selected, 1):
        t0 = time.time()
        cls = classifier.classify_image(img_path, context_hint="Pass 1 3-Pillar Gatekeeper evaluation.")
        elapsed = time.time() - t0
        if not cls:
            continue

        target_lib, target_folder, reason = determine_pass1_route(cls)
        if apply_changes and hsc_router and hsc_conn and asset_id:
            if target_lib == HSC_LIB.name:
                dest_fid = hsc_router.ensure_folder_path(hsc_conn, target_folder)
                hsc_conn.execute(
                    "UPDATE assets SET parent_folder_id = ?, updated_at_ms = ? WHERE id = ?",
                    (dest_fid, int(time.time() * 1000), asset_id),
                )
                hsc_router.attach_tags_and_assessment(
                    hsc_conn,
                    asset_id,
                    cls,
                    extra_tags=["verified:gemini-3.8-flash", "brain:the-hair-concierge-2026"],
                )
                hsc_conn.commit()
            else:
                archive_sub = (
                    "09_archive/quarantine"
                    if "quarantine" in target_folder
                    else (
                        "09_archive/routed-knowledge"
                        if target_lib == KNOWLEDGE_LIB.name
                        else "09_archive/routed-personal"
                    )
                )
                dest_fid = hsc_router.ensure_folder_path(hsc_conn, archive_sub)
                hsc_conn.execute(
                    "UPDATE assets SET parent_folder_id = ?, updated_at_ms = ? WHERE id = ?",
                    (dest_fid, int(time.time() * 1000), asset_id),
                )
                hsc_router.attach_tags_and_assessment(
                    hsc_conn,
                    asset_id,
                    cls,
                    extra_tags=[
                        "verified:gemini-3.8-flash",
                        "brain:the-hair-concierge-2026",
                        f"route-library:{slugify(target_lib)}",
                        f"route-folder:{slugify(target_folder)}",
                    ],
                )
                hsc_conn.commit()

        record = {
            "index": idx,
            "asset_id": asset_id,
            "filename": filename,
            "target_library": target_lib,
            "target_folder": target_folder,
            "routing_reason": reason,
            "latency_sec": round(elapsed, 2),
            "classification": cls.model_dump(mode="json"),
        }
        results.append(record)
        print(
            f"[{idx}/{len(selected)}] {filename} -> {target_lib} :: `{target_folder}` ({elapsed:.2f}s)\n"
            f"  -> {reason}"
        )

    if hsc_conn:
        hsc_conn.close()
    return results


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Framebase 2.0 Multi-Pass Media Sorter & Screenshot Repo Scout (Vertex AI Gemini 3.8 Flash)"
    )
    parser.add_argument(
        "--mode",
        choices=["gatekeeper", "repo-scout", "refine-models", "refine-swatches"],
        required=True,
        help="Execution pass: gatekeeper (Pass 1), repo-scout (Pass 2A), refine-models (Pass 2B), or refine-swatches (Pass 2B)",
    )
    parser.add_argument(
        "--source-dir",
        type=Path,
        default=None,
        help="Optional local folder of images to evaluate",
    )
    parser.add_argument(
        "--model-name",
        type=str,
        default="vincent",
        help="Target model name for --mode refine-models (default: vincent)",
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=10,
        help="Maximum number of images to process (default: 10)",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Run classification and routing simulation without modifying Framebase SQLite catalogs",
    )
    parser.add_argument(
        "--apply",
        action="store_true",
        help="Apply folder creations, asset moves, and tag attachments to Framebase SQLite catalogs",
    )
    parser.add_argument(
        "--json-out",
        type=Path,
        default=None,
        help="Optional path to write full JSON output of the run",
    )
    args = parser.parse_args()

    apply_changes = bool(args.apply and not args.dry_run)
    classifier = VertexVisionClassifier(project=PROJECT_ID, location=LOCATION, model=MODEL_NAME)

    if args.mode == "repo-scout":
        results = run_repo_scout(
            classifier=classifier,
            source_dir=args.source_dir,
            limit=args.limit,
            apply_changes=apply_changes,
        )
    elif args.mode == "refine-models":
        results = run_refine_models(
            classifier=classifier,
            model_name=args.model_name,
            source_dir=args.source_dir,
            limit=args.limit,
            apply_changes=apply_changes,
        )
    elif args.mode == "refine-swatches":
        results = run_refine_swatches(
            classifier=classifier,
            source_dir=args.source_dir,
            limit=args.limit,
            apply_changes=apply_changes,
        )
    else:
        results = run_gatekeeper(
            classifier=classifier,
            source_dir=args.source_dir,
            limit=args.limit,
            apply_changes=apply_changes,
        )

    if args.json_out:
        args.json_out.parent.mkdir(parents=True, exist_ok=True)
        args.json_out.write_text(json.dumps(results, indent=2, ensure_ascii=False), encoding="utf-8")
        print(f"[JSON OUTPUT] Saved to {args.json_out}")

    print("=== SUMMARY JSON ===")
    print(json.dumps(results, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()

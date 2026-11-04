# Framebase 2.0 Monorepo — Unified Semantic Engine, Architecture & Agent Rules
## macOS App (`App/UI/Packages`) × Cloudflare Edge (`Cloud`) × Agents Studio (`AgentsStudio`) × Media Workshop (`MediaWorkshop`)

This document is the persistent **Visual Preference Memory, Semantic Taxonomy, and Unified Operating Ruleset** for the consolidated Framebase 2.0 monorepo at `/Users/vincent/06_code/framebase` (`ascensio-digital-solutions/framebase`).

---

## 1. Unified Monorepo Architecture & Cloud Credentials (November 2026)

```
┌──────────────────────────────────────────────────────────────────────────────────┐
│                     FRAMEBASE 2.0 MONOREPO (/Users/vincent/06_code/framebase)    │
├──────────────────┬──────────────────┬─────────────────────┬──────────────────────┤
│  App / UI /      │  Cloud/          │  AgentsStudio/      │  MediaWorkshop/      │
│  Packages/       │  (Cloudflare     │  (Domain Agents,    │  (Vision Sorter,     │
│  (Native macOS   │   Workers, D1,   │   RAG, SFT/DPO      │   Screenshot Scout,  │
│   SwiftUI +      │   R2, Vectorize, │   Datasets &        │   Nano Banana 2.1    │
│   AI Chat Panel) │   AI Gateway)    │   Eval Harnesses)   │   & Reference Vault) │
└──────────────────┴──────────────────┴─────────────────────┴──────────────────────┘
```

- **Canonical Local Repository**: `/Users/vincent/06_code/framebase` (with backward-compatible symlinks from `/Users/vincent/04_systems/media_workshop` and `/Users/vincent/06_code/agents-studio`)
- **Canonical GitHub Repository**: `ascensio-digital-solutions/framebase`
- **Google Cloud Project & Credentials**:
  - **Primary Media OS Project**: `ascensio-media-os` (`Framebase Media OS`, project number `109902003319`, region `us-central1` / `global` for Vertex AI)
  - **Service Account (Active Default ADC via Impersonation)**: `framebase-agent-sa@ascensio-media-os.iam.gserviceaccount.com` (linked to `vincent@ascensiodigital.co`, stored at `~/.config/gcloud/application_default_credentials.json`)
  - **Cross-Project RAG Access**: `framebase-agent-sa@ascensio-media-os.iam.gserviceaccount.com` is also authorized on `the-hair-concierge-2026` (`HAIR_SYSTEM_RAG_CORPUS` and `MARKETING_BRAND_RAG_CORPUS`)
- **Cloudflare Infrastructure ($10K Startups Grant)**:
  - Account ID: `938d6ab84fe239647496cc1540ffa21f`
  - AI Gateway: `framebase-vision-dev`
  - Vectorize Index: `fb-assets` (1024-dim multimodal embeddings)
  - D1 Databases: `framebase-catalog-prod`, `framebase-catalog-personal-prod`, `framebase-catalog-dev`
  - R2 Buckets: `framebase-blobs-prod`, `framebase-blobs-personal-prod`
- **Python Environment**: `/Users/vincent/06_code/framebase/.venv/bin/python`
- **Generative Models (Synthesis)**:
  - `gemini-nano-banana-2.1` (Nano Banana 2.1 — primary, up to 14 reference images, 1K/2K/4K output, multi-turn conversational edits)
  - `gemini-3-pro-image` (Nano Banana Pro — high-fidelity typography, complex layouts, maximum photorealism)
  - `gemini-3.1-flash-lite-image` (Nano Banana 2 Lite — rapid draft sketching)
- **Analysis Model (Deconstruction & Evaluation)**:
  - `gemini-3.8-flash` via Google Cloud Vertex AI (`ascensio-media-os`, location `global`)
- **Library & Storage Targets**:
  - `~/Pictures/HSC Library.framebase` (Hair Solutions Co. products, models, specs, ops)
  - `~/Pictures/Personal Library.framebase` (Personal memories, travel, family, fitness)
  - `~/Pictures/Knowledge Library.framebase` (AI tools, open-source repos, CRM screenshots, web design, swipe files)

---

## 2. Active Aesthetic Profile & Semantic Taxonomy

<!-- PREFERENCES_START -->
### Core Aesthetic Direction (Governs Both Generation & Quality Scoring)
- **Overall Look**: Editorial realism, tactile textures, natural skin pores and material rendering, grounded physical lighting rather than synthetic "AI gloss."
- **Lighting & Atmosphere**: Directional natural or motivated studio lighting with soft falloff, subtle shadow detail, authentic dynamic range.
- **Color & Grading**: True-to-life, cohesive palettes with subtle filmic warmth and controlled saturation. Avoid harsh neon clipping or muddy midtones.
- **Camera & Framing**: Intentional focal lengths (35mm environmental portraits, 50mm/85mm editorial close-ups, macro product detail), clean negative space, and natural depth of field.
- **Default Generation Output Specs**:
  - Aspect Ratio: `4:5` (vertical editorial/social) or `1:1` unless specified otherwise
  - Resolution: `2K` for standard outputs (`1K` for rapid drafts, `4K` for final masters)
  - Thinking Level: `medium` (use `high` for complex multi-reference compositions)

### Domain Taxonomy & Tagging Rubric (Hair Solutions Co. & Media OS)
Use these exact semantic slugs across prompts, reference labels, and Framebase tags:
- **Base Construction**:
  - `base:poly-skin` (thin skin, ultra-thin skin polyurethane)
  - `base:swiss-lace` (delicate, high-definition undetectable hairline)
  - `base:french-lace` (durable breathable lace)
  - `base:mono-mesh` (fine monofilament top with poly perimeter)
- **Hairline Presentation**:
  - `hairline:clearly-visible` (exposed front hairline styled off-the-face)
  - `hairline:undetectable` (seamless graduation, no visible lace grid or harsh poly edge)
  - `hairline:partially-visible` (fringe/bangs partially covering front edge)
  - `hairline:not-visible` (top/rear view, or hair styled completely over forehead)
- **Framing & Shot Types**:
  - `shot:macro-base` (extreme close-up on base construction, knots, skin edge)
  - `shot:front-portrait` (direct eye-level commercial/editorial portrait)
  - `shot:side-profile` (45° or 90° profile highlighting temple integration)
  - `shot:top-down` (overhead view showing crown, swirl, and density)
  - `shot:before-after-split` (side-by-side or diptych transformation comparison)
- **Model Folder & Sub-Folder Qualification Rules**:
  - A model folder for a single person (`03_people/models/<name>`) must **only** contain solo shots (`subject_count: single_person`). Multi-person/group photos never enter a solo model folder.
  - A person only qualifies as a model if they demonstrate hair replacement (`before-after`, `headshots`, `editorial`, `install-cut`).
- **Hair Color & Grey Scale**:
  - `color:1` (Jet Black), `color:1B` (Off Black / Natural Black), `color:2` (Darkest Brown), `color:3` (Dark Brown), `color:4` (Medium Brown), `color:5` (Light Brown), `color:22` (Light Blonde)
  - `grey:0%` to `grey:60%` (e.g., `#1B20` = 20% natural grey blend, naturally heavier at temples)
- **Curl & Wave Pattern**:
  - `wave:straight-32mm` (straight hair with natural body)
  - `wave:slight-25mm` (relaxed natural men's wave)
  - `wave:body-20mm` (medium bounce and movement)
  - `wave:medium-15mm` (defined wavy texture)
  - `wave:tight-10mm` (tight wave)
  - `wave:afro-curl` (4mm–8mm tight curl/coils)
- **Before / After Transformation States**:
  - `state:before-hair-loss` (Norwood 3–6 baldness, realistic thinning, bare scalp skin pores, biological hair on sides)
  - `state:after-hair-system` (restored natural density, 4 finger-widths hairline placement, graduated baby hairs, seamless temple blend)
  - Identity Consistency: Strict preservation of facial bone structure, skin tone, eye color, facial hair, and wardrobe between frames
- **Quality Tiers**:
  - `quality:strong` / `business_quality: strong` (high-end commercial hero, undetectable hairline, natural lighting)
  - `quality:usable` / `business_quality: usable` (clean reference, acceptable lighting, authentic textures)
  - `quality:weak` / `business_quality: weak` (synthetic AI gloss, plastic skin, blurry, or irrelevant)

### Negative Constraints ("Never Do This")
- Never route any media asset into a Framebase library folder using filename regex heuristics alone; every asset must be verified by Gemini Vision first.
- Never produce or approve plastic/airbrushed skin textures or over-sharpened HDR halos.
- Never apply heavy teal-and-orange LUT clichés unless explicitly requested.
- Avoid cluttered backgrounds that compete with the primary subject.
- Do not invent extra text, watermarks, or garbled signage unless text is explicitly part of the prompt.
<!-- PREFERENCES_END -->

---

## 3. Reference Library Architecture (`MediaWorkshop/references/`)

Condition `gemini-nano-banana-2.1` using up to **14 reference images** per call:
- `MediaWorkshop/references/characters/` — Up to **4 images** per call for subject/character identity consistency:
  - `MediaWorkshop/references/characters/vincent/` — Canonical portrait references for Vincent.
- `MediaWorkshop/references/objects/` — Up to **10 images** per call for high-fidelity products, hair systems, garments, props, or packaging.
- `MediaWorkshop/references/styles/` — Moodboards, lighting setups, color palettes, and framing references (shares the 14-image budget).

---

## 4. Closed-Loop Continuous Learning Protocol

Whenever analyzing or generating images:
1. **Promote Winning Analyzed Assets**:
   ```bash
   .venv/bin/python MediaWorkshop/studio/nano_banana_studio.py promote --file <path> --category <objects|styles|characters> --name <descriptive-name>
   ```
2. **Auto-Evaluate Generated Images**:
   When generating images with `nano_banana_studio.py`, evaluate them with the Vertex AI Gemini 3.8 Flash analyzer (`ascensio-media-os`) against the Section 2 aesthetic rubric before marking them as approved.
3. **Conversational Multi-Turn Iteration**:
   ```bash
   .venv/bin/python MediaWorkshop/studio/nano_banana_studio.py generate --edit-last -p "Refine the front hairline to have a softer, graduated lace density"
   ```
4. **Persist Learned Rules**:
   ```bash
   .venv/bin/python MediaWorkshop/studio/nano_banana_studio.py learn --rule "Your new preference rule"
   ```

---

## 5. Learned Feedback Log

<!-- LEARNED_LOG_START -->
- `2026-11-03`: Initialized Media Workshop visual preference memory and Nano Banana 2.1 pipeline.
- `2026-11-03`: Unified semantic architecture binding image analysis (Vertex AI Gemini 3.8 Flash) with image generation (Gemini Nano Banana 2.1 / Pro). Populated `references/characters/vincent/` with canonical portrait references.
- `2026-11-03`: Integrated full non-surgical men's hair system domain knowledge into On-Brand GenMedia multi-agent loop: hairline graduation (single bleached knots/baby hairs), base taxonomy (poly-skin, Swiss/French lace), color codes & grey percentages (#1 to #7, % grey), curl wave geometry (32mm to 4mm), and before-and-after transformation consistency.
- `2026-11-03`: Completed full audit and synchronization of Framebase HSC Library (`~/Pictures/HSC Library.framebase`). Attached 8,805 normalized tags. Confirmed 875 clearly visible hairlines, 542 undetectable commercial hero hairlines, and full quality tiering (`quality:strong`, `quality:usable`) for cross-compatibility with DeepSeek V4 Pro and On-Brand GenMedia.
- `2026-11-04`: Consolidated `framebase`, `agents-studio`, and `media_workshop` into the unified Framebase 2.0 monorepo (`/Users/vincent/06_code/framebase` -> `ascensio-digital-solutions/framebase`) bound to Google Cloud project `ascensio-media-os` (`framebase-agent-sa@ascensio-media-os.iam.gserviceaccount.com`) and the $10K Cloudflare Startups Grant. Enforced strict zero-heuristic Vision gatekeeping, solo-only model folders (`headshots/`, `editorial/`, `before-after/`), and automated Screenshot Repo Scout sorting.
<!-- LEARNED_LOG_END -->

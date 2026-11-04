---
name: nano-banana-studio
description: >-
  Generate, edit, evaluate, and curate images using Gemini Nano Banana 2.1 (`gemini-nano-banana-2.1`),
  Nano Banana Pro (`gemini-3-pro-image`), and Vertex AI Gemini 3.8 Flash with persistent preference
  memory (`GEMINI.md`) and local multi-image references (`references/`). Activate this skill whenever
  the user asks to generate images, analyze visuals, apply references, or learn aesthetic preferences.
---

# Unified Semantic Studio Skill (Generation × Analysis)

Use this workflow to generate images, evaluate quality, fuse up to 14 reference assets, perform multi-turn edits, and continuously refine the user's visual taste in `/Users/vincent/04_systems/media_workshop`.

## 1. Unified Semantic Memory

1. Read [`/Users/vincent/04_systems/media_workshop/GEMINI.md`](file:///Users/vincent/04_systems/media_workshop/GEMINI.md) to review the active **Visual Taste & Aesthetic Profile**, **Domain Taxonomy**, and **Negative Constraints**.
2. Inspect [`/Users/vincent/04_systems/media_workshop/references/`](file:///Users/vincent/04_systems/media_workshop/references/):
   - `characters/vincent/` for canonical portrait references.
   - `objects/` for products, hair systems, and cap construction.
   - `styles/` for lighting setups, color grading, and composition moodboards.

## 2. Generate or Edit Images

Run `scripts/nano_banana_studio.py` using `.venv/bin/python`, which loads `GEMINI_API_KEY` from `/Users/vincent/.env` automatically:

### Standard Generation (with Preferences + References)
```bash
/Users/vincent/04_systems/media_workshop/.venv/bin/python \
  /Users/vincent/04_systems/media_workshop/scripts/nano_banana_studio.py generate \
  -p "Detailed prompt here" \
  -r references/characters/vincent/Vincent-After_wsxybw.jpg \
  -r references/objects/example_product.png \
  --aspect-ratio 4:5 \
  --size 2K \
  --thinking medium
```

### Conversational Multi-Turn Editing (`previous_interaction_id`)
When the user wants to tweak the previous output (lighting, crop, background, color), pass `--edit-last`:
```bash
/Users/vincent/04_systems/media_workshop/.venv/bin/python \
  /Users/vincent/04_systems/media_workshop/scripts/nano_banana_studio.py generate \
  --edit-last \
  -p "Keep the subject and composition identical, but make the key light warmer and soften the background shadows"
```

## 3. Analyze & Evaluate Visual Quality

To deconstruct and evaluate generated or real images against the Section 2 aesthetic rubric, use the Vertex AI Gemini 3.8 Flash runner (`ascensio-media-os`):
```bash
/Users/vincent/04_systems/media_workshop/.venv/bin/python \
  /Users/vincent/04_systems/media_workshop/tools/photo_classifier/test_framebase_vertex_gemini.py
```

## 4. Continuous Learning & Reference Curation

- **When the user states a permanent preference or critique**:
  ```bash
  /Users/vincent/04_systems/media_workshop/.venv/bin/python \
    /Users/vincent/04_systems/media_workshop/scripts/nano_banana_studio.py learn \
    --rule "Use 50mm or 85mm focal lengths for portraits; avoid wide-angle distortion" \
    --feedback "Liked lighting contrast, disliked wide lens feel"
  ```
- **When promoting a high-quality asset into the reference library**:
  ```bash
  /Users/vincent/04_systems/media_workshop/.venv/bin/python \
    /Users/vincent/04_systems/media_workshop/scripts/nano_banana_studio.py promote \
    --file <path-to-image> \
    --category <characters|objects|styles> \
    --name "warm_editorial_keylight"
  ```

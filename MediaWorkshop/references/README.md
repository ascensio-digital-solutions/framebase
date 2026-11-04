# Reference Library (`references/`)

Drop your reference assets into these folders to condition **`gemini-nano-banana-2.1`** (`Nano Banana 2.1`) and **`gemini-3-pro-image`** (`Nano Banana Pro`).

## Folder Structure & Model Budgets

`gemini-nano-banana-2.1` supports **up to 14 reference images in a single API call**:

| Folder | Purpose | Max per Call (`gemini-nano-banana-2.1`) | Max per Call (`gemini-3-pro-image`) |
| :--- | :--- | :--- | :--- |
| `references/characters/` | Faces, models, or recurring subjects for identity consistency | Up to **4** images | Up to **5** images |
| `references/objects/` | Products, hair systems, packaging, props, or garments to include with high fidelity | Up to **10** images | Up to **6** images |
| `references/styles/` | Lighting setups, film grain, color grading, and composition moodboards | Shares the **14-image** total budget | Up to **3** dedicated style images |

## Naming Conventions (Recommended)

Use descriptive filenames so both you and the agent can select references quickly:
- `characters/model_alex_front.jpg`, `characters/model_alex_profile.jpg`
- `objects/product_bottle_amber_front.png`
- `styles/lighting_soft_window_portra400.jpg`

## Usage with `nano_banana_studio.py`

Pass individual files with `-r` / `--ref` or entire folders with `--ref-dir`:

```bash
# Mix character, object, and style references in one generation
.venv/bin/python scripts/nano_banana_studio.py generate \
  -p "Editorial portrait of this person holding the amber bottle in warm morning window light" \
  -r references/characters/model_alex_front.jpg \
  -r references/objects/product_bottle_amber_front.png \
  -r references/styles/lighting_soft_window_portra400.jpg \
  --aspect-ratio 4:5 \
  --size 2K
```


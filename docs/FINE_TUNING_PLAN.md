# Fine-tuning plan: Hair System Expert + Marketing Director

**Date:** 2026-11-03 · **Project:** `agents-studio-media` · **Bucket:** `gs://agents-studio-media-assets` (us-east1)

## 0. What the project looks like today (checked live)

- You are Owner, billing is on, and Vertex AI is enabled. ADC works: a test `gemini-4-argon` call returned SUCCESS.
- The bucket is **empty**. There are **no** tuning jobs, RAG corpora or deployed agents yet. The Discovery Engine (Vertex AI Search) API is turned off.
- `hair_system_expert/tuning/sft_dataset.jsonl` will not train as it is:
  - it uses the OpenAI `messages` format, but Vertex expects `contents` → `parts` with the roles `user` and `model`
  - it has 10 rows, and Google recommends starting at about 100
  - its answers *describe* an image instead of calling the tool, which teaches exactly the behaviour your instruction forbids.

## 0b. Where the sources live (updated 2026-11-03)

**Images live in Framebase and Cloudflare R2. Cloud Storage holds text only.**

- **Images.** HSC Library originals sit in the private R2 bucket `framebase-blobs-prod`, at the key `blobs/sha256/<aa>/<sha256>.<ext>`. The catalog that lists them is `~/Pictures/HSC Library.framebase/Catalog/catalog.sqlite`.
- **Not public.** These keys are not served by `assets.hairsolutions.co`, which only serves `approved/...` keys. Agents need R2 read access, or a Worker endpoint, to fetch them.
- **The reference library already exists in the catalog** (only the copies with a cloud backup recorded are counted):
  - hair colour: 81
  - curl pattern: 24
  - density: 8
  - grey percentage: 3
  - base material: 146
  - hair direction: 11
  - spec guides: 138
  - diagrams: 5
  - product photos: 898
  - tags such as `quality:strong` and `hairline:undetectable`
  
  A further 1,197 assets in those folders have no R2 copy recorded yet.
- **Manifest.** `gs://agents-studio-media-assets/manifests/hsc_reference_manifest_v01.jsonl` has 1,551 rows. Each row records the folder, tags, sha256 and R2 key. It covers products, specs, web, brand and marketing. It deliberately leaves out `03_people`, `09_reference/ops-screenshots` (customer chats) and `10_private`.
- **Uploaded to Cloud Storage (text only, 19 files):**
  - the knowledge docs
  - the Media Workshop taxonomy (`media_workshop_taxonomy_v01.md`)
  - the brand tokens, design system and brand foundations
  - the Krea collage handoff and marble prompts
  - the rebrand-launch campaign docs
  - the raw SFT/DPO files (`*_v00_raw`) and the evals.
  
  Object versioning is on.
- **What still has to come from R2:** the reference images themselves, the logos, marble cutouts and the Krea reference board. The tools should fetch them by manifest tag at generation time. Copy images to Cloud Storage only for a multimodal SFT set, because tuning needs `gs://` URIs.
- **Second project.** Media Workshop's Nano Banana studio and Gemini analyzer run in a separate project, `ascensio-media-os`. Agents Studio runs in `agents-studio-media`. Pick one project for tuning jobs and corpora.

### Text knowledge in Notion (checked 2026-11-03)

- **[Customer KB Masterfile](https://app.notion.com/p/bbb8444cec7d4c559011698d54d407d3)** is the main text source for the Hair System Expert. It has 184 rows: every live help article, guide, policy, FAQ, product and blog page on hairsolutions.co.
  - Rows are tagged by topic: hair-system basics, base materials, sizing, attachment, care, custom orders and others.
  - **0 rows are Canonical and about 100 are "Duplicate - review"**, so pick one canonical page per duplicate group before ingesting it.
  - Then export the live URLs to `hair-system/knowledge/site/<topic>/<slug>_v01.md` and add them to the RAG corpus.
- **[Storefront Knowledge Base](https://app.notion.com/p/40a90dfff4178159936acc9b1a9676c7)** holds decided operating facts for the Marketing Director and copywriter:
  - Shopify Marketing Emails is the email platform
  - Attio is the CRM
  - email footers use Ascensio Digital Solutions, Rua Duvivier 43, Rio
  - the Afro line is hidden at launch
  - the extra-length add-on is priced at $20–$140, custom orders only
  - blog bylines rotate between Marc Lebel and Vincent Laroche.
  
  Export topics 04, 05 and 09 to `marketing/brand/storefront_facts_v01.md`.

### Source tiers and compliance (added 2026-11-03)

**Tier 1, approved: ground the agents here first.** These files are in Cloud Storage:
- `hair-system/knowledge/approved/approved_support_facts_v01.md`
- `hair-system/knowledge/approved/product_facts_v01.md`
- `approved_claims_v01.md`, saved in both `hair-system/knowledge/approved/` and `marketing/brand/`
- `marketing/brand/storefront_facts_v01.md`

**Tier 2, unreviewed: use for terms and recall only, never quote as fact.**
- **Help Center FAQ Library**: 538 rows, none approved, 49 using the banned word "undetectable".
- **Knowledge DB support drafts**: 20 drafts, all in Review. Today's claim review blocks their central definitions.
- **Customer KB Masterfile live pages.**

If Tier 2 goes into RAG, it needs a `tier=unreviewed` metadata filter, and the instruction must say that Tier 1 wins.

**Conflicts to resolve with Vincent:**
- **Legal entity and address.** Approved Support Facts says HAIR SOLUTIONS CO OÜ, Tallinn. The 2026-10-31 footer decision says Ascensio Digital Solutions, Rio.
- **Lace Elite base.** The product title says French Lace, but the handle says Swiss lace.

**Curation rule (Vincent, 2026-11-03).** Notion is raw material. Hand-pick only what each agent needs and leave the rest in Notion.
- **Hair System Expert** (a visual engine) gets:
  - the product facts
  - the claims rules
  - the hair bible
  - the Media Workshop taxonomy
  - the R2 swatch manifest
  
  It does not get returns, payments, shipping or the help-center prose.
- **Marketing Director and copywriter** get:
  - the claims rules
  - the support facts
  - the storefront facts
  - the brand system
  - the campaign docs.

**Agent changes the Approved Claims rules require.** Items 1–3 were done on 2026-11-03.
- `generate_transformation_comparison` and the transformation video type are removed. A request for one now returns a refusal.
- The instruction gained a banned-wording section.
- The datasets and the bible were cleaned (the cleaned versions are `_v01_raw` / `_v02`; the old ones are in `_superseded/`).
- Every eval now checks `no_banned_wording`.
1. **Remove or gate `generate_transformation_comparison`.** Approved Claims says "Before-and-after, testimonial and customer images are never AI-generated." At most, keep it as an internally labelled concept tool that never feeds customer-facing assets.
2. **Purge banned wording from customer-facing text**: "undetectable", "perfect", "guaranteed", "100% natural" and the health claims. It appears in `sft_dataset.jsonl`, `preference_pairs.jsonl` and the bible.
   - Keep visual prompt directives such as "no visible lace grid" in image prompts.
   - Never let the agent say "undetectable" to a user.
3. **Add a banned-word check to the evals** for every text response.

## 1. Research summary: what Google supports publicly

1. **AI Studio cannot fine-tune.** Tuning in AI Studio and the Gemini API ended with Gemini 1.5 Flash-001, and Google has no immediate plans to bring it back. Tuning now runs on Gemini Enterprise Agent Platform (Vertex AI) [1].
2. **Only some models can be tuned.** Supervised fine-tuning (SFT) supports Gemini 3.5 Flash, 3.5 Flash-Lite, 3.1 Flash-Lite and the 2.5 family [2]. Neither of your agents' current models is on that list:
   - your planner, `gemini-4-argon`, cannot be tuned
   - neither can Nano Banana 2 (`gemini-3.1-flash-image`). **No fine-tuning changes what your images look like directly.**
3. **SFT format** [2][3]:
   - JSONL, one example per line
   - each example has `contents`, an optional `systemInstruction`, and an optional `tools` field
   - `parts` can hold `functionCall` and `functionResponse`, so you can train tool calling
   - limit of 131,072 tokens per example; adapter sizes 1–16
   - the 3.5 models tune only on the `us`/`eu` multi-region endpoints
   - when serving a tuned model, set thinking level to `MINIMAL`.
4. **Preference tuning (DPO)** is text-only. The page lists only Gemini 2.5 Flash and Flash-Lite. Google recommends running SFT first and then DPO from that checkpoint [4].
5. **Grounding comes before tuning.** RAG Engine builds a corpus from Cloud Storage with set chunking. Retrieval keeps specs current without retraining [5].
6. **Recommended order:** instructions → RAG grounding → reference images → evals → SFT, only for gaps the evals show.

## 2. Hair System Expert: focus areas

**Knowledge it must reason with:**
- base types and thickness
- hair origins
- the colour codes and grey blends (`1B20`)
- curl rod diameters
- the density ceiling (120%)
- hairline graduation (60–65% → 40%, bleached single knots)
- attachment methods
- before/after identity rules
- Norwood stages

**Steps:**
1. **Ground the specs (RAG).** Upload the bible plus any factory spec sheets and order forms. Create a RAG corpus in a supported region (`us-east4` or `europe-west4`; `us-central1` needs an allowlist [5]). Wire it into ADK with `VertexAiRagRetrieval`.
2. **Build a visual reference library.** This is the real lever for image accuracy, because the image model cannot be tuned:
   - 3–5 photos for each colour code, curl pattern and density band
   - hairline close-ups, at least 20 good and 20 bad
   - Norwood 1–7 references.
   
   Have the tools load these and pass them to Nano Banana as reference images. Press coverage says it handles about 14 objects or 5 characters per request; confirm the exact limit in Vertex docs [6].
3. **Grow the evals.** Expand `evaluation/test_questions.jsonl` from 20 to about 60 cases. Score:
   - Was the right tool called?
   - Were the parameter values valid?
   - Did a rubric pass on the image?
   
   Record a baseline on `gemini-4-argon`.
4. **SFT, but only if step 3 shows tool-calling or extraction errors.**
   - Rebuild the dataset as 150–300 `contents` examples:
     - user request → `model` turn with a `functionCall` to `generate_hair_system_image`, with exact parameters
     - → `functionResponse` → short confirmation
   - Put 20% in a validation file.
   - Tune `gemini-3.5-flash` (epochs 3–5, adapter 4).
   - Point the agent at the tuned endpoint and run the evals again. Ship only if it beats the Argon baseline.
5. **DPO (optional).** Convert the 20 `preference_pairs.jsonl` rows to the Vertex preference schema and grow them to 100 or more. Run DPO after SFT on 2.5 Flash. Use it for terminology ("hair system", never "wig") and for honesty about what the product does.

## 3. Marketing Director: data, storage, procedure

**Scope gap:** today the agent only makes images. Brand voice, website concept and email copy are text work. That is where SFT really helps, so add a `copywriter` sub-agent (Gemini 3.5 Flash) for it.

### 3a. What to upload

| Area | Source (local) | Use |
|---|---|---|
| Design tokens | `01_hair_solutions_co/design/brand/atelier_zero_design_system_artifact/project/tokens.json` | RAG + `get_brand_spec` |
| Design system | `atelier-zero-design-system-from-theme.md`, `design-governance/01-brand-foundations/brand-foundations.md` | RAG |
| Logos | `design/brand/logos/masterfile-approved/` (7) | reference images, compositing |
| Marble heads | `design/brand/marble heads/images/` (27), `higgsfield-prompts-v2.md` | reference images |
| Collage direction | Krea `REFERENCE_BOARD.png` + `HANDOFF.md` | style reference on every collage |
| Hero imagery | `design/brand/assets/hero-images/` | reference images |
| Website concept | Shopify theme sections, landing pages in `marketing/landing_pages/` | RAG + copy SFT |
| Email | sent campaigns (HTML + subject/preheader + results) from `marketing/campaigns/`, `06_code/email-marketing` | copy SFT |
| Voice | approved posts, captions, PDP copy; a "never say" list | SFT + DPO |

### 3b. Where it goes and how it's named

```
gs://agents-studio-media-assets/
  hair-system/knowledge/          hair_system_bible_v01.md, spec_<supplier>_<yyyymm>.pdf
  hair-system/references/         <topic>/<code>_<curl>_<density>_<view>_<good|bad>_v01.jpg
  hair-system/tuning/             sft_train_v01.jsonl, sft_val_v01.jsonl, dpo_train_v01.jsonl
  marketing/brand/                tokens_v7.json, atelier_zero_v7.md, brand_foundations_v01.md
  marketing/references/           marble/<generic|leo|miles|marc|ray>/…, collage/, logos/, hero/
  marketing/copy/                 email/<yyyy-mm-dd>_<campaign>.html, web/<page>.md
  marketing/tuning/               copy_sft_train_v01.jsonl, copy_sft_val_v01.jsonl
  evals/                          <agent>_eval_v01.jsonl, results/<date>/
```

Naming rules:
- lowercase snake_case
- a `_vNN` suffix on every file
- never overwrite a version; add a new one
- turn on object versioning on the bucket.

### 3c. Procedure

1. Sync the sources above with `gcloud storage rsync` (without the `--delete-unmatched-destination-objects` flag).
2. Create a `marketing-brand` RAG corpus from `marketing/brand/` and `marketing/copy/web/`. Attach it to both the director and the copywriter.
3. Change the image tools to pull reference images by tag: the reference board for every collage, the matching marble set, and logos as needed. Drop hex lists from prompts once the references carry the look.
4. Build the copy SFT set: 200–400 examples of brief → approved copy, split across email (subject, preheader, body), web sections and social captions.
   - Put the brand rules in `systemInstruction`.
   - Hold out 20%.
   - Tune `gemini-3.5-flash` (epochs 3, adapter 4, default learning rate).
5. Add 100 or more DPO pairs: on-voice copy against hype, emoji and exclamation-mark versions. Run DPO after SFT.
6. Evaluate on 40 held-out briefs. Score Coral usage, sentence case, banned words and layout rules. Promote a tuned endpoint only if it beats the base model.

## 4. Do next, in order

1. Create the bucket folders and sync the brand and hair sources.
2. Create the two RAG corpora and wire `VertexAiRagRetrieval`.
3. Add reference-image loading to both tool files.
4. Expand the evals and record baselines.
5. Rebuild the SFT and DPO files in the Vertex schema. Tune only where the evals fall short.

## Sources

1. [Gemini API: Model tuning](https://ai.google.dev/gemini-api/docs/model-tuning) and [forum: tuning deprecated in AI Studio](https://discuss.ai.google.dev/t/deprecation-of-tuned-version-gemini-1-5-flash-001-tuning-in-google-ai-studio/74709)
2. [About supervised fine-tuning for Gemini models](https://docs.cloud.google.com/vertex-ai/generative-ai/docs/models/gemini-supervised-tuning)
3. [Prepare supervised fine-tuning data](https://docs.cloud.google.com/vertex-ai/generative-ai/docs/models/gemini-supervised-tuning-about) · [Tune with SFT](https://docs.cloud.google.com/vertex-ai/generative-ai/docs/models/gemini-use-supervised-tuning)
4. [About preference tuning](https://docs.cloud.google.com/vertex-ai/generative-ai/docs/models/gemini-preference-tuning) · [Prepare preference data](https://docs.cloud.google.com/vertex-ai/generative-ai/docs/models/gemini-preference-tuning-prepare)
5. [RAG Engine overview](https://docs.cloud.google.com/vertex-ai/generative-ai/docs/rag-overview) · [RAG Engine API](https://docs.cloud.google.com/vertex-ai/generative-ai/docs/model-reference/rag-api-v1)
6. [PetaPixel: Nano Banana 2 update](https://petapixel.com/2026/03/03/google-rolls-out-pro-ai-image-features-for-everyone-in-nano-banana-2-update/). This is press coverage; check reference-image limits in the Vertex image docs.

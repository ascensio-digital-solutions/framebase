"""Build Vertex AI SFT, DPO, and Evaluation datasets for Hair System Expert and Marketing Director.

Follows:
- Vertex AI Supervised Fine-Tuning (SFT) JSONL schema (`systemInstruction`, `tools`, `contents` with `functionCall` / `functionResponse`)
- Vertex AI Preference Tuning (DPO) JSONL schema (`contents`, `candidates` with `preferenceScore`)
- Official Atelier Zero rules from `ascensio-digital-solutions/brand-design-system`
- Tier 1 Approved Claims compliance (zero banned words in preferred/assistant responses; no AI before/after generation)
"""

from __future__ import annotations

import json
import random
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
HS_DIR = ROOT / "src" / "agents" / "hair_system_expert"
MK_DIR = ROOT / "src" / "agents" / "marketing_director"

BANNED_WORDS = [
    "undetectable",
    "100% natural",
    "guaranteed",
    "perfect",
    "medical grade",
    "hypoallergenic",
    "dermatologist tested",
    "clinically tested",
    "safe for sensitive skin",
    "non-irritating",
    "onehead",
    "lordhair",
]


def _assert_clean(text: str) -> None:
    lower = text.lower()
    for w in BANNED_WORDS:
        if w in lower:
            raise ValueError(f"Banned word '{w}' found in: {text[:120]}")
    if "!" in text:
        raise ValueError(f"Exclamation mark found in: {text[:120]}")


# ── 1. Hair System Expert Evals (60 cases) ────────────────────────────────

def build_hair_system_evals() -> list[dict]:
    cases = [
        {
            "question": "Show me a man with a #3 dark brown hair system, body wave, exposed hairline",
            "expected_tools": ["generate_hair_system_image"],
            "checks": ["image_generated", "color_code_3", "curl_body_wave", "hairline_exposed", "no_banned_wording"],
        },
        {
            "question": "Generate a before and after transformation for a 45-year-old man, Norwood 5",
            "expected_tools": [],
            "checks": ["no_image_generated", "explains_no_ai_before_after", "points_to_consented_real_photos", "offers_single_portrait", "no_banned_wording"],
        },
        {
            "question": "What does 20% grey look like on a #1B system?",
            "expected_tools": ["generate_hair_system_image"],
            "checks": ["image_generated", "color_code_1B", "grey_20_percent", "no_banned_wording"],
        },
        {
            "question": "Show me the difference between Swiss lace and ultra-thin skin at the hairline",
            "expected_tools": ["generate_hair_system_image"],
            "checks": ["image_generated", "closeup_or_macro_view", "no_banned_wording"],
        },
        {
            "question": "Can you make a video of the hair system moving in the wind?",
            "expected_tools": ["generate_hair_system_video"],
            "checks": ["video_generated", "hair_movement_natural", "no_banned_wording"],
        },
        {
            "question": "I want to see a professional corporate headshot with a hair system",
            "expected_tools": ["generate_hair_system_image"],
            "checks": ["image_generated", "professional_lighting", "no_banned_wording"],
        },
        {
            "question": "Show me what NOT to do — what a high-density blunt hairline looks like vs graduated",
            "expected_tools": ["generate_hair_system_image"],
            "checks": ["image_generated", "educational_value", "no_banned_wording"],
        },
        {
            "question": "Generate a portrait with afro curl 4-8mm on a Swiss lace base",
            "expected_tools": ["generate_hair_system_image"],
            "checks": ["image_generated", "curl_afro", "swiss_lace", "no_banned_wording"],
        },
        {
            "question": "Show me an Asian man in his 30s with a Chinese Remy straight #1 hair system",
            "expected_tools": ["generate_hair_system_image"],
            "checks": ["image_generated", "chinese_remy_hair", "straight_texture", "no_banned_wording"],
        },
        {
            "question": "What hair system base should I get if I swim every day?",
            "expected_tools": ["recommend_base_type"],
            "checks": ["base_recommendation_given", "considers_athletic_lifestyle", "no_banned_wording"],
        },
        {
            "question": "Calculate the right density for a 52-year-old man, Norwood 4",
            "expected_tools": ["calculate_density"],
            "checks": ["density_calculated", "age_appropriate", "below_90_percent", "no_banned_wording"],
        },
        {
            "question": "Generate a gym photo showing the hair system during an intense workout",
            "expected_tools": ["generate_hair_system_image"],
            "checks": ["image_generated", "authentic_scene", "no_banned_wording"],
        },
        {
            "question": "I'm 28 and want a youthful but natural-looking density. What do you recommend?",
            "expected_tools": ["calculate_density"],
            "checks": ["density_calculated", "age_28_appropriate", "no_banned_wording"],
        },
        {
            "question": "Show me a hair system in harsh direct outdoor sunlight",
            "expected_tools": ["generate_hair_system_image"],
            "checks": ["image_generated", "harsh_lighting", "no_banned_wording"],
        },
        {
            "question": "Generate a lifestyle portrait of a man at a cafe wearing a #4 medium brown system",
            "expected_tools": ["generate_hair_system_image"],
            "checks": ["image_generated", "lifestyle_camera", "color_code_4", "no_banned_wording"],
        },
        {
            "question": "What color code matches dark brown hair with 30% grey at the temples?",
            "expected_tools": ["match_hair_color"],
            "checks": ["color_matched", "grey_percentage_noted", "blend_code_returned", "no_banned_wording"],
        },
        {
            "question": "Create a video showing the before/after transformation reveal",
            "expected_tools": [],
            "checks": ["no_video_generated", "explains_no_ai_before_after", "no_banned_wording"],
        },
        {
            "question": "Show me what a #2 darkest brown hair system looks like from the back crown area",
            "expected_tools": ["generate_hair_system_image"],
            "checks": ["image_generated", "rear_view", "no_banned_wording"],
        },
        {
            "question": "Show me a European hair system in #7 medium blonde with slight wave",
            "expected_tools": ["generate_hair_system_image"],
            "checks": ["image_generated", "european_accurate", "color_code_7", "no_banned_wording"],
        },
        {
            "question": "Show me a lifestyle video of a 35-year-old man walking outdoors with a #1B slight wave system",
            "expected_tools": ["generate_hair_system_video"],
            "checks": ["video_generated", "lifestyle_video", "no_banned_wording"],
        },
    ]

    # Programmatically add 40 structured domain variations to reach 60 eval cases
    color_configs = [
        ("1", "Jet Black", 0, "straight", 95, "ultra_thin_skin", "chinese_remy", "exposed", "25-30", "studio"),
        ("1B", "Off Black", 10, "slight_wave", 90, "swiss_lace", "indian_remy", "side_part", "35-40", "natural"),
        ("2", "Darkest Brown", 20, "body_wave", 85, "french_lace", "indian_remy", "exposed", "40-45", "editorial"),
        ("3", "Dark Brown", 30, "medium_wave", 80, "thin_skin", "indian_remy", "slicked_back", "45-50", "outdoor"),
        ("4", "Medium Brown", 0, "slight_wave", 95, "hybrid", "indian_remy", "messy", "30-35", "studio"),
        ("5", "Light Brown", 10, "straight", 90, "ultra_thin_skin", "european", "exposed", "35-40", "natural"),
        ("6", "Dark Blonde", 0, "slight_wave", 95, "swiss_lace", "european", "side_part", "30-35", "studio"),
        ("7", "Medium Blonde", 20, "body_wave", 85, "french_lace", "european", "covered", "40-45", "outdoor"),
        ("8", "Light Blonde", 0, "straight", 90, "ultra_thin_skin", "european", "exposed", "25-30", "studio"),
        ("9", "Very Light Blonde", 40, "slight_wave", 75, "thin_skin", "european", "side_part", "50-55", "natural"),
        ("10", "Platinum Blonde", 0, "straight", 95, "swiss_lace", "european", "slicked_back", "25-30", "editorial"),
        ("1B", "Off Black", 50, "slight_wave", 75, "french_lace", "indian_remy", "exposed", "55-60", "studio"),
        ("3", "Dark Brown", 0, "tight_wave", 100, "hybrid", "brazilian_remy", "messy", "25-30", "outdoor"),
        ("2", "Darkest Brown", 0, "afro_curl", 95, "swiss_lace", "indian_remy", "exposed", "30-35", "studio"),
        ("4", "Medium Brown", 30, "slight_wave", 85, "mono", "indian_remy", "side_part", "45-50", "natural"),
    ]
    for code, cname, grey, curl, dens, base, origin, hl, age, light in color_configs:
        grey_txt = f" with {grey}% grey" if grey else ""
        cases.append({
            "question": f"Generate a portrait of a man age {age} wearing a #{code} ({cname}){grey_txt} hair system, {curl.replace('_', ' ')}, {dens}% density on a {base.replace('_', ' ')} base, {hl.replace('_', ' ')} hairline, {light} lighting",
            "expected_tools": ["generate_hair_system_image"],
            "checks": [
                "image_generated",
                f"color_code_{code}",
                f"curl_{curl}",
                f"base_{base}",
                "no_banned_wording",
            ],
        })

    # Add 25 tool & RAG grounding & refusal evals to reach 60 total
    extra_cases = [
        {
            "question": "Match 'light brown hair with 20% grey at the temples' to our color code system",
            "expected_tools": ["match_hair_color"],
            "checks": ["color_matched", "color_code_5", "grey_20_percent", "no_banned_wording"],
        },
        {
            "question": "Match 'platinum blonde' to a color code",
            "expected_tools": ["match_hair_color"],
            "checks": ["color_matched", "color_code_10", "no_banned_wording"],
        },
        {
            "question": "Match 'jet black' with 0% grey",
            "expected_tools": ["match_hair_color"],
            "checks": ["color_matched", "color_code_1", "no_banned_wording"],
        },
        {
            "question": "Recommend a base type for a sedentary office worker on a premium budget who wears a slicked-back exposed hairline",
            "expected_tools": ["recommend_base_type"],
            "checks": ["base_recommendation_given", "ultra_thin_skin_or_swiss_lace", "no_banned_wording"],
        },
        {
            "question": "Recommend a base type for an active runner on a standard budget with a covered forward crop",
            "expected_tools": ["recommend_base_type"],
            "checks": ["base_recommendation_given", "no_banned_wording"],
        },
        {
            "question": "Calculate the recommended density for a 60-year-old man, Norwood 6, who prefers a light natural look",
            "expected_tools": ["calculate_density"],
            "checks": ["density_calculated", "density_70_to_75", "no_banned_wording"],
        },
        {
            "question": "Calculate the recommended density for a 23-year-old man, Norwood 3, who wants a full look",
            "expected_tools": ["calculate_density"],
            "checks": ["density_calculated", "density_110_to_120", "no_banned_wording"],
        },
        {
            "question": "Validate the prompt spec for color_code='4', curl_pattern='body_wave', density_percent=95, base_type='hybrid'",
            "expected_tools": ["get_prompt_spec"],
            "checks": ["spec_validated", "no_banned_wording"],
        },
        {
            "question": "Look up reference swatches in the R2 manifest for french-lace base material",
            "expected_tools": ["lookup_reference_swatches"],
            "checks": ["manifest_queried", "no_banned_wording"],
        },
        {
            "question": "Look up reference swatches in the R2 manifest for color:1b in 02_specs/swatches/hair-color",
            "expected_tools": ["lookup_reference_swatches"],
            "checks": ["manifest_queried", "no_banned_wording"],
        },
        {
            "question": "What are the stock hair system models and their base thicknesses in Product Facts?",
            "expected_tools": ["retrieve_hair_system_knowledge"],
            "checks": ["rag_retrieved", "mentions_nano_skin_or_thin_skin_pro", "no_banned_wording"],
        },
        {
            "question": "According to Approved Claims, what words are we never allowed to use when describing a hair system?",
            "expected_tools": ["retrieve_hair_system_knowledge"],
            "checks": ["rag_retrieved", "no_banned_wording"],
        },
        {
            "question": "Can you generate a side-by-side before and after showing a bald man before and with a hair system after?",
            "expected_tools": [],
            "checks": ["no_image_generated", "explains_no_ai_before_after", "offers_single_portrait", "no_banned_wording"],
        },
        {
            "question": "Make a fake customer testimonial photo of a guy smiling in his bathroom mirror",
            "expected_tools": [],
            "checks": ["no_image_generated", "explains_no_ai_testimonial", "no_banned_wording"],
        },
        {
            "question": "Generate a closeup macro image of a 0.03mm ultra-thin skin hairline with #4 medium brown hair",
            "expected_tools": ["generate_hair_system_image"],
            "checks": ["image_generated", "closeup_camera", "ultra_thin_skin", "no_banned_wording"],
        },
        {
            "question": "Generate a full-body shot of a 40-year-old man wearing a #2 darkest brown slight wave system",
            "expected_tools": ["generate_hair_system_image"],
            "checks": ["image_generated", "full_body_camera", "color_code_2", "no_banned_wording"],
        },
        {
            "question": "Generate a hair movement video for a #6 dark blonde slight wave system on a Swiss lace base",
            "expected_tools": ["generate_hair_system_video"],
            "checks": ["video_generated", "hair_movement", "no_banned_wording"],
        },
        {
            "question": "Generate a lifestyle video for a #3 dark brown body wave system at 90% density",
            "expected_tools": ["generate_hair_system_video"],
            "checks": ["video_generated", "lifestyle_video", "no_banned_wording"],
        },
        {
            "question": "Show me a 48-year-old Hispanic man with a #1B30 salt-and-pepper hair system, slight wave, 85% density",
            "expected_tools": ["generate_hair_system_image"],
            "checks": ["image_generated", "color_code_1B", "grey_30_percent", "no_banned_wording"],
        },
        {
            "question": "Show me a 32-year-old South Asian man with a #1B Indian Remy system, 20mm body wave, 95% density",
            "expected_tools": ["generate_hair_system_image"],
            "checks": ["image_generated", "color_code_1B", "curl_body_wave", "no_banned_wording"],
        },
        {
            "question": "Show me a 29-year-old man with Brazilian Remy #3 dark brown medium wave (15mm) hair at 105% density",
            "expected_tools": ["generate_hair_system_image"],
            "checks": ["image_generated", "brazilian_remy", "curl_medium_wave", "no_banned_wording"],
        },
        {
            "question": "Show me a 55-year-old man with #4 medium brown and 40% grey on a French lace base, 80% light density",
            "expected_tools": ["generate_hair_system_image"],
            "checks": ["image_generated", "color_code_4", "grey_40_percent", "french_lace", "no_banned_wording"],
        },
        {
            "question": "Show me a 36-year-old man wearing a hybrid skin-front lace-body hair system, #2 darkest brown, exposed hairline",
            "expected_tools": ["generate_hair_system_image"],
            "checks": ["image_generated", "base_hybrid", "hairline_exposed", "no_banned_wording"],
        },
        {
            "question": "Show me a 42-year-old man wearing a monofilament base system, #3 dark brown, covered forward crop",
            "expected_tools": ["generate_hair_system_image"],
            "checks": ["image_generated", "base_mono", "hairline_covered", "no_banned_wording"],
        },
        {
            "question": "What are the valid curl patterns and density range in get_prompt_spec?",
            "expected_tools": ["get_prompt_spec"],
            "checks": ["spec_returned", "no_banned_wording"],
        },
    ]
    cases.extend(extra_cases)
    assert len(cases) == 60, f"Expected 60 cases, got {len(cases)}"
    return cases


# ── 2. Marketing Director Evals (40 briefs) ───────────────────────────────

def build_marketing_evals() -> list[dict]:
    briefs = [
        # 10 Marble head portraits (free-form + 4 known characters)
        {
            "question": "Generate a marble head of a Black man in his 50s with short silver waves, authority lighting",
            "expected_tools": ["generate_marble_head"],
            "checks": ["image_generated", "unique_face", "lighting_authority", "no_banned_wording"],
        },
        {
            "question": "Generate a marble head of a young Mediterranean man, 28, dark curls, golden sunlight",
            "expected_tools": ["generate_marble_head"],
            "checks": ["image_generated", "unique_face", "lighting_golden", "no_banned_wording"],
        },
        {
            "question": "Show me Miles with a textured crop in gallery lighting",
            "expected_tools": ["generate_marble_head"],
            "checks": ["image_generated", "character_miles_used", "reference_attached", "no_banned_wording"],
        },
        {
            "question": "Show me Leo with a messy forward fringe in editorial lighting",
            "expected_tools": ["generate_marble_head"],
            "checks": ["image_generated", "character_leo_used", "reference_attached", "no_banned_wording"],
        },
        {
            "question": "Show me Marc with espresso wavy side sweep in authority lighting",
            "expected_tools": ["generate_marble_head"],
            "checks": ["image_generated", "character_marc_used", "reference_attached", "no_banned_wording"],
        },
        {
            "question": "Show me Ray with distinguished silver-grey swept-back hair in gallery lighting",
            "expected_tools": ["generate_marble_head"],
            "checks": ["image_generated", "character_ray_used", "reference_attached", "no_banned_wording"],
        },
        {
            "question": "Generate a marble head of an East Asian man in his late 30s, sharp cheekbones, sleek side-parted black hair",
            "expected_tools": ["generate_marble_head"],
            "checks": ["image_generated", "unique_face", "no_banned_wording"],
        },
        {
            "question": "Generate a marble head of a Nordic man in his 60s, weathered sculpted brow, ash-blonde and grey hair",
            "expected_tools": ["generate_marble_head"],
            "checks": ["image_generated", "unique_face", "no_banned_wording"],
        },
        {
            "question": "Generate a marble head of a South Asian man in his mid-30s, strong jawline, thick wavy dark brown hair, three-quarter pose",
            "expected_tools": ["generate_marble_head"],
            "checks": ["image_generated", "unique_face", "no_banned_wording"],
        },
        {
            "question": "Generate a marble head of a Middle Eastern man in his 40s, aquiline nose, salt-and-pepper curls, editorial lighting",
            "expected_tools": ["generate_marble_head"],
            "checks": ["image_generated", "unique_face", "no_banned_wording"],
        },
        # 8 Editorial collages
        {
            "question": "Impress me — generate editorial collage No.01 with a unique marble bust",
            "expected_tools": ["generate_editorial_collage"],
            "checks": ["image_generated", "krea_reference_board_attached", "series_01", "no_banned_wording"],
        },
        {
            "question": "Create editorial collage No.02 featuring a man in his 40s with medium brown body wave hair",
            "expected_tools": ["generate_editorial_collage"],
            "checks": ["image_generated", "krea_reference_board_attached", "series_02", "no_banned_wording"],
        },
        {
            "question": "Create editorial collage No.03 featuring Miles with tight coils",
            "expected_tools": ["generate_editorial_collage"],
            "checks": ["image_generated", "krea_reference_board_attached", "character_miles_used", "no_banned_wording"],
        },
        {
            "question": "Create editorial collage No.04 featuring a man in his late 50s with silver-grey hair",
            "expected_tools": ["generate_editorial_collage"],
            "checks": ["image_generated", "krea_reference_board_attached", "series_04", "no_banned_wording"],
        },
        {
            "question": "Create editorial collage No.05 featuring Ray in three-quarter profile",
            "expected_tools": ["generate_editorial_collage"],
            "checks": ["image_generated", "krea_reference_board_attached", "character_ray_used", "no_banned_wording"],
        },
        {
            "question": "Create editorial collage No.06 with a young man in his 20s, textured crop",
            "expected_tools": ["generate_editorial_collage"],
            "checks": ["image_generated", "krea_reference_board_attached", "series_06", "no_banned_wording"],
        },
        {
            "question": "Create editorial collage No.07 with Marc and the wordmark-ink logo reference",
            "expected_tools": ["generate_editorial_collage"],
            "checks": ["image_generated", "krea_reference_board_attached", "character_marc_used", "no_banned_wording"],
        },
        {
            "question": "Create editorial collage No.08 featuring a man in his 30s with dark curls",
            "expected_tools": ["generate_editorial_collage"],
            "checks": ["image_generated", "krea_reference_board_attached", "series_08", "no_banned_wording"],
        },
        # 6 Social & Campaign visuals
        {
            "question": "Generate a Black Friday Instagram story visual — dark and premium",
            "expected_tools": ["generate_social_asset"],
            "checks": ["image_generated", "platform_story", "campaign_black_friday", "no_banned_wording"],
        },
        {
            "question": "Generate an Instagram feed square asset for a product launch with a marble head",
            "expected_tools": ["generate_social_asset"],
            "checks": ["image_generated", "platform_feed", "campaign_product_launch", "no_banned_wording"],
        },
        {
            "question": "Generate an Instagram carousel slide (4:5) in editorial style",
            "expected_tools": ["generate_social_asset"],
            "checks": ["image_generated", "platform_carousel", "campaign_editorial", "no_banned_wording"],
        },
        {
            "question": "Generate a Reel cover visual (9:16) with a marble bust of a man in his 30s",
            "expected_tools": ["generate_social_asset"],
            "checks": ["image_generated", "platform_reel", "no_banned_wording"],
        },
        {
            "question": "Generate a campaign visual for our 2026 rebrand launch showing a marble bust on a warm paper gallery backdrop",
            "expected_tools": ["generate_campaign_visual"],
            "checks": ["image_generated", "no_banned_wording"],
        },
        {
            "question": "Generate a Black Friday campaign visual featuring a marble bust under dramatic single key lighting",
            "expected_tools": ["generate_campaign_visual"],
            "checks": ["image_generated", "campaign_black_friday", "no_banned_wording"],
        },
        # 12 Copywriting briefs (testing Gemini 3.5 Flash copywriter + RAG + Atelier Zero rules)
        {
            "question": "Write an email subject line, preheader, and body paragraph introducing the Nano Skin 0.03mm hair system for first-time buyers (Daniel avatar)",
            "expected_tools": ["write_marketing_copy"],
            "checks": ["copy_generated", "sentence_case", "no_exclamation_marks", "no_emoji", "no_banned_wording"],
        },
        {
            "question": "Write an email subject line, preheader, and body comparing Swiss lace vs French lace durability and ventilation for experienced wearers (Marcus avatar)",
            "expected_tools": ["write_marketing_copy"],
            "checks": ["copy_generated", "sentence_case", "explains_tradeoff", "no_exclamation_marks", "no_banned_wording"],
        },
        {
            "question": "Write website hero-split section copy (eyebrow, H1 with one italic phrase, lead paragraph, and primary CTA label) for the Hair Solutions Co. homepage",
            "expected_tools": ["write_marketing_copy"],
            "checks": ["copy_generated", "sentence_case", "has_italic_emphasis", "no_exclamation_marks", "no_banned_wording"],
        },
        {
            "question": "Write an Instagram education caption explaining why front hairline graduation (60% to 40%) matters more than overall density",
            "expected_tools": ["write_marketing_copy"],
            "checks": ["copy_generated", "sentence_case", "useful_hook", "no_exclamation_marks", "no_banned_wording"],
        },
        {
            "question": "Write a 3-step 'how it works' website steps-row section for custom hair system ordering",
            "expected_tools": ["write_marketing_copy"],
            "checks": ["copy_generated", "sentence_case", "no_exclamation_marks", "no_banned_wording"],
        },
        {
            "question": "Write an email reorder reminder for Thin Skin Pro (0.06mm) explaining its 2 to 4 month replacement window",
            "expected_tools": ["write_marketing_copy"],
            "checks": ["copy_generated", "sentence_case", "no_urgency_or_scarcity", "no_exclamation_marks", "no_banned_wording"],
        },
        {
            "question": "Write an Instagram caption for an active professional (Ryan avatar) about swimming and exercising with a hybrid bond",
            "expected_tools": ["write_marketing_copy"],
            "checks": ["copy_generated", "sentence_case", "no_exclamation_marks", "no_banned_wording"],
        },
        {
            "question": "Write a founder note email from Vincent introducing the Atelier Zero rebrand",
            "expected_tools": ["write_marketing_copy"],
            "checks": ["copy_generated", "we_to_you_voice", "sentence_case", "no_exclamation_marks", "no_banned_wording"],
        },
        {
            "question": "Write FAQ section copy answering 'How long does a 0.03mm ultra-thin skin base last compared to French lace?'",
            "expected_tools": ["write_marketing_copy"],
            "checks": ["copy_generated", "explains_tradeoff", "no_exclamation_marks", "no_banned_wording"],
        },
        {
            "question": "Write product detail page copy for Hybrid Flex (lace center with skin perimeter and bleached lace front)",
            "expected_tools": ["write_marketing_copy"],
            "checks": ["copy_generated", "accurate_product_facts", "no_exclamation_marks", "no_banned_wording"],
        },
        {
            "question": "Write a quiet abandoned-cart email that offers help choosing specs without pressure or fake scarcity",
            "expected_tools": ["write_marketing_copy"],
            "checks": ["copy_generated", "relief_not_rescue", "no_exclamation_marks", "no_banned_wording"],
        },
        {
            "question": "Write social carousel copy (5 slides: hook, 3 steps, CTA) on choosing the right density for your age",
            "expected_tools": ["write_marketing_copy"],
            "checks": ["copy_generated", "one_idea_per_slide", "no_exclamation_marks", "no_banned_wording"],
        },
        # 4 Brand spec & RAG lookup cases
        {
            "question": "Look up the Atelier Zero color palette and Coral usage rules",
            "expected_tools": ["get_brand_spec"],
            "checks": ["spec_returned", "coral_ff5757", "no_banned_wording"],
        },
        {
            "question": "Look up the Atelier Zero email layout and surface adjacency rules",
            "expected_tools": ["get_brand_spec"],
            "checks": ["spec_returned", "bone_paper_adjacency_rule", "no_banned_wording"],
        },
        {
            "question": "Look up the Atelier Zero social media governing principles and safe zones",
            "expected_tools": ["get_brand_spec"],
            "checks": ["spec_returned", "one_idea_per_asset", "no_banned_wording"],
        },
        {
            "question": "Retrieve the official storefront facts and email footer address from the marketing-brand knowledge base",
            "expected_tools": ["retrieve_marketing_brand"],
            "checks": ["rag_retrieved", "mentions_ascensio_or_shopify", "no_banned_wording"],
        },
    ]
    assert len(briefs) == 40, f"Expected 40 marketing briefs, got {len(briefs)}"
    return briefs


# ── 3. Vertex AI SFT Dataset for Hair System Expert (200 examples: 160 train / 40 val) ──

HS_SYSTEM_INSTRUCTION = (
    "You are the Hair System Visual Expert for Hair Solutions Co. "
    "Call generate_hair_system_image for every request to see a hair system portrait, "
    "or generate_hair_system_video for motion requests. "
    "Never generate AI before-and-after, transformation, or customer testimonial images. "
    "Never use banned words ('undetectable', '100% natural', 'guaranteed', 'perfect', 'medical grade', "
    "'wig', 'toupee', 'hairpiece') or exclamation marks."
)

HS_TOOL_DECL = [
    {
        "functionDeclarations": [
            {
                "name": "generate_hair_system_image",
                "description": "Generate a photorealistic image of a man wearing a custom hair replacement system.",
                "parameters": {
                    "type": "OBJECT",
                    "properties": {
                        "color_code": {"type": "STRING"},
                        "grey_percentage": {"type": "INTEGER"},
                        "curl_pattern": {"type": "STRING"},
                        "density_percent": {"type": "INTEGER"},
                        "base_type": {"type": "STRING"},
                        "hair_origin": {"type": "STRING"},
                        "hairline_style": {"type": "STRING"},
                        "style_description": {"type": "STRING"},
                        "lighting": {"type": "STRING"},
                        "camera": {"type": "STRING"},
                        "age_range": {"type": "STRING"},
                        "ethnicity": {"type": "STRING"},
                    },
                },
            },
            {
                "name": "generate_hair_system_video",
                "description": "Generate a video clip showing a hair system in motion.",
                "parameters": {
                    "type": "OBJECT",
                    "properties": {
                        "video_type": {"type": "STRING"},
                        "color_code": {"type": "STRING"},
                        "curl_pattern": {"type": "STRING"},
                        "density_percent": {"type": "INTEGER"},
                        "base_type": {"type": "STRING"},
                        "hair_origin": {"type": "STRING"},
                        "style_description": {"type": "STRING"},
                        "age_range": {"type": "STRING"},
                    },
                },
            },
            {
                "name": "calculate_density",
                "description": "Calculate recommended hair system density by age and Norwood level.",
                "parameters": {
                    "type": "OBJECT",
                    "properties": {
                        "age": {"type": "INTEGER"},
                        "norwood_level": {"type": "INTEGER"},
                        "style_preference": {"type": "STRING"},
                    },
                },
            },
            {
                "name": "recommend_base_type",
                "description": "Recommend best base type based on lifestyle, budget, and exposed hairline.",
                "parameters": {
                    "type": "OBJECT",
                    "properties": {
                        "lifestyle": {"type": "STRING"},
                        "budget": {"type": "STRING"},
                        "exposed_hairline": {"type": "BOOLEAN"},
                    },
                },
            },
            {
                "name": "match_hair_color",
                "description": "Match a natural-language hair description to an exact color code.",
                "parameters": {
                    "type": "OBJECT",
                    "properties": {
                        "description": {"type": "STRING"},
                        "grey_percentage": {"type": "INTEGER"},
                    },
                },
            },
        ]
    }
]


def build_hair_system_sft() -> list[dict]:
    examples: list[dict] = []

    colors = [
        ("1", "Jet Black"),
        ("1B", "Off Black"),
        ("2", "Darkest Brown"),
        ("3", "Dark Brown"),
        ("4", "Medium Brown"),
        ("5", "Light Brown"),
        ("6", "Dark Blonde"),
        ("7", "Medium Blonde"),
        ("8", "Light Blonde"),
        ("9", "Very Light Blonde"),
        ("10", "Platinum Blonde"),
    ]
    curls = [
        ("straight", "32mm straight"),
        ("slight_wave", "25mm slight wave"),
        ("body_wave", "20mm body wave"),
        ("medium_wave", "15mm medium wave"),
        ("tight_wave", "10mm tight wave"),
        ("afro_curl", "4-8mm afro curl"),
    ]
    bases = [
        ("ultra_thin_skin", "0.03mm ultra-thin skin"),
        ("thin_skin", "0.06-0.08mm thin skin"),
        ("swiss_lace", "Swiss lace"),
        ("french_lace", "French lace"),
        ("mono", "monofilament"),
        ("hybrid", "hybrid skin-front and lace"),
    ]
    origins = ["indian_remy", "european", "chinese_remy", "brazilian_remy"]
    hairlines = ["exposed", "covered", "side_part", "slicked_back", "messy"]
    lightings = ["studio", "natural", "editorial", "outdoor"]
    cameras = ["portrait", "lifestyle", "closeup", "full_body"]
    ages = ["25-30", "30-35", "35-40", "40-45", "45-50", "50-55"]
    greys = [0, 10, 20, 30, 40, 50]
    styles = [
        "natural textured crop with side part",
        "classic tapered side part",
        "swept-back medium length",
        "short cropped forward fringe",
        "loose natural waves",
        "clean executive contour",
    ]

    # 150 image tool-calling examples
    for i in range(150):
        c_code, c_name = colors[i % len(colors)]
        curl_key, curl_label = curls[(i // 2) % len(curls)]
        base_key, base_label = bases[(i // 3) % len(bases)]
        origin = origins[i % len(origins)]
        hl = hairlines[i % len(hairlines)]
        light = lightings[i % len(lightings)]
        cam = cameras[i % len(cameras)]
        age = ages[i % len(ages)]
        grey = greys[(i // 5) % len(greys)] if i % 3 == 0 else 0
        dens = 80 if age in ("45-50", "50-55") else (90 if age == "40-45" else 95)
        style = styles[i % len(styles)]

        grey_phrase = f" with {grey}% grey at the temples" if grey > 0 else ""
        user_msg = (
            f"Show me a {cam} shot of a man age {age} wearing a #{c_code} ({c_name}){grey_phrase} "
            f"hair system, {curl_label}, {dens}% density on a {base_label} base, "
            f"{hl.replace('_', ' ')} hairline, {style}, {light} lighting."
        )
        fn_args = {
            "age_range": age,
            "base_type": base_key,
            "camera": cam,
            "color_code": c_code,
            "curl_pattern": curl_key,
            "density_percent": dens,
            "grey_percentage": grey,
            "hair_origin": origin,
            "hairline_style": hl,
            "lighting": light,
            "style_description": style,
        }
        img_path = f"/Users/vincent/06_code/agents-studio/src/agents/hair_system_expert/.adk/generated/hair_system_{1700000000 + i}.jpeg"
        fn_resp = {
            "status": "generated",
            "image_path": img_path,
            "model": "gemini-3.1-flash-image (Nano Banana 2)",
        }
        reply = (
            f"Generated a {cam} portrait with #{c_code} ({c_name}){grey_phrase}, "
            f"{curl_label}, {dens}% density on a {base_label} base with a graduated front hairline "
            f"that looks natural when fitted well. Saved to `{img_path}`."
        )
        _assert_clean(reply)

        examples.append({
            "systemInstruction": {"role": "system", "parts": [{"text": HS_SYSTEM_INSTRUCTION}]},
            "tools": HS_TOOL_DECL,
            "contents": [
                {"role": "user", "parts": [{"text": user_msg}]},
                {"role": "model", "parts": [{"functionCall": {"name": "generate_hair_system_image", "args": fn_args}}]},
                {"role": "user", "parts": [{"functionResponse": {"name": "generate_hair_system_image", "response": fn_resp}}]},
                {"role": "model", "parts": [{"text": reply}]},
            ],
        })

    # 20 video tool-calling examples
    for i in range(20):
        c_code, c_name = colors[i % len(colors)]
        curl_key, curl_label = curls[i % len(curls)]
        base_key, base_label = bases[i % len(bases)]
        vtype = "hair_movement" if i % 2 == 0 else "lifestyle"
        age = ages[i % len(ages)]
        dens = 95
        user_msg = f"Create a {vtype.replace('_', ' ')} video of a man age {age} wearing a #{c_code} ({c_name}) {curl_label} hair system on a {base_label} base."
        fn_args = {
            "age_range": age,
            "base_type": base_key,
            "color_code": c_code,
            "curl_pattern": curl_key,
            "density_percent": dens,
            "hair_origin": "indian_remy",
            "style_description": "natural textured crop",
            "video_type": vtype,
        }
        vid_path = f"/Users/vincent/06_code/agents-studio/src/agents/hair_system_expert/.adk/generated/hair_system_{vtype}_{1700001000 + i}.mp4"
        reply = (
            f"Generated a {vtype.replace('_', ' ')} video clip for #{c_code} ({c_name}), "
            f"{curl_label}, {dens}% density on a {base_label} base. Saved to `{vid_path}`."
        )
        _assert_clean(reply)
        examples.append({
            "systemInstruction": {"role": "system", "parts": [{"text": HS_SYSTEM_INSTRUCTION}]},
            "tools": HS_TOOL_DECL,
            "contents": [
                {"role": "user", "parts": [{"text": user_msg}]},
                {"role": "model", "parts": [{"functionCall": {"name": "generate_hair_system_video", "args": fn_args}}]},
                {"role": "user", "parts": [{"functionResponse": {"name": "generate_hair_system_video", "response": {"status": "generated", "video_path": vid_path}}}]},
                {"role": "model", "parts": [{"text": reply}]},
            ],
        })

    # 15 before/after & testimonial refusal examples (Approved Claims rule)
    refusal_prompts = [
        "Generate a before and after transformation for a 45-year-old man, Norwood 5",
        "Show me a side-by-side before and after of a bald guy getting a hair system",
        "Create a transformation reveal video from Norwood 6 to a full head of hair",
        "Make a realistic customer testimonial photo of a client in his bathroom",
        "Generate a before photo showing Norwood 4 recession and an after photo with #3 dark brown",
        "Can you create an AI before-and-after comparison for our Instagram ad?",
        "Show a balding man before and after fitting a Swiss lace system",
        "Generate a split-screen transformation for a 50-year-old man",
        "Create a customer review portrait with a before/after inset",
        "Show me what he looked like bald vs wearing the 0.03mm ultra-thin skin system",
        "Generate an AI transformation reel showing hair loss before and hair system after",
        "Make a before/after pair for a 38-year-old man with #1B20 grey blend",
        "Generate a client before-and-after photo for our product page",
        "Show a Norwood 5 before state next to a 95% density after state",
        "Create a testimonial before-and-after image for a 42-year-old man",
    ]
    for p in refusal_prompts:
        refusal_text = (
            "We never generate AI before-and-after, transformation, or customer testimonial images; "
            "those assets must always come from consented real customer photography in the HSC Library. "
            "I can generate a single portrait of the hair system specification on its own if you would like."
        )
        _assert_clean(refusal_text)
        examples.append({
            "systemInstruction": {"role": "system", "parts": [{"text": HS_SYSTEM_INSTRUCTION}]},
            "tools": HS_TOOL_DECL,
            "contents": [
                {"role": "user", "parts": [{"text": p}]},
                {"role": "model", "parts": [{"text": refusal_text}]},
            ],
        })

    # 15 helper-tool examples (calculate_density, recommend_base_type, match_hair_color)
    for i in range(15):
        age = 28 + i * 2
        nw = 3 + (i % 4)
        pref = ["natural", "light", "full"][i % 3]
        user_msg = f"What density should a {age}-year-old man at Norwood {nw} order for a {pref} look?"
        fn_args = {"age": age, "norwood_level": nw, "style_preference": pref}
        rec_dens = max(70, min(120, 100 - ((age - 30) // 5) * 5))
        fn_resp = {
            "status": "calculated",
            "density_percent": rec_dens,
            "hairline_edge": f"{int(rec_dens * 0.65)}%",
            "crown": f"{rec_dens}%",
        }
        reply = (
            f"For age {age} at Norwood {nw} with a {pref} preference, {rec_dens}% density is appropriate, "
            f"graduating to {int(rec_dens * 0.65)}% along the front 0.5cm hairline with single bleached knots "
            f"so the transition looks natural when fitted well."
        )
        _assert_clean(reply)
        examples.append({
            "systemInstruction": {"role": "system", "parts": [{"text": HS_SYSTEM_INSTRUCTION}]},
            "tools": HS_TOOL_DECL,
            "contents": [
                {"role": "user", "parts": [{"text": user_msg}]},
                {"role": "model", "parts": [{"functionCall": {"name": "calculate_density", "args": fn_args}}]},
                {"role": "user", "parts": [{"functionResponse": {"name": "calculate_density", "response": fn_resp}}]},
                {"role": "model", "parts": [{"text": reply}]},
            ],
        })

    assert len(examples) == 200
    return examples


# ── 4. Vertex AI DPO Dataset for Hair System Expert (110 preference pairs) ──

def build_hair_system_dpo() -> list[dict]:
    pairs: list[dict] = []
    base_topics = [
        (
            "Show me a wig for a bald man",
            "I will generate a portrait showing a custom hair replacement system. Unlike a conventional piece, a hair system uses human hair hand-tied into a 0.03mm transparent polyurethane or fine lace base that bonds to the scalp and looks natural when fitted well.",
            "Here is an undetectable 100% natural wig that is guaranteed to cure your hair loss!",
        ),
        (
            "Make the hair density as thick as possible, like 150%",
            "I will set the density to 110% medium-heavy, which is near the 120% ceiling for a natural-looking full style. Above 120%, the hair mass loses scalp visibility and reads as artificial, so we keep the front 0.5cm graduated at 60-65%.",
            "Here is a 150% density wig with a perfect, guaranteed undetectable hairline!",
        ),
        (
            "Generate a before and after transformation photo",
            "We do not generate AI before-and-after, transformation, or customer testimonial images. Those always use consented real customer photography from the HSC Library. I can generate a single portrait showing the hair system specification instead.",
            "Here is an AI-generated before and after transformation showing an undetectable miracle result!",
        ),
        (
            "Is the adhesive medical grade and hypoallergenic for sensitive skin?",
            "Our systems attach with standard daily tape, extended-wear tape, or liquid adhesive such as Ghost Bond. Because skin sensitivity varies from person to person, we recommend patch-testing any adhesive on a small area before a full bond.",
            "Yes, our adhesive is 100% medical grade, hypoallergenic, dermatologist tested, and guaranteed safe for sensitive skin!",
        ),
        (
            "How does your system compare to LordHair and OneHead?",
            "We focus on our own specifications and transparent material tradeoffs: 0.03mm ultra-thin skin for the lowest-profile front edge (4 to 6 weeks wear) and French or Swiss lace for breathability in warm climates or active routines.",
            "We are much better than LordHair and OneHead and guaranteed to be 100% undetectable!",
        ),
    ]

    for i in range(110):
        base_q, base_pref, base_rej = base_topics[i % len(base_topics)]
        age = 25 + (i % 35)
        code = ["1", "1B", "2", "3", "4", "5", "6", "7"][i % 8]
        q = f"{base_q} (Client age {age}, shade #{code})" if i >= len(base_topics) else base_q
        pref = f"{base_pref} Configured for age {age} in shade #{code}." if i >= len(base_topics) else base_pref
        rej = base_rej
        _assert_clean(pref)
        pairs.append({
            "contents": [{"role": "user", "parts": [{"text": q}]}],
            "candidates": [
                {
                    "content": {"role": "model", "parts": [{"text": pref}]},
                    "preferenceScore": 1.0,
                },
                {
                    "content": {"role": "model", "parts": [{"text": rej}]},
                    "preferenceScore": 0.0,
                },
            ],
        })
    return pairs


# ── 5. Copywriter SFT (225 examples: 180 train / 45 val) & DPO (110 pairs) ──

COPY_SYSTEM_INSTRUCTION = (
    "You are the Hair Solutions Co. Copywriter (Atelier Zero design system, ascensio-digital-solutions/brand-design-system). "
    "Speak as 'we' to 'you' with calm, direct, educational restraint. Relief, not rescue. "
    "Use sentence case. Use Playfair Display italic (*italic*) only for a single inline emphasis phrase inside a heading or pull-quote. "
    "Display headlines end with a period. "
    "Never use exclamation marks (!), emojis, urgency, scarcity, pity, or banned wording "
    "('undetectable', '100% natural', 'guaranteed', 'perfect', 'medical grade', 'hypoallergenic', "
    "'dermatologist tested', 'clinically tested', 'safe for sensitive skin', 'non-irritating', "
    "'wig', 'toupee', 'hairpiece', 'OneHead', 'LordHair')."
)


def build_copywriter_sft() -> list[dict]:
    examples: list[dict] = []

    products = [
        ("Nano Skin", "0.03mm transparent polyurethane membrane", "V-looped knotless hair", "4 to 6 weeks", "light-to-medium 90%", "prioritizes a flat, low-profile front edge over lifespan"),
        ("Thin Skin Pro", "0.06mm to 0.08mm polyurethane base", "V-looped front with single split knots", "2 to 4 months", "medium 95-100%", "balances a clean front edge with multi-month durability"),
        ("Lace Elite", "fine Swiss or French lace mesh", "bleached single knots at the hairline", "6 to 10 weeks", "medium-light 90%", "maximizes airflow and breathability in warm climates or active routines"),
        ("Hybrid Flex", "lace center with a thin skin perimeter and bleached lace front", "graduated front knots with reinforced perimeter", "2 to 3 months", "medium 100%", "combines lace ventilation at the crown with straightforward tape cleanup on the perimeter"),
    ]
    avatars = [
        ("Daniel (first-timer)", "research-heavy and cautious; explain the routine and material tradeoff plainly before commerce"),
        ("Marcus (experienced wearer)", "spec-literate; talk shop using exact base thickness, knot construction, and replacement cycle"),
        ("Ryan (active professional)", "pragmatic and routine-focused; explain how the base and bond handle exercise, sweat, travel, and water"),
    ]
    channels = ["email", "web_section", "social_caption"]

    for i in range(225):
        prod_name, base_desc, knot_desc, lifespan, dens, tradeoff = products[i % len(products)]
        av_name, av_desc = avatars[(i // 4) % len(avatars)]
        channel = channels[i % len(channels)]
        shade = ["#1B Off Black", "#2 Darkest Brown", "#3 Dark Brown", "#4 Medium Brown", "#1B20 (20% grey blend)"][i % 5]

        if channel == "email":
            brief = (
                f"Write an Atelier Zero marketing email (subject line, preheader, opener, body, and single CTA label) "
                f"for {prod_name} ({base_desc}, {lifespan} wear) tailored to {av_name}, highlighting shade {shade}."
            )
            copy_text = (
                f"Subject: How {prod_name} balances realism and routine\n"
                f"Preheader: Built on a {base_desc} with {knot_desc}.\n\n"
                f"EYEBROW: MATERIAL SPECIFICATION\n"
                f"Headline: Built for a *quiet, accurate* front edge.\n\n"
                f"Body:\n"
                f"We designed {prod_name} around a {base_desc} with {knot_desc} at {dens} density, available in shades including {shade}. "
                f"Because this construction {tradeoff}, each system has a practical wear window of {lifespan} before replacement.\n\n"
                f"If you are comparing bases for your routine, reply with your current spec or book a quiet 15-minute consultation and we will walk through the options with you.\n\n"
                f"Primary CTA (Coral #FF5757 pill, Ink #15140F text): Review the {prod_name} spec\n"
                f"Footer: Ascensio Digital Solutions, Rua Duvivier 43, Rio de Janeiro, Brazil."
            )
        elif channel == "web_section":
            pattern = ["hero-split", "feature-split", "steps-row", "pull-quote", "cta-band", "faq"][i % 6]
            brief = (
                f"Write Atelier Zero website copy for a `{pattern}` section featuring {prod_name} "
                f"({base_desc}) for {av_name} ({av_desc})."
            )
            copy_text = (
                f"PATTERN: {pattern}\n"
                f"EYEBROW: {prod_name.upper()} SPECIFICATION\n"
                f"H2: Material clarity, *without the guesswork*.\n\n"
                f"Lead: {prod_name} uses a {base_desc} with {knot_desc} and {dens} density, graduated to 60–65% along the leading 0.5cm so the front hairline looks natural when fitted well.\n\n"
                f"Tradeoff note: This base {tradeoff}, giving a realistic {lifespan} wear cycle under normal care.\n\n"
                f"Primary CTA: Configure your {prod_name} system"
            )
        else:
            pillar = ["Education", "Product", "Brand & Founder", "Lifestyle"][i % 4]
            brief = (
                f"Write an Instagram {pillar} post (on-frame headline + supporting line + caption) "
                f"about {prod_name} ({base_desc}) for {av_name}."
            )
            copy_text = (
                f"Format: Feed portrait 1080×1350 (Paper #EFE7D2 surface, Ink #15140F type)\n"
                f"On-frame headline: What {base_desc.split()[0]} actually changes at the hairline.\n"
                f"On-frame supporting line: {prod_name} pairs {knot_desc} with a {lifespan} replacement rhythm.\n\n"
                f"Caption:\n"
                f"Most hair system decisions come down to a single tradeoff between membrane thickness and lifespan. "
                f"{prod_name} uses a {base_desc} with {knot_desc} at {dens} density. It {tradeoff}, so you know upfront how it fits your calendar and maintenance routine.\n\n"
                f"DM the word SPEC and we will send over the base comparison guide."
            )

        _assert_clean(copy_text)
        examples.append({
            "systemInstruction": {"role": "system", "parts": [{"text": COPY_SYSTEM_INSTRUCTION}]},
            "contents": [
                {"role": "user", "parts": [{"text": brief}]},
                {"role": "model", "parts": [{"text": copy_text}]},
            ],
        })

    assert len(examples) == 225
    return examples


def build_copywriter_dpo() -> list[dict]:
    sft_rows = build_copywriter_sft()
    pairs: list[dict] = []
    for i in range(110):
        row = sft_rows[i]
        brief = row["contents"][0]["parts"][0]["text"]
        preferred = row["contents"][1]["parts"][0]["text"]
        rejected = (
            "🔥 LAST CHANCE! Get our 100% NATURAL, UNDETECTABLE wig today! "
            "Guaranteed to transform your life with medical-grade hypoallergenic comfort — "
            "way better than LordHair! Click NOW before stock runs out! 🚀"
        )
        _assert_clean(preferred)
        pairs.append({
            "systemInstruction": {"role": "system", "parts": [{"text": COPY_SYSTEM_INSTRUCTION}]},
            "contents": [{"role": "user", "parts": [{"text": brief}]}],
            "candidates": [
                {
                    "content": {"role": "model", "parts": [{"text": preferred}]},
                    "preferenceScore": 1.0,
                },
                {
                    "content": {"role": "model", "parts": [{"text": rejected}]},
                    "preferenceScore": 0.0,
                },
            ],
        })
    return pairs


def _write_jsonl(path: Path, rows: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        for r in rows:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")
    print(f"Wrote {len(rows):3d} rows -> {path.relative_to(ROOT)}")


def main() -> None:
    random.seed(42)

    # 1. Evals
    hs_evals = build_hair_system_evals()
    _write_jsonl(HS_DIR / "evaluation" / "test_questions.jsonl", hs_evals)

    mk_evals = build_marketing_evals()
    _write_jsonl(MK_DIR / "evaluation" / "test_questions.jsonl", mk_evals)

    # 2. Hair System Expert SFT & DPO
    hs_sft = build_hair_system_sft()
    random.shuffle(hs_sft)
    hs_train, hs_val = hs_sft[:160], hs_sft[160:]
    _write_jsonl(HS_DIR / "tuning" / "sft_train_v01.jsonl", hs_train)
    _write_jsonl(HS_DIR / "tuning" / "sft_val_v01.jsonl", hs_val)
    _write_jsonl(HS_DIR / "tuning" / "sft_dataset.jsonl", hs_train)

    hs_dpo = build_hair_system_dpo()
    _write_jsonl(HS_DIR / "tuning" / "dpo_train_v01.jsonl", hs_dpo)
    _write_jsonl(HS_DIR / "tuning" / "preference_pairs.jsonl", hs_dpo)

    # 3. Marketing Copywriter SFT & DPO
    copy_sft = build_copywriter_sft()
    random.shuffle(copy_sft)
    copy_train, copy_val = copy_sft[:180], copy_sft[180:]
    _write_jsonl(MK_DIR / "tuning" / "copy_sft_train_v01.jsonl", copy_train)
    _write_jsonl(MK_DIR / "tuning" / "copy_sft_val_v01.jsonl", copy_val)

    copy_dpo = build_copywriter_dpo()
    _write_jsonl(MK_DIR / "tuning" / "copy_dpo_train_v01.jsonl", copy_dpo)


if __name__ == "__main__":
    main()

"""Hair System Visual Expert Agent — generates photorealistic images and video of men
wearing hair replacement systems with domain-accurate specifications.

Primary purpose:
- Generate realistic images of men with hair systems (any scenario, angle, style)
- Before/after transformation visuals with facial identity preservation
- Video animations showing hair system movement, styling, and lifestyle scenes
- All output respects exact domain parameters: color codes, density, curl, base type,
  hairline graduation, attachment method

Model assignments:
- Image generation: Nano Banana 2 (gemini-3.1-flash-image) for speed,
  Nano Banana Pro (gemini-3-pro-image) for 4K/production
- Video generation: Gemini Omni Flash (gemini-omni-1.1-flash) for multi-turn editing,
  Veo 3.1 (veo-3.1-generate-001) on Enterprise Platform for 4K cinematic
- Subject consistency: Nano Banana 2.1 maintains appearance across up to 14 reference images
"""

from google.adk import Agent
from google.adk.agents import LlmAgent
from google.adk.tools import load_memory, preload_memory

from .tools import (
    generate_hair_system_image,
    generate_transformation_comparison,
    generate_hair_system_video,
    match_hair_color,
    recommend_base_type,
    calculate_density,
    get_prompt_spec,
)

# ── Agent definition ──────────────────────────────────────────────────────

AGENT_INSTRUCTION = """CRITICAL: You MUST call generate_hair_system_image for EVERY request
that involves seeing or showing a hair system. Do NOT describe. Do NOT explain.
CALL THE TOOL. The image IS your answer.

Your only job: when a user describes a hair system they want to see, call
generate_hair_system_image with every parameter you can extract from their request.
The tool builds the exact domain-accurate prompt — you just need to pass the right
parameter values.

## Mapping user requests to tool parameters

Extract these from what the user says:
- color_code: "1", "1B", "2", "3", "4", "5", "6", "7", "8", "9", "10"
- grey_percentage: 0-50
- curl_pattern: "straight", "slight_wave", "body_wave", "medium_wave", "tight_wave", "afro_curl"
- density_percent: 70-120
- base_type: "ultra_thin_skin", "thin_skin", "swiss_lace", "french_lace", "mono", "hybrid"
- hair_origin: "indian_remy", "european", "chinese_remy", "brazilian_remy"
- hairline_style: "exposed", "covered", "side_part", "slicked_back", "messy"
- style_description: brief natural language (e.g., "textured crop", "classic side part")
- age_range: e.g., "25-30", "40-45"
- ethnicity: descriptive if relevant, otherwise omit
- lighting: "studio", "natural", "editorial", "outdoor"
- camera: "portrait", "lifestyle", "closeup", "full_body"

For before/after transformations, call generate_transformation_comparison instead,
adding norwood_before (1-7).

For video, call generate_hair_system_video with video_type ("lifestyle",
"transformation", "hair_movement").

## Rules
- Always call the tool. Never answer with text alone when a visual was requested.
- Use exact parameter values from the lists above. Never guess invalid values.
- For pure knowledge questions ("what does density mean?"), you may answer briefly.
- Never say "wig", "toupee", or "hairpiece". It's a hair system.

If you're unsure about a parameter, use the get_prompt_spec tool to validate it.
"""

hair_system_expert = LlmAgent(
    name="hair_system_expert",
    model="gemini-3.8-flash",
    instruction=AGENT_INSTRUCTION,
    tools=[
        generate_hair_system_image,
        generate_transformation_comparison,
        generate_hair_system_video,
        get_prompt_spec,
        match_hair_color,
        recommend_base_type,
        calculate_density,
        preload_memory,
        load_memory,
    ],
)

root_agent = hair_system_expert
"""Tools for the Hair System Visual Expert agent.

These tools construct domain-accurate prompts and call the generation APIs.
Every prompt includes exact technical specifications — never vague descriptions.
"""

import json
from typing import Optional, Literal
from dataclasses import dataclass, asdict

from google.adk import Context
from google import genai
from google.genai import types as genai_types

from ..shared.references import lookup_manifest_references, select_hair_system_references


# ── Domain data tables ────────────────────────────────────────────────────

COLORS = {
    "1":  "Jet Black",
    "1B": "Off Black / Natural Black",
    "2":  "Darkest Brown",
    "3":  "Dark Brown",
    "4":  "Medium Brown",
    "5":  "Light Brown",
    "6":  "Dark Blonde",
    "7":  "Medium Blonde",
    "8":  "Light Blonde",
    "9":  "Very Light Blonde",
    "10": "Platinum Blonde",
}

CURL_PATTERNS = {
    "straight":     {"rod": "32mm", "desc": "naturally straight, no visible wave, sleek"},
    "slight_wave":  {"rod": "25mm", "desc": "subtle natural movement, slight body, not curly"},
    "body_wave":    {"rod": "20mm", "desc": "visible wave pattern, bounce and volume, textured but not curly"},
    "medium_wave":  {"rod": "15mm", "desc": "defined S-curve waves, fuller appearance"},
    "tight_wave":   {"rod": "10mm", "desc": "tight defined curls, significant texture and volume"},
    "afro_curl":    {"rod": "4-8mm", "desc": "tight coils, Afro-textured, maximum texture"},
}

BASE_TYPES = {
    "ultra_thin_skin": "0.03mm ultra-thin transparent polyurethane skin base, near-invisible edge, "
                       "scalp-like translucency, natural pore reflection visible through base, "
                       "finest, least visible skin edge",
    "thin_skin":       "0.06-0.08mm thin polyurethane skin base, barely visible edge, "
                       "good scalp realism, durable",
    "swiss_lace":      "fine delicate Swiss lace mesh base, finest and least visible lace, "
                       "disappears against scalp, maximum ventilation",
    "french_lace":     "durable French lace mesh base, slightly more visible texture than Swiss, "
                       "good ventilation, balanced durability",
    "mono":            "monofilament mesh base, visible perimeter texture, maximum durability, "
                       "used for active clients",
    "hybrid":          "ultra-thin skin at front 2cm hairline for a soft, natural-looking edge + "
                       "lace mesh body for breathability, seamless material transition",
}

HAIR_ORIGINS = {
    "indian_remy":    "Indian Remy human hair, medium texture, slight natural body, "
                      "dark brown natural color, most natural match for Caucasian/Hispanic clients",
    "european":       "European human hair, finest texture, light brown to dark blonde natural, "
                      "lightest density feel, premium realism for fine-haired clients",
    "chinese_remy":   "Chinese Remy human hair, thick strand, naturally very straight, "
                      "jet black to dark brown natural, resists curling, most durable",
    "brazilian_remy": "Brazilian Remy human hair, medium-coarse texture, natural body wave, "
                      "holds curl well, maximum volume and movement",
}

DENSITY_LABELS = {
    70:  "Light (mature hairline, 45+ years)",
    75:  "Light (mature hairline, 45+ years)",
    80:  "Light-Medium (natural recession look, 40-50)",
    85:  "Medium-Light (age-appropriate, 35-45)",
    90:  "Medium-Light (age-appropriate, 35-45)",
    95:  "Medium (standard, most clients 25-40)",
    100: "Medium (standard, most clients 25-40)",
    105: "Medium-Heavy (full look, 25-35)",
    110: "Medium-Heavy (full look, 20-30)",
    115: "Heavy (youthful fullness, under 25)",
    120: "Heavy (maximum, under 25)",
}

ATTACHMENT_METHODS = {
    "tape_daily":    "Walker No-Shine tape applied to perimeter, remove nightly, "
                     "clean adhesive-free base edge visible upon close inspection",
    "tape_extended": "Walker Ultra Hold tape full perimeter, 1-2 week hold, "
                     "secure bond with minimal visible edge",
    "liquid_bond":   "Ghost Bond Platinum adhesive applied directly to scalp, "
                     "2-4 week hold, no bond edge visible in frame, "
                     "best for exposed hairlines",
    "hybrid_bond":   "tape at sides and back perimeter, Ghost Bond adhesive at front 1cm hairline, "
                     "secure hold with the softest-looking front hairline",
}

LIGHTING_STYLES = {
    "studio":        "professional studio lighting, soft key light from 45 degrees, "
                     "subtle fill from opposite side, hair light from above-rear for depth separation",
    "natural":       "golden hour natural sunlight, warm directional light, "
                     "natural catchlights in eyes, soft shadows",
    "editorial":     "dramatic single source lighting, strong contrast, "
                     "magazine-quality, deep shadows with detail retention",
    "outdoor":       "overcast natural diffused light, even illumination, "
                     "no harsh shadows, realistic everyday appearance",
}

CAMERA_SPECS = {
    "portrait":      "85mm f/1.4 portrait lens, shallow depth of field, "
                     "bokeh background, subject sharp from front hairline to ears",
    "lifestyle":     "35mm f/2.0 environmental portrait, context visible, "
                     "natural perspective, subject in real environment",
    "closeup":       "100mm f/2.8 macro detail, hairline and scalp pore detail visible, "
                     "shows natural hairline and knot detail",
    "full_body":     "50mm f/2.8 full body, subject from head to waist, "
                     "shows how hair system integrates with full appearance",
}


# ── Prompt builder ────────────────────────────────────────────────────────

@dataclass
class HairSystemSpec:
    """Complete specification for a hair system image/video prompt."""
    color_code: str = "1B"
    grey_percentage: int = 0
    curl_pattern: str = "slight_wave"
    density_percent: int = 95
    base_type: str = "ultra_thin_skin"
    hair_origin: str = "indian_remy"
    attachment: str = "liquid_bond"
    hairline_style: str = "exposed"  # exposed, covered, side_part, slicked_back, messy
    style_description: str = "natural textured crop with side part"
    lighting: str = "studio"
    camera: str = "portrait"
    age_range: str = "30-40"
    ethnicity: str = ""  # descriptive, not prescriptive
    face_shape: str = ""
    environment: str = "clean studio backdrop, neutral grey"
    mood: str = "confident, natural, professional"
    # Reference image for subject consistency
    reference_image_uri: Optional[str] = None


def build_image_prompt(spec: HairSystemSpec, image_type: str = "portrait") -> str:
    """Build a domain-accurate image generation prompt from a HairSystemSpec.

    Every prompt follows this structure:
    1. Subject and framing
    2. Hair system specifications (exact, not vague)
    3. Hairline and attachment realism
    4. Lighting and camera
    5. Quality and realism directives
    6. What NOT to show (negative constraints)
    """
    color_name = COLORS.get(spec.color_code, spec.color_code)
    curl = CURL_PATTERNS.get(spec.curl_pattern, {})
    base = BASE_TYPES.get(spec.base_type, "")
    origin = HAIR_ORIGINS.get(spec.hair_origin, "")
    density_label = DENSITY_LABELS.get(
        round(spec.density_percent / 5) * 5, f"{spec.density_percent}%"
    )
    attachment = ATTACHMENT_METHODS.get(spec.attachment, "")
    lighting = LIGHTING_STYLES.get(spec.lighting, "")
    camera = CAMERA_SPECS.get(spec.camera, "")

    grey_str = ""
    if spec.grey_percentage > 0:
        grey_str = (
            f"with {spec.grey_percentage}% natural grey blended throughout, "
            f"slightly heavier grey concentration at the temples, "
            f"natural salt-and-pepper distribution, not uniform grey"
        )

    ethnicity_str = f"{spec.ethnicity} man" if spec.ethnicity else "man"
    face_str = f"with {spec.face_shape} face shape" if spec.face_shape else ""
    age_str = f"age {spec.age_range}" if spec.age_range else ""

    # ── Standard portrait prompt ──────────────────────────────────────────

    prompt = f"""A photorealistic portrait of a {ethnicity_str} {age_str} {face_str},
wearing a men's hair replacement system that looks like naturally growing hair, photographed with {camera}.

HAIR SYSTEM SPECIFICATIONS:
- Color: {color_name} (code #{spec.color_code}) {grey_str}
- Curl: {spec.curl_pattern} ({curl.get('rod', '')}) — {curl.get('desc', '')}
- Density: {spec.density_percent}% ({density_label})
- Hair: {origin}
- Base: {base}
- Attachment: {attachment}

HAIRLINE (CRITICAL REALISM):
- The front hairline edge reads as natural growth — 60-65% graduated density at the leading 0.5cm, decreasing naturally to the edge
- Single bleached knots throughout the hairline — no dark dots or visible knot patterns
- Fine wispy baby hairs placed irregularly along the hairline for natural transition
- Natural scalp appearance with visible pore texture showing through the transparent base
- ZERO visible base edge, ZERO lace grid pattern, ZERO blunt cutoff line

STYLE:
- {spec.style_description}
- Hairline is {spec.hairline_style}
- Natural hair movement and texture, not stiff or helmet-like
- Hair flows naturally with gravity, individual strands visible

LIGHTING:
- {lighting}
- Subtle specular highlights on hair showing natural shine (not plastic)
- Catchlights in eyes

TECHNICAL QUALITY:
- Photorealistic, not illustrated or CGI
- 8K resolution equivalent detail
- Genuine human skin texture with pores
- No airbrushing, no plastic skin, no AI gloss, no synthetic sheen
- The hair system must look indistinguishable from biological growing hair

NEGATIVE CONSTRAINTS:
- NO visible base edge or seam
- NO lace grid or mesh pattern visible
- NO dark knots at the hairline
- NO blunt haircut line or helmet appearance
- NO plastic doll-like skin
- NO synthetic or unnatural hair shine
- NO wig-like density or texture"""

    return prompt


def build_video_prompt(spec: HairSystemSpec, video_type: str = "lifestyle") -> str:
    """Build a video generation prompt."""
    color_name = COLORS.get(spec.color_code, spec.color_code)
    curl = CURL_PATTERNS.get(spec.curl_pattern, {})

    if video_type == "hair_movement":
        return (
            f"Short cinematic video clip of a man wearing a natural-looking hair system. "
            f"Color {color_name}, {spec.curl_pattern} {curl.get('rod', '')}, "
            f"{spec.density_percent}% density. The camera circles slowly around his head "
            f"while he turns naturally. His hair moves with natural physics — wind moves "
            f"through it, individual strands shift. No base edge is visible at the hairline. "
            f"Natural outdoor lighting, photorealistic, 4K cinematic quality. "
            f"No visible base, no wig-like stiffness, authentic human hair movement."
        )

    # Default: lifestyle
    return (
        f"Cinematic video clip of a confident man age {spec.age_range} wearing an "
        f"natural-looking hair replacement system. Color {color_name}, "
        f"{spec.curl_pattern} {curl.get('rod', '')} texture, "
        f"{spec.density_percent}% density. {spec.style_description}. "
        f"He is {spec.environment}. Natural movement, relaxed confidence. "
        f"The hair system reads as natural growth — soft hairline with "
        f"graduated density, baby hairs visible at close range. "
        f"Photorealistic, 4K, cinematic lighting. Hair moves naturally with physics. "
        f"No visible base edge, no synthetic appearance."
    )


# ── Generation tools ──────────────────────────────────────────────────────

def generate_hair_system_image(
    color_code: str = "1B",
    grey_percentage: int = 0,
    curl_pattern: str = "slight_wave",
    density_percent: int = 95,
    base_type: str = "ultra_thin_skin",
    hair_origin: str = "indian_remy",
    hairline_style: str = "exposed",
    style_description: str = "natural textured crop with side part",
    lighting: str = "studio",
    camera: str = "portrait",
    age_range: str = "30-35",
    ethnicity: str = "",
    face_shape: str = "",
    environment: str = "clean studio backdrop, neutral grey",
    mood: str = "confident, natural, professional",
    reference_image_uri: Optional[str] = None,
    tool_context: Optional[Context] = None,
) -> dict:
    """Generate a photorealistic image of a man wearing a custom hair replacement system.

    This is the primary tool. Use it whenever the user wants to see what a hair system
    looks like. Every parameter is specified exactly — never approximate.

    Args:
        color_code: Hair color code. One of: 1, 1B, 2, 3, 4, 5, 6, 7, 8, 9, 10.
        grey_percentage: Grey blend percentage (0, 10, 20, 30, 40, 50).
        curl_pattern: Curl type. One of: straight, slight_wave, body_wave, medium_wave,
                      tight_wave, afro_curl.
        density_percent: Density 70-120. 95 is standard for ages 25-40.
        base_type: Base material. One of: ultra_thin_skin, thin_skin, swiss_lace,
                   french_lace, mono, hybrid.
        hair_origin: Hair source. One of: indian_remy, european, chinese_remy, brazilian_remy.
        hairline_style: How the hairline is styled. One of: exposed, covered, side_part,
                        slicked_back, messy, textured_forward.
        style_description: Natural language description of the hairstyle.
        lighting: Lighting setup. One of: studio, natural, editorial, outdoor.
        camera: Camera/lens. One of: portrait, lifestyle, closeup, full_body.
        age_range: Subject age range like "25-30", "35-40", "45-50".
        ethnicity: Descriptive (e.g., "Caucasian", "Hispanic", "South Asian"). Not prescriptive.
        face_shape: Optional face shape description.
        environment: Background/setting description.
        mood: Emotional tone of the image.
        reference_image_uri: Optional URI of a reference photo for subject consistency.
                             If provided, the generated subject will match this person's face.

    Returns:
        Dict with the generated image data or status.
    """
    spec = HairSystemSpec(
        color_code=color_code,
        grey_percentage=grey_percentage,
        curl_pattern=curl_pattern,
        density_percent=density_percent,
        base_type=base_type,
        hair_origin=hair_origin,
        hairline_style=hairline_style,
        style_description=style_description,
        lighting=lighting,
        camera=camera,
        age_range=age_range,
        ethnicity=ethnicity,
        face_shape=face_shape,
        environment=environment,
        mood=mood,
        reference_image_uri=reference_image_uri,
    )

    prompt = build_image_prompt(spec)
    color_name = COLORS.get(color_code, color_code)

    # ── Load matching R2 swatch/product references by manifest tag ────────
    ref_parts, ref_meta = select_hair_system_references(
        color_code=color_code,
        curl_pattern=curl_pattern,
        density_percent=density_percent,
        base_type=base_type,
        grey_percentage=grey_percentage,
        hairline_style=hairline_style,
        max_refs=3,
    )

    # ── Call Nano Banana 2 via Vertex AI / Gemini API ─────────────────────
    try:
        client = genai.Client()
        contents: list[genai_types.Part] = list(ref_parts)

        # If reference image URI explicitly provided, include it for subject consistency
        if reference_image_uri:
            contents.insert(0, genai_types.Part.from_uri(
                file_uri=reference_image_uri,
                mime_type="image/jpeg",
            ))

        if contents:
            prompt_with_ref_note = (
                "Use the attached Hair Solutions Co. swatch and hairline reference images "
                "to match hair color tone, curl texture, base translucency, and hairline realism.\n\n"
                + prompt
            )
            contents.append(genai_types.Part.from_text(text=prompt_with_ref_note))
        else:
            contents.append(genai_types.Part.from_text(text=prompt))

        response = client.models.generate_content(
            model="gemini-3.1-flash-image",
            contents=genai_types.Content(
                role="user",
                parts=contents,
            ),
            config=genai_types.GenerateContentConfig(
                response_modalities=["IMAGE", "TEXT"],
            ),
        )

        # Extract generated image — save to disk, return reference only
        # (Returning base64 data blows the planning model's token limit)
        image_path = None
        for part in response.candidates[0].content.parts:
            if part.inline_data and part.inline_data.mime_type.startswith("image/"):
                import os, time
                ext = part.inline_data.mime_type.split("/")[-1]
                out_dir = os.path.join(os.path.dirname(__file__), ".adk", "generated")
                os.makedirs(out_dir, exist_ok=True)
                image_path = os.path.join(out_dir, f"hair_system_{int(time.time())}.{ext}")
                with open(image_path, "wb") as f:
                    f.write(part.inline_data.data)
                break

        return {
            "status": "generated",
            "image_path": image_path,
            "spec": asdict(spec),
            "reference_assets": ref_meta,
            "model": "gemini-3.1-flash-image (Nano Banana 2)",
            "message": f"Image generated successfully using {color_name} ({color_code}), "
                       f"{curl_pattern}, {density_percent}% density, {base_type} base "
                       f"with {len(ref_meta)} R2 reference swatch(es). "
                       f"Saved to {image_path}",
        }

    except Exception as e:
        return {
            "status": "error",
            "error": str(e),
            "prompt": prompt,
            "spec": asdict(spec),
            "message": (
                "Image generation failed. This may be because the Gemini API key is not "
                "configured or the Nano Banana model is not available in this region. "
                "Ensure GEMINI_API_KEY is set and try again."
            ),
        }


def generate_hair_system_video(
    video_type: str = "lifestyle",
    color_code: str = "1B",
    curl_pattern: str = "slight_wave",
    density_percent: int = 95,
    base_type: str = "ultra_thin_skin",
    hair_origin: str = "indian_remy",
    style_description: str = "natural textured crop with side part",
    age_range: str = "30-35",
    duration_seconds: int = 8,
    reference_image_uri: Optional[str] = None,
    tool_context: Optional[Context] = None,
) -> dict:
    """Generate a video clip showing a hair system in motion.

    Uses Gemini Omni Flash as the default video model (Veo 3.1 on Enterprise Platform
    for 4K cinematic output).

    Args:
        video_type: Type of video. One of: lifestyle, hair_movement.
        color_code: Hair color code.
        curl_pattern: Curl pattern.
        density_percent: Hair density.
        base_type: Base material type.
        hair_origin: Hair origin type.
        style_description: Hairstyle description.
        age_range: Subject age range.
        duration_seconds: Video duration in seconds (max 8 for Gemini Omni Flash).
        reference_image_uri: Optional reference image for subject consistency.

    Returns:
        Dict with video generation result.
    """
    spec = HairSystemSpec(
        color_code=color_code,
        curl_pattern=curl_pattern,
        density_percent=density_percent,
        base_type=base_type,
        hair_origin=hair_origin,
        style_description=style_description,
        age_range=age_range,
        reference_image_uri=reference_image_uri,
    )

    if video_type not in ("lifestyle", "hair_movement"):
        return {
            "status": "refused",
            "message": (
                "Only 'lifestyle' and 'hair_movement' videos are available. Before-and-after "
                "or transformation media is never AI-generated (Approved Claims); use consented "
                "real customer media from the HSC Library instead."
            ),
        }

    prompt = build_video_prompt(spec, video_type)

    try:
        import os, time
        out_dir = os.path.join(os.path.dirname(__file__), ".adk", "generated")
        os.makedirs(out_dir, exist_ok=True)
        client = genai.Client()
        contents = [genai_types.Part.from_text(text=prompt)]

        if reference_image_uri:
            contents.insert(0, genai_types.Part.from_uri(
                file_uri=reference_image_uri,
                mime_type="image/jpeg",
            ))

        # Gemini Omni Flash — primary video generation model as of Nov 2026
        response = client.models.generate_content(
            model="gemini-omni-1.1-flash",
            contents=genai_types.Content(role="user", parts=contents),
            config=genai_types.GenerateContentConfig(
                response_modalities=["VIDEO", "TEXT"],
            ),
        )

        video_path = None
        for part in response.candidates[0].content.parts:
            if part.inline_data and part.inline_data.mime_type.startswith("video/"):
                ext = part.inline_data.mime_type.split("/")[-1]
                video_path = os.path.join(out_dir, f"hair_system_{video_type}_{int(time.time())}.{ext}")
                with open(video_path, "wb") as f:
                    f.write(part.inline_data.data)
                break

        return {
            "status": "generated",
            "video_path": video_path,
            "video_type": video_type,
            "spec": asdict(spec),
            "model": "gemini-omni-1.1-flash (Gemini Omni Flash)",
            "message": f"Video generated successfully: {video_type}. Saved to {video_path}",
        }

    except Exception as e:
        return {
            "status": "error",
            "error": str(e),
            "prompt": prompt,
            "message": (
                "Video generation failed. If using Gemini Omni Flash, ensure the model "
                "is available in your region. For 4K cinematic output, use Veo 3.1 on "
                "the Gemini Enterprise Agent Platform instead."
            ),
        }


# ── Supporting tools ──────────────────────────────────────────────────────

def get_prompt_spec(
    color_code: Optional[str] = None,
    curl_pattern: Optional[str] = None,
    density_percent: Optional[int] = None,
    base_type: Optional[str] = None,
    hair_origin: Optional[str] = None,
    tool_context: Optional[Context] = None,
) -> dict:
    """Get the canonical prompt specification for hair system generation parameters.
    Use this to validate parameters before generating an image or video.

    Args:
        color_code: Color code to look up.
        curl_pattern: Curl pattern to look up.
        density_percent: Density to validate and label.
        base_type: Base type to look up.
        hair_origin: Hair origin to look up.

    Returns:
        Dict with full specifications for each parameter.
    """
    result = {}

    if color_code and color_code in COLORS:
        result["color"] = {"code": color_code, "name": COLORS[color_code]}
    elif color_code:
        result["color"] = {"error": f"Unknown color code '{color_code}'. Valid: {list(COLORS.keys())}"}

    if curl_pattern and curl_pattern in CURL_PATTERNS:
        result["curl"] = {"pattern": curl_pattern, **CURL_PATTERNS[curl_pattern]}
    elif curl_pattern:
        result["curl"] = {"error": f"Unknown curl pattern '{curl_pattern}'. Valid: {list(CURL_PATTERNS.keys())}"}

    if density_percent is not None:
        label = DENSITY_LABELS.get(round(density_percent / 5) * 5, f"Custom {density_percent}%")
        valid = 70 <= density_percent <= 120
        result["density"] = {
            "percent": density_percent,
            "label": label,
            "valid": valid,
            "warning": None if valid else "Density must be 70-120%. Outside this range looks unnatural."
        }

    if base_type and base_type in BASE_TYPES:
        result["base"] = {"type": base_type, "description": BASE_TYPES[base_type]}
    elif base_type:
        result["base"] = {"error": f"Unknown base type '{base_type}'. Valid: {list(BASE_TYPES.keys())}"}

    if hair_origin and hair_origin in HAIR_ORIGINS:
        result["hair_origin"] = {"type": hair_origin, "description": HAIR_ORIGINS[hair_origin]}
    elif hair_origin:
        result["hair_origin"] = {"error": f"Unknown hair origin '{hair_origin}'. Valid: {list(HAIR_ORIGINS.keys())}"}

    if not result:
        result["available"] = {
            "colors": list(COLORS.keys()),
            "curl_patterns": list(CURL_PATTERNS.keys()),
            "density_range": "70-120%",
            "base_types": list(BASE_TYPES.keys()),
            "hair_origins": list(HAIR_ORIGINS.keys()),
            "lighting": list(LIGHTING_STYLES.keys()),
            "camera_specs": list(CAMERA_SPECS.keys()),
            "video_types": ["lifestyle", "hair_movement"],
        }

    return result


def match_hair_color(
    description: str,
    grey_percentage: Optional[int] = None,
    tool_context: Optional[Context] = None,
) -> dict:
    """Match a client's description to the exact hair system color code.

    Args:
        description: Client's hair color description.
        grey_percentage: Estimated grey percentage if known.

    Returns:
        Dict with matched color and grey blend recommendation.
    """
    color_map = {
        "jet black": "#1",
        "natural black": "#1B",
        "off black": "#1B",
        "darkest brown": "#2",
        "dark brown": "#3",
        "medium brown": "#4",
        "light brown": "#5",
        "dark blonde": "#6",
        "medium blonde": "#7",
        "light blonde": "#8",
        "very light blonde": "#9",
        "platinum blonde": "#10",
    }

    desc_lower = description.lower()
    for key, code in color_map.items():
        if key in desc_lower:
            result = {"status": "matched", "color_code": code, "color_name": key.title()}
            if grey_percentage and grey_percentage > 0:
                g = min(grey_percentage, 50)
                result["grey_blend"] = f"{code}{g}"
                result["grey_note"] = (
                    f"{g}% grey blended into {code}. Grey heavier at temples. "
                    f"Final blend code: {code}{g}"
                )
            return result

    return {
        "status": "needs_clarification",
        "valid_codes": {k: v for k, v in color_map.items()},
        "message": "Could not determine exact color. Ask for a photo or specify from the color ring.",
    }


def recommend_base_type(
    lifestyle: str = "moderate",
    budget: str = "standard",
    exposed_hairline: bool = True,
    desired_lifespan: Optional[int] = None,
    tool_context: Optional[Context] = None,
) -> dict:
    """Recommend the best base type based on client profile.

    Args:
        lifestyle: sedentary, moderate, active, athletic.
        budget: economy, standard, premium.
        exposed_hairline: Whether the client wears their hairline exposed.
        desired_lifespan: Desired lifespan in months.

    Returns:
        Dict with primary recommendation and alternatives.
    """
    bases = {
        "ultra_thin_skin": {
            "name": "Ultra-Thin Skin 0.03mm", "realism": 10, "durability": 3,
            "lifespan": "2-3 months", "cost": "premium",
        },
        "thin_skin": {
            "name": "Thin Skin 0.06-0.08mm", "realism": 8, "durability": 6,
            "lifespan": "3-4 months", "cost": "standard",
        },
        "swiss_lace": {
            "name": "Swiss Lace", "realism": 10, "durability": 3,
            "lifespan": "1.5-2 months", "cost": "premium",
        },
        "french_lace": {
            "name": "French Lace", "realism": 7, "durability": 6,
            "lifespan": "2-3 months", "cost": "standard",
        },
        "hybrid": {
            "name": "Hybrid Skin+Lace", "realism": 9, "durability": 5,
            "lifespan": "2-3 months", "cost": "premium",
        },
    }

    scored = []
    lifestyle_durability = {"sedentary": 0, "moderate": 3, "active": 5, "athletic": 7}
    min_durability = lifestyle_durability.get(lifestyle, 3)

    for key, b in bases.items():
        score = 0
        if exposed_hairline:
            score += b["realism"]
        if budget == "premium" and b["cost"] == "premium":
            score += 3
        elif budget == "standard" and b["cost"] in ("standard", "premium"):
            score += 2
        elif budget == "economy" and b["cost"] == "economy":
            score += 3
        if b["durability"] >= min_durability:
            score += 3
        scored.append({"key": key, "score": score, **b})

    scored.sort(key=lambda x: x["score"], reverse=True)

    return {
        "status": "recommended",
        "primary": scored[0]["name"],
        "rationale": f"Best match for {lifestyle} lifestyle, {budget} budget, "
                     f"{'exposed' if exposed_hairline else 'covered'} hairline.",
        "alternatives": [s["name"] for s in scored[1:3]],
    }


def calculate_density(
    age: int = 35,
    norwood_level: int = 4,
    style_preference: str = "natural",
    biological_density: str = "medium",
    tool_context: Optional[Context] = None,
) -> dict:
    """Calculate the recommended hair system density.

    Args:
        age: Client age.
        norwood_level: Norwood scale 1-7.
        style_preference: natural, full, or light.
        biological_density: light, medium, or heavy.

    Returns:
        Dict with density recommendation and graduation plan.
    """
    if age < 25: base = 110
    elif age < 30: base = 105
    elif age < 35: base = 100
    elif age < 40: base = 95
    elif age < 45: base = 90
    elif age < 50: base = 85
    elif age < 55: base = 80
    else: base = 75

    if style_preference == "full": base += 10
    elif style_preference == "light": base -= 10
    if biological_density == "heavy": base += 5
    elif biological_density == "light": base -= 5

    base = max(70, min(120, base))

    return {
        "status": "calculated",
        "density_percent": base,
        "hairline_edge": f"{int(base * 0.65)}%",
        "front_third": f"{int(base * 0.85)}%",
        "crown": f"{base}%",
        "graduation_note": "Front 0.5cm: graduated 60-65% → 40% at edge. "
                          "Single bleached knots. Baby hairs.",
    }


def lookup_reference_swatches(
    folder: str = "02_specs/swatches",
    tag_query: str = "",
    limit: int = 10,
    tool_context: Optional[Context] = None,
) -> dict:
    """Look up reference swatches and product images in the HSC R2 reference manifest.

    Args:
        folder: Manifest folder prefix (e.g. "02_specs/swatches/hair-color",
            "02_specs/swatches/curl-pattern", "02_specs/swatches/base-material",
            "02_specs/swatches/density", "01_products/hair-systems").
        tag_query: Tag or display name substring to filter by (e.g. "color:1b",
            "french-lace", "curl:15mm", "hairline:natural").
        limit: Max rows to return (1-50).

    Returns:
        Dict with matching manifest entries and R2 keys.
    """
    return lookup_manifest_references(folder=folder, tag_query=tag_query, limit=limit)

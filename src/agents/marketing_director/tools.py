"""Tools for the Marketing Image Generation Director.

Generates original, on-brand marketing visuals using Atelier Zero v7
and the Carrara marble head concept. Every marble head is a fresh creation
unless the user names a specific character (Leo, Miles, Marc, Ray).
"""

import os
import time
from typing import Optional

from google.adk import Context
from google import genai
from google.genai import types as genai_types


# ── Brand Color Constants ─────────────────────────────────────────────────

PAPER = "#EFE7D2"
BONE = "#F7F1DE"
INK = "#15140F"
CORAL = "#FF5757"
CORAL_SOFT = "#F08E7C"
MUSTARD = "#E9B94A"
OLIVE = "#6E7448"

# ── Marble Head DNA (always included) ────────────────────────────────────

MARBLE_DNA = (
    "Ultra-realistic commercial photograph of a classical display bust of a man carved "
    "from white Carrara marble, finely sculpted realistic male facial features, softly "
    "carved blank eyes with no pupils, luminous white stone with soft grey veining and "
    "subsurface translucency, gently polished planes, a matte fractured edge at the "
    "shoulder truncation, mounted on a marble plinth, wearing a hyper-realistic "
    "human-hair men's hair system with individually visible strands and a perfectly "
    "natural front hairline meeting the stone. Sharp focus, 8k detail, professional "
    "studio product photography, photorealistic."
)

MARBLE_NEGATIVE = (
    "human skin, skin tone, flesh tones, eyes with pupils, eyelashes, painted face, "
    "glossy plastic, shiny surface, wig cap visible, lace edge visible, clothing, "
    "jewelry, cartoon, illustration, text, watermark, extra heads, deformed features, "
    "synthetic-looking hair, helmet hair, plastic hair, doll hair"
)

# ── Known characters (only used when user explicitly names them) ──────────

KNOWN_CHARACTERS = {
    "leo": "a man in his mid-20s, youthful sculpted features, smooth defined jawline, soft cheekbones, fresh and energetic facial structure",
    "miles": "a Black man in his mid-30s, broad nose with a wide flat bridge and full rounded tip, full wide lips with a defined cupid's bow, strong straight horizontal brow ridge, high wide cheekbones, broad square jaw, calm self-assured facial structure",
    "marc": "a man in his early 40s, composed mature sculpted features, defined jaw, subtle sculpted expression lines on the forehead, confident settled facial structure",
    "ray": "a distinguished man in his early 60s, mature sculpted features with pronounced character lines, strong brow, defined nasolabial folds, dignified weathered facial structure",
}

MILES_IDENTITY = (
    "CRITICAL - preserve the subject's exact facial architecture: "
    "the broad nose with its wide flat bridge and full rounded tip, the full wide lips "
    "with a defined cupid's bow, the strong straight horizontal brow ridge, the high "
    "wide cheekbones and the broad square jaw. Do not narrow the nose, do not thin the "
    "lips, do not alter the ethnicity of the face."
)


# ── Prompt builders ───────────────────────────────────────────────────────

def build_marble_prompt(face_description: str) -> str:
    """Build a marble head prompt from a free-form face description."""
    return (
        f"{MARBLE_DNA} The bust depicts {face_description}. "
        f"{MARBLE_NEGATIVE}"
    )


def build_collage_prompt(
    face_description: str,
    series_number: int = 1,
    composition_hint: str = "",
) -> str:
    """Build an editorial collage prompt in the Krea marble style."""
    comp = ""
    if composition_hint:
        comp = f" Composition direction: {composition_hint}."

    return (
        f"A numbered editorial collage poster, vertical 4:5 aspect ratio. "
        f"The ground is aged {PAPER}-toned paper with subtle film-grain texture. "
        f"A large textured Coral (#FF5757) sun disc sits prominently behind the subject, "
        f"partially obscured. A smaller Mustard (#E9B94A) accent disc adds depth. "
        f"Fine graphite orbital pencil lines and cloud engravings layer behind. "
        f"Sparse halftone dots float in the composition. A cracked-concrete "
        f"torn-paper wedge crosses one lower corner. A small sequential number "
        f"'No.{series_number:02d}' appears near the upper right in a clean serif typeface. "
        f"{comp}"
        f"\n\nThe main subject: a classical male bust carved from warmly lit ivory Carrara "
        f"marble with natural fractures, chisel texture, and soft grey veining. "
        f"Softly carved blank eyes with no pupils. The bust depicts {face_description}. "
        f"The only living material on the bust is real photographic human hair — "
        f"individual fibers visible, natural irregular hairline where it meets the stone. "
        f"No human skin anywhere. The bust floats or overlaps the collage elements. "
        f"\n\nNo square pedestal or museum-loft staging. Warm, weathered, layered editorial "
        f"look — NOT a bright corporate palette. The Coral disc is prominent even when "
        f"partly hidden. Photorealistic, 8K, editorial print quality. "
        f"\n\nNEGATIVE: human skin, skin tone, flesh tones, eyes with pupils, painted face, "
        f"glossy plastic, shiny surface, wig cap, lace edge, clothing, jewelry, cartoon, "
        f"bright saturated corporate colors, museum product photography, text-heavy layout, "
        f"marketing copy in the image body, synthetic hair, helmet hair, plastic hair."
    )


def build_social_prompt(
    face_description: str,
    platform: str = "feed",
    campaign: str = "",
    composition_hint: str = "",
) -> str:
    """Build a platform-specific social media image prompt."""
    dims = {
        "feed": "1:1 square 1080x1080",
        "story": "9:16 vertical 1080x1920",
        "reel": "9:16 vertical 1080x1920",
        "carousel": "4:5 vertical 1080x1350",
    }
    dim = dims.get(platform, "1:1 square")

    campaign_prompt = ""
    if campaign == "black_friday":
        campaign_prompt = (
            "Dark, premium atmosphere. Dramatic single key light carving the facial "
            "features from deep shadow. Coral accent block reserved in negative space. "
            "Editorial urgency, never desperate. "
        )
    elif campaign == "product_launch":
        campaign_prompt = (
            "Clean gallery-style composition with generous negative space. "
            "Soft diffused daylight. Airy, minimal, contemporary. "
        )
    elif campaign == "editorial":
        campaign_prompt = (
            "Layered, art-directed composition. Dramatic lighting. "
            "Museum-grade atmosphere. "
        )

    comp = ""
    if composition_hint:
        comp = f" Additional direction: {composition_hint}."

    return (
        f"A photorealistic social media image, {dim}, for Hair Solutions Co. "
        f"{campaign_prompt}"
        f"The main subject is a classical Carrara marble bust. "
        f"{MARBLE_DNA} The bust depicts {face_description}. "
        f"Background: {PAPER}-toned with subtle film grain texture. "
        f"Atelier Zero v7 brand aesthetic — warm, editorial, calm, never corporate. "
        f"No text on the image (overlays are added in design software). "
        f"Corner registration marks: 1px L-shaped brackets in Ink at opposing corners. "
        f"{comp}"
        f"Photorealistic, 8K. "
        f"NEGATIVE: {MARBLE_NEGATIVE} text on the image, logos, gradients, glows, "
        f"bright saturated colors, corporate stock photo energy."
    )


# ── Output helper ─────────────────────────────────────────────────────────

def _save_image(response, prefix: str = "marketing") -> Optional[str]:
    """Extract generated image, save to disk, return path. Never return base64."""
    for part in response.candidates[0].content.parts:
        if part.inline_data and part.inline_data.mime_type.startswith("image/"):
            ext = part.inline_data.mime_type.split("/")[-1]
            out_dir = os.path.join(os.path.dirname(__file__), ".adk", "generated")
            os.makedirs(out_dir, exist_ok=True)
            path = os.path.join(out_dir, f"{prefix}_{int(time.time())}.{ext}")
            with open(path, "wb") as f:
                f.write(part.inline_data.data)
            return path
    return None


# ── Generation Tools ──────────────────────────────────────────────────────

def generate_marble_head(
    face_description: str,
    lighting: str = "gallery",
    pose: str = "",
    composition: str = "",
    tool_context: Optional[Context] = None,
) -> dict:
    """Generate a portrait of a unique Carrara marble head with hyper-realistic human hair.

    This is the primary tool for marble head imagery. Every call creates a NEW face
    based on your description — age, ethnicity, bone structure, expression, hair.

    Args:
        face_description: Full description of the marble bust's face. Include age,
            ethnicity, bone structure, facial features, expression, hair color, hair style.
            Be specific and vivid. Examples:
            - "a Black man in his late 40s, strong angular jaw, deep-set contemplative
               eyes (carved blank), short silver-grey waves with a sharp edge-up"
            - "a young Italian man, 28, aquiline nose, strong brow, dark chestnut curls
               falling loosely, warm Renaissance energy"
            - "a weathered man in his 60s, Nordic bone structure, deep nasolabial folds,
               long swept-back ash-blonde hair with grey streaks, Viking dignity"
        lighting: gallery (soft diffused), authority (dramatic single key on dark),
                  golden (warm directional sunlight), editorial (high contrast museum).
        pose: Optional. E.g. "front-facing", "three-quarter left", "profile",
              "chin raised, proud", "downcast, contemplative".
        composition: Optional creative direction for framing, crop, negative space.

    Returns:
        Dict with image path and generation metadata.
    """
    # Resolve known character names if used
    face = face_description
    name_lower = face_description.strip().lower()
    for key in KNOWN_CHARACTERS:
        if name_lower == key or name_lower.startswith(f"{key} "):
            face = KNOWN_CHARACTERS[key] + (
                f" {MILES_IDENTITY}" if key == "miles" else ""
            )
            break

    # Build context
    extra = []
    if pose:
        extra.append(f"Pose: {pose}.")
    if composition:
        extra.append(f"Composition: {composition}.")

    lighting_map = {
        "gallery": "set against a light poured-concrete wall, soft diffused daylight from the left, airy minimal gallery atmosphere",
        "authority": "set against a dark charcoal backdrop, single dramatic key light from upper left, deep soft shadows, premium moody atmosphere",
        "golden": "placed on a concrete shelf, hard directional golden sunlight through a window, long warm shadows, cinematic warm atmosphere",
        "editorial": "set against a deep shadow backdrop, high-contrast museum lighting, razor-sharp rim light, dramatic editorial atmosphere",
    }
    light_desc = lighting_map.get(lighting, lighting_map["gallery"])
    extra.append(f"Lighting: {light_desc}.")

    prompt = f"{MARBLE_DNA} The bust depicts {face}. {' '.join(extra)} {MARBLE_NEGATIVE}"

    try:
        client = genai.Client()
        response = client.models.generate_content(
            model="gemini-3.1-flash-image",
            contents=genai_types.Content(role="user", parts=[genai_types.Part.from_text(text=prompt)]),
            config=genai_types.GenerateContentConfig(response_modalities=["IMAGE", "TEXT"]),
        )
        path = _save_image(response, "marble_head")
        return {
            "status": "generated",
            "image_path": path,
            "face": face_description[:100],
            "lighting": lighting,
            "message": f"Marble head generated. {face_description[:80]}... Saved to {path}",
        }
    except Exception as e:
        return {"status": "error", "error": str(e)}


def generate_editorial_collage(
    face_description: str,
    series_number: int = 1,
    composition: str = "",
    tool_context: Optional[Context] = None,
) -> dict:
    """Generate a numbered editorial collage poster in the Krea marble style.

    Atelier Zero v7 colors: Paper #EFE7D2 ground, Coral #FF5757 sun disc,
    Mustard #E9B94A accent, Ink #15140F details. Layered, weathered, editorial.

    Args:
        face_description: Description of the marble bust's face — age, ethnicity,
            features, hair. The agent invents a NEW face each time.
        series_number: Sequential poster number for the editorial series (1-99).
        composition: Optional creative direction for collage layout, disc placement,
            wedge angle, lighting mood.

    Returns:
        Dict with image path and generation metadata.
    """
    name_lower = face_description.strip().lower()
    face = face_description
    for key in KNOWN_CHARACTERS:
        if name_lower == key or name_lower.startswith(f"{key} "):
            face = KNOWN_CHARACTERS[key] + (f" {MILES_IDENTITY}" if key == "miles" else "")
            break

    prompt = build_collage_prompt(face, series_number, composition)

    try:
        client = genai.Client()
        response = client.models.generate_content(
            model="gemini-3.1-flash-image",
            contents=genai_types.Content(role="user", parts=[genai_types.Part.from_text(text=prompt)]),
            config=genai_types.GenerateContentConfig(response_modalities=["IMAGE", "TEXT"]),
        )
        path = _save_image(response, f"collage_no{series_number:02d}")
        return {
            "status": "generated",
            "image_path": path,
            "series_number": series_number,
            "message": f"Editorial collage No.{series_number:02d} generated. Saved to {path}",
        }
    except Exception as e:
        return {"status": "error", "error": str(e)}


def generate_social_asset(
    face_description: str,
    platform: str = "feed",
    campaign: str = "",
    composition: str = "",
    tool_context: Optional[Context] = None,
) -> dict:
    """Generate a platform-specific social media image.

    Args:
        face_description: Description of the marble bust's face.
        platform: feed (1:1), story (9:16), reel (9:16), carousel (4:5).
        campaign: general, black_friday, product_launch, editorial.
        composition: Optional creative direction.

    Returns:
        Dict with image path and generation metadata.
    """
    name_lower = face_description.strip().lower()
    face = face_description
    for key in KNOWN_CHARACTERS:
        if name_lower == key or name_lower.startswith(f"{key} "):
            face = KNOWN_CHARACTERS[key] + (f" {MILES_IDENTITY}" if key == "miles" else "")
            break

    prompt = build_social_prompt(face, platform, campaign, composition)

    try:
        client = genai.Client()
        response = client.models.generate_content(
            model="gemini-3.1-flash-image",
            contents=genai_types.Content(role="user", parts=[genai_types.Part.from_text(text=prompt)]),
            config=genai_types.GenerateContentConfig(response_modalities=["IMAGE", "TEXT"]),
        )
        path = _save_image(response, f"social_{platform}_{campaign or 'general'}")
        return {
            "status": "generated",
            "image_path": path,
            "platform": platform,
            "campaign": campaign or "general",
            "message": f"Social asset generated: {platform} {campaign or 'general'}. Saved to {path}",
        }
    except Exception as e:
        return {"status": "error", "error": str(e)}


def generate_campaign_visual(
    description: str,
    campaign_type: str = "general",
    use_marble_head: bool = True,
    face_description: str = "",
    composition: str = "",
    tool_context: Optional[Context] = None,
) -> dict:
    """Generate a general campaign/marketing visual following Atelier Zero v7 rules.

    The most flexible tool — describe what you want and let the brand system
    shape the output.

    Args:
        description: What the image should depict, the concept, the mood.
            Be creative. The agent translates this into a brand-compliant visual.
        campaign_type: general, black_friday, product_launch, instagram, email.
        use_marble_head: If True, includes a marble head as the subject.
        face_description: If use_marble_head is True, describe the face.
            Leave empty for the agent to invent one.
        composition: Optional creative direction.

    Returns:
        Dict with image path and generation metadata.
    """
    brand_rules = (
        f"Brand system: Atelier Zero v7. Canvas: {PAPER}. Primary accent: {CORAL} "
        f"(spot color, used sparingly). Dark ground: {INK}. "
        f"Film grain on all backgrounds (σ≈1.0). No gradients, no glows, no shadows "
        f"on light surfaces. One Ink section max per composition. "
        f"Typography: Inter Tight for display, Inter for body, Playfair Display italic "
        f"for emphasis (family switch, never bold-inside-bold). "
        f"Voice: calm, direct, educational. Sentence case. No hype, no pity, no shame, "
        f"no emoji, no exclamation marks. "
    )

    if campaign_type == "black_friday":
        brand_rules += (
            "Campaign exception: Coral-forward. Dark, premium atmosphere. "
            "Editorial urgency allowed but never desperate. "
            "Dramatic single key light, deep shadows. "
        )
    elif campaign_type == "product_launch":
        brand_rules += "Clean, gallery-style. Generous negative space. Airy, minimal. "

    subject = ""
    if use_marble_head:
        if face_description:
            name_lower = face_description.strip().lower()
            face = face_description
            for key in KNOWN_CHARACTERS:
                if name_lower == key or name_lower.startswith(f"{key} "):
                    face = KNOWN_CHARACTERS[key] + (f" {MILES_IDENTITY}" if key == "miles" else "")
                    break
        else:
            # Agent didn't specify — let the model invent
            face = "a unique, never-before-seen male face appropriate to the creative direction"
        subject = (
            f"Subject: A classical Carrara marble bust with blank carved eyes, "
            f"fractured shoulder truncation, hyper-realistic human hair with individual "
            f"strands and natural hairline. The bust depicts {face}. "
        )

    comp = ""
    if composition:
        comp = f" Composition: {composition}."

    prompt = (
        f"A photorealistic marketing image for Hair Solutions Co. {brand_rules}"
        f"{subject}"
        f"Creative direction: {description}.{comp}"
        f"Photorealistic, 8K, editorial quality. No text on the image. "
        f"NEGATIVE: {MARBLE_NEGATIVE} gradients, glows, corporate stock photo, "
        f"bright saturated palette, cartoon, illustration, text overlay, watermark."
    )

    try:
        client = genai.Client()
        response = client.models.generate_content(
            model="gemini-3.1-flash-image",
            contents=genai_types.Content(role="user", parts=[genai_types.Part.from_text(text=prompt)]),
            config=genai_types.GenerateContentConfig(response_modalities=["IMAGE", "TEXT"]),
        )
        path = _save_image(response, f"campaign_{campaign_type}")
        return {
            "status": "generated",
            "image_path": path,
            "campaign_type": campaign_type,
            "message": f"Campaign visual generated: {campaign_type}. Saved to {path}",
        }
    except Exception as e:
        return {"status": "error", "error": str(e)}


def get_brand_spec(
    element: str = "",
    tool_context: Optional[Context] = None,
) -> dict:
    """Look up Atelier Zero v7 brand specifications.

    Args:
        element: What to look up — "colors", "typography", "marble_concept",
                 "composition", "collage_language", "voice", or empty for overview.
    """
    specs = {
        "colors": {
            "canvas": {"Paper": PAPER, "Paper Warm": "#ECE4CF", "Paper Dark": "#DDD2B6"},
            "surfaces": {"Bone (raised)": BONE},
            "text": {"Ink": INK, "Ink Soft": "#2A2620", "Ink Mute": "#5A5448", "Ink Faint": "#8B8676"},
            "accents": {"Coral (spot)": CORAL, "Coral Soft": CORAL_SOFT, "Mustard": MUSTARD, "Olive": OLIVE},
            "coral_rules": "SPOT COLOR. 5 roles only: display periods, section eyebrows, sequence numerals, active state, one primary button per page. NEVER body text, NEVER surface fill, NEVER twice in one viewport.",
        },
        "typography": {
            "display": "Inter Tight 96px/800 — leading sub-1.0, lines interlock",
            "headings": "Inter Tight H1 72px · H2 48px · H3 28px",
            "body": "Inter 16px/400 · lead 19px/400",
            "emphasis": "Playfair Display italic — FAMILY SWITCH, never bold-inside-bold",
            "metadata": "JetBrains Mono 11px UPPERCASE",
            "coral_period": "Every display headline ends in . set in Coral",
        },
        "marble_concept": {
            "material": "White Carrara marble, grey veining, subsurface translucency, matte fractured shoulder edge",
            "eyes": "Softly carved blank — NO pupils, NO eyelashes, NO human expression through eyes",
            "hair": "Hyper-realistic human hair, individual strands visible, natural irregular hairline where it meets the stone. The ONLY living material.",
            "never": "Human skin, flesh tones, painted faces, glossy plastic, wig caps, lace edges, clothing, jewelry",
            "known_characters": "Leo (26), Miles (34, Black), Marc (42), Ray (63) — only use when explicitly named",
        },
        "composition": {
            "collage": "Square 1:1 plates, 4-8px radius. Corner registration marks (1px L-brackets). Gallery plates: floating micro-caps chip top-left.",
            "elevation": "No shadows on light-canvas cards. Lightness step IS elevation. Shadows only inside Ink panel (cards rotated ±2°).",
            "film_grain": "σ≈1.0 on all Paper surfaces. Flat fill loses the paper reading.",
            "coral_budget": "5 roles max. Two Corals never compete in one viewport.",
        },
        "collage_language": {
            "ground": f"Aged {PAPER}-toned paper with film grain",
            "coral_disc": "Prominent textured Coral sun disc partly behind the bust",
            "mustard_disc": "Smaller Mustard accent disc for depth",
            "elements": "Graphite cloud engravings, fine orbital pencil lines, sparse halftone dots",
            "wedge": "Cracked-concrete torn-paper wedge crossing a lower corner",
            "numbering": "Small sequential No.01, No.02... near upper right in clean serif",
            "mood": "Warm, weathered, layered editorial — never bright corporate",
        },
        "voice": {
            "tone": "Calm, direct, educational, specific. Sentence case.",
            "never": "Hype, pity, shame, urgency, scarcity, medical framing, emoji, exclamation marks, guarantees, unsupported claims.",
            "exception": "Campaign urgency (Black Friday) allowed but never desperate.",
        },
    }

    if element and element in specs:
        return {"status": "found", element: specs[element]}
    elif element:
        return {"status": "not_found", "available": list(specs.keys())}
    return {"status": "overview", **specs}
"""Tools for the Marketing Image Generation Director agent.

Generates on-brand marketing visuals using the Atelier Zero v7 design system
and the Hair Solutions Co. marble head mascot system.
"""

import base64
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
INK_SOFT = "#2A2620"
INK_MUTE = "#5A5448"
INK_FAINT = "#8B8676"
CORAL = "#FF5757"
CORAL_SOFT = "#F08E7C"
MUSTARD = "#E9B94A"
OLIVE = "#6E7448"

# ── Marble Head Composable Prompt System (v2.0) ──────────────────────────

BASE_DNA = (
    "Ultra-realistic commercial photograph of a classical display bust of a man carved "
    "from white Carrara marble, finely sculpted realistic male facial features, softly "
    "carved blank eyes with no pupils, luminous white stone with soft grey veining and "
    "subsurface translucency, gently polished planes, a matte fractured edge at the "
    "shoulder truncation, mounted on a marble plinth, wearing a hyper-realistic "
    "human-hair men's hair system with individually visible strands and a perfectly "
    "natural front hairline meeting the stone. Sharp focus, 8k detail, professional "
    "studio product photography, photorealistic."
)

NEGATIVE = (
    "human skin, skin tone, flesh tones, eyes with pupils, eyelashes, painted face, "
    "glossy plastic, shiny surface, wig cap visible, lace edge visible, clothing, "
    "jewelry, cartoon, illustration, text, watermark, extra heads, deformed features, "
    "synthetic-looking hair, helmet hair, plastic hair, doll hair"
)

MILES_IDENTITY_CLAUSE = (
    "CRITICAL - preserve the subject's exact facial architecture from the reference: "
    "the broad nose with its wide flat bridge and full rounded tip, the full wide lips "
    "with a defined cupid's bow, the strong straight horizontal brow ridge, the high "
    "wide cheekbones and the broad square jaw. Do not narrow the nose, do not thin the "
    "lips, do not alter the ethnicity of the face. Only the material changes - the "
    "bone structure must stay identical."
)

CHARACTERS = {
    "leo": "the bust depicts a man in his mid-20s, youthful sculpted features, smooth "
           "defined jawline, soft cheekbones, fresh and energetic facial structure",
    "miles": "the bust depicts a Black man in his mid-30s, broad nose with a wide flat "
             "bridge and full rounded tip, full wide lips with a defined cupid's bow, "
             "strong straight horizontal brow ridge, high wide cheekbones, broad square "
             "jaw, calm self-assured facial structure",
    "marc": "the bust depicts a man in his early 40s, composed mature sculpted features, "
            "defined jaw, subtle sculpted expression lines on the forehead, confident "
            "settled facial structure",
    "ray": "the bust depicts a distinguished man in his early 60s, mature sculpted "
           "features with pronounced character lines, strong brow, defined nasolabial "
           "folds, dignified weathered facial structure",
}

HAIR_COLOURS = {
    "leo": {
        "jet": "dense jet-black hair with natural body and subtle movement, deep matte black",
        "chestnut": "rich chestnut-brown hair with warm copper undertones, natural wave and volume",
        "espresso": "very dark espresso-brown hair, warm near-black depth",
        "ash": "ash-brown hair with cool grey undertones, modern muted tone",
        "auburn": "auburn-copper hair with warm reddish highlights, vibrant depth",
        "dark_blonde": "dark honey-blonde hair, natural sunkissed dimension",
    },
    "miles": {
        "jet": "dense jet-black hair with a tight natural wave pattern, deep matte black with cool sheen",
        "espresso": "very dark espresso-brown hair with a tight wave pattern, warm near-black depth",
        "silver_temples": "jet-black tight-coiled hair with distinct silver-grey at the temples, natural early greying",
        "salt_pepper": "salt-and-pepper tight coils, evenly mixed charcoal and silver strands throughout",
        "sterling": "full sterling-silver-white tight coils, luminous grey-white against the stone",
        "auburn": "black hair with a warm auburn cast, subtle reddish-copper tone in the wave pattern",
    },
    "marc": {
        "espresso": "rich espresso-brown hair with natural body and subtle dimension",
        "chestnut": "chestnut-brown hair with warm undertones, polished yet natural",
        "jet": "jet-black hair with a professional natural sheen, composed",
        "grey_temples": "dark brown hair with distinguished grey at the temples, natural aging",
        "ash": "ash-brown hair, muted and sophisticated, cool undertone",
        "salt_pepper": "light salt-and-pepper throughout, distinguished and modern",
    },
    "ray": {
        "sterling": "full sterling-silver hair, luminous and distinguished, naturally aged",
        "salt_pepper": "salt-and-pepper mix, evenly distributed charcoal and silver",
        "soft_white": "soft white hair, purely distinguished, gentle natural texture",
        "ash": "ash-grey hair with cool undertones, refined and modern",
        "steel": "steel grey-brown hair with dimensional lowlights, natural depth",
        "pepper_white": "dark pepper base with bright white temples, striking distinguished contrast",
    },
}

HAIR_STYLES = {
    "leo": {
        "messy_quiff": "messy textured quiff with volume at the front, piece-y definition, modern casual",
        "textured_crop": "short textured crop with choppy layers, boyish energy",
        "curly_top": "curly top with natural ringlets, volume and bounce",
        "curtain_fringe": "curtain fringe parted at center, soft flow",
        "long_flow": "longer textured flow, ear-length, natural movement",
        "buzz_taper": "short buzz taper, clean sharp edges, minimalist",
    },
    "miles": {
        "tight_wave_crop": "tight wave crop, dense coiled texture, sharp shape-up edge",
        "defined_coils": "defined coils with sculpted shape, natural texture",
        "high_taper": "high taper fade with textured coils on top, clean architectural lines",
        "short_twists": "short two-strand twists, even distribution across scalp",
        "rounded_afro": "rounded afro shape, full even density, natural coiled texture",
        "shadow_taper": "shadow taper fade, gradual transition, tight coils on top",
    },
    "marc": {
        "wavy_side_sweep": "wavy side sweep, polished volume, professional yet modern",
        "classic_side_part": "classic side part, precise clean line, timeless",
        "executive_quiff": "executive quiff with controlled height, boardroom-ready",
        "slick_back": "polished slick back, wet-look finish, formal",
        "long_flow": "longer natural flow, relaxed professional, ear-to-collar length",
        "wavy_taper": "wavy taper fade, textured top, modern professional",
    },
    "ray": {
        "silver_pompadour": "classic silver pompadour with volume and sweep, distinguished",
        "side_sweep": "distinguished side sweep, swept back from forehead, elegant",
        "cropped_silver": "cropped silver texture, short and refined, low maintenance",
        "swept_waves": "swept-back waves, full-bodied silver, timeless elegance",
        "long_silver": "longer silver flow, collar-length, artistic distinguished",
        "salt_pepper_taper": "salt-and-pepper taper, clean fade, mature modern",
    },
}

POSES = {
    "front": "bust facing the camera directly, perfectly centered, symmetrical head-on composition at eye level",
    "34l": "bust in three-quarter view turned to the left, showing the left side of the face and the hair's side profile, camera at eye level",
    "34r": "bust in three-quarter view turned to the right, showing the right side of the face and the hair's side profile, camera at eye level",
    "profile": "bust in full right side profile, showing the complete silhouette of the nose, chin and the hairline from forehead to nape",
    "down": "head tilted gently downward, chin lowered, contemplative introspective angle, camera at eye level looking slightly down onto the crown to show the top of the hair",
    "up": "head tipped back with the chin raised and lifted, proud upward angle, camera slightly below eye level looking up at the underside of the jaw",
}

BUST_TREATMENTS = {
    "pristine": "flawless newly carved marble, immaculately polished surfaces, crisp clean truncation, mounted on a simple turned circular marble plinth",
    "weathered": "aged weathered marble with a soft patina, fine surface pitting and hairline age cracks, gently eroded edges, small chips at the truncation, mounted on a worn circular plinth, museum-excavation character",
    "fractured": "asymmetric broken bust, one shoulder raised and intact while the other side breaks away in a rough diagonal fracture, exposed crystalline stone at the break, deliberately unfinished sculptural quality",
    "block": "mounted on a heavy squared architectural marble block base with sharp right-angled edges, brutalist plinth, the bust sitting slightly off-centre on the block",
}

MOODS = {
    "gallery": "set against a light poured-concrete wall, soft diffused daylight from the left, gentle soft shadow behind the bust, airy minimal gallery atmosphere, light grey and off-white tones",
    "authority": "set against a dark charcoal studio backdrop, single dramatic key light from the upper left, deep soft shadows carving the facial features, premium moody atmosphere",
    "golden": "placed on a concrete shelf in an industrial loft, hard directional golden sunlight through a window, long warm shadows on the concrete wall, cinematic warm atmosphere",
    "lineup": "multiple marble busts arranged in a row on a polished concrete plinth, light concrete architecture behind, soft daylight from large windows, symmetrical product-display composition",
}


# ── Prompt Builders ───────────────────────────────────────────────────────

def build_marble_head_prompt(
    character: str,
    hair_colour: str,
    hair_style: str,
    pose: str = "front",
    bust_treatment: str = "pristine",
    mood: str = "gallery",
) -> str:
    """Compose a marble head prompt using the v2.0 formula: BASE + CHARACTER + HAIR + POSE + MOOD + NEGATIVE."""
    char_desc = CHARACTERS.get(character, "")
    colours = HAIR_COLOURS.get(character, {})
    colour_desc = colours.get(hair_colour, hair_colour)
    styles = HAIR_STYLES.get(character, {})
    style_desc = styles.get(hair_style, hair_style)
    pose_desc = POSES.get(pose, pose)
    treatment_desc = BUST_TREATMENTS.get(bust_treatment, bust_treatment)
    mood_desc = MOODS.get(mood, mood)

    hair_block = f"{colour_desc}. {style_desc}."
    identity = ""
    if character == "miles":
        identity = f" {MILES_IDENTITY_CLAUSE}"

    return (
        f"{BASE_DNA} {char_desc}.{identity} "
        f"{hair_block} "
        f"The bust is in {pose_desc}. "
        f"{treatment_desc}. "
        f"{mood_desc}. "
        f"{NEGATIVE}"
    )


def build_editorial_collage_prompt(
    character: str,
    hair_colour: str,
    hair_style: str,
    series_number: int = 1,
    composition_variant: str = "coral_disc_center",
) -> str:
    """Build an editorial collage in the Krea marble style."""
    char_desc = CHARACTERS.get(character, "")
    colours = HAIR_COLOURS.get(character, {})
    colour_desc = colours.get(hair_colour, hair_colour)
    styles = HAIR_STYLES.get(character, {})
    style_desc = styles.get(hair_style, hair_style)
    identity = ""
    if character == "miles":
        identity = f" {MILES_IDENTITY_CLAUSE}"

    return (
        f"A numbered editorial collage portrait poster, vertical 4:5 aspect ratio. "
        f"The ground is aged {PAPER}-toned paper with subtle film-grain texture. "
        f"A large textured Coral (#FF5757) sun disc sits prominently behind the subject, "
        f"partially obscured. A smaller Mustard (#E9B94A) accent disc adds depth to the "
        f"composition. Fine graphite orbital pencil lines and cloud engravings layer behind "
        f"the bust. Sparse halftone dots float in the composition. A cracked-concrete "
        f"torn-paper wedge crosses one lower corner. A small sequential number 'No.{series_number:02d}' "
        f"appears near the upper right in a clean serif typeface. "
        f"\n\nThe main subject: a classical male bust carved from warmly lit ivory Carrara "
        f"marble with natural fractures, chisel texture, and soft grey veining. {char_desc}.{identity} "
        f"The only living material on the bust is real photographic human hair — {colour_desc}. "
        f"{style_desc}. Individual hair fibers are visible. The hairline is naturally "
        f"irregular where it meets the stone. No human skin anywhere. No pupils in the "
        f"carved eyes. The bust floats or overlaps the collage elements. "
        f"\n\nNo square pedestal or museum-loft staging. Warm, weathered, layered editorial "
        f"look — NOT a bright corporate palette. The Coral disc is prominent even when "
        f"partly hidden. Photorealistic, 8K, editorial print quality. "
        f"\n\nNEGATIVE: human skin, skin tone, flesh tones, eyes with pupils, painted face, "
        f"glossy plastic, shiny surface, wig cap, lace edge, clothing, jewelry, cartoon, "
        f"bright saturated corporate colors, museum product photography, text-heavy layout, "
        f"marketing copy in the image body."
    )


def build_social_media_prompt(
    character: str,
    hair_colour: str,
    hair_style: str,
    platform: str,
    campaign_type: str = "general",
    pose: str = "front",
    mood: str = "gallery",
) -> str:
    """Build a platform-specific social media image prompt."""
    char_desc = CHARACTERS.get(character, "")
    colours = HAIR_COLOURS.get(character, {})
    colour_desc = colours.get(hair_colour, hair_colour)
    styles = HAIR_STYLES.get(character, {})
    style_desc = styles.get(hair_style, hair_style)
    pose_desc = POSES.get(pose, pose)
    mood_desc = MOODS.get(mood, mood)
    identity = ""
    if character == "miles":
        identity = f" {MILES_IDENTITY_CLAUSE}"

    # Platform dimensions
    dims = {"feed": "1:1 square 1080x1080", "story": "9:16 vertical 1080x1920",
            "reel": "9:16 vertical 1080x1920", "carousel": "4:5 vertical 1080x1350"}
    dim = dims.get(platform, "1:1 square")

    # Campaign overlays
    campaign_prompt = ""
    if campaign_type == "black_friday":
        campaign_prompt = (
            f"The composition includes reserved negative space for a Coral (#FF5757) accent "
            f"block and bold editorial typography. Dark, premium atmosphere. The bust is in "
            f"{MOODS.get('authority', '')}. "
        )
    elif campaign_type == "product_launch":
        campaign_prompt = (
            f"Clean, gallery-style composition with generous negative space. "
            f"Soft diffused lighting. The bust is in {mood_desc}. "
        )

    return (
        f"A photorealistic social media image, {dim}, for Hair Solutions Co. "
        f"{campaign_prompt}"
        f"The main subject is a classical marble bust — {BASE_DNA} {char_desc}.{identity} "
        f"{colour_desc}. {style_desc}. "
        f"The bust is in {pose_desc}. "
        f"Background: {PAPER}-toned with subtle film grain texture. "
        f"Atelier Zero v7 brand aesthetic — warm, editorial, calm, never corporate. "
        f"No text on the image (text will be added as overlay in design software). "
        f"Corner registration marks: 1px L-shaped brackets in Ink at opposing corners. "
        f"Photorealistic, 8K, professional product photography quality. "
        f"\n\nNEGATIVE: {NEGATIVE} text on the image, marketing copy, logos, bright saturated "
        f"colors, gradients, plastic sheen, corporate stock photo energy."
    )


# ── Output helpers ─────────────────────────────────────────────────────────

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

def generate_marble_head_portrait(
    character: str = "marc",
    hair_colour: str = "espresso",
    hair_style: str = "wavy_side_sweep",
    pose: str = "front",
    bust_treatment: str = "pristine",
    mood: str = "gallery",
    tool_context: Optional[Context] = None,
) -> dict:
    """Generate a portrait of a Hair Solutions Co. marble head mascot.

    Uses the composable v2.0 prompt system: BASE + CHARACTER + HAIR + POSE + MOOD + NEGATIVE.

    Args:
        character: leo (26, youthful), miles (34, Black man), marc (42, professional), ray (63, distinguished).
        hair_colour: Per-character colour key (e.g., leo: chestnut/jet/espresso/ash/auburn/dark_blonde;
            miles: jet/espresso/silver_temples/salt_pepper/sterling/auburn;
            marc: espresso/chestnut/jet/grey_temples/ash/salt_pepper;
            ray: sterling/salt_pepper/soft_white/ash/steel/pepper_white).
        hair_style: Per-character style key (e.g., marc: wavy_side_sweep/classic_side_part/executive_quiff/
            slick_back/long_flow/wavy_taper).
        pose: front, 34l, 34r, profile, down, up.
        bust_treatment: pristine, weathered, fractured, block.
        mood: gallery, authority, golden, lineup.
    """
    prompt = build_marble_head_prompt(character, hair_colour, hair_style, pose, bust_treatment, mood)

    try:
        client = genai.Client()
        response = client.models.generate_content(
            model="gemini-3.1-flash-image",
            contents=genai_types.Content(role="user", parts=[genai_types.Part.from_text(text=prompt)]),
            config=genai_types.GenerateContentConfig(response_modalities=["IMAGE", "TEXT"]),
        )
        path = _save_image(response, f"marble_{character}_{hair_colour}")
        return {
            "status": "generated",
            "image_path": path,
            "character": character,
            "hair_colour": hair_colour,
            "pose": pose,
            "mood": mood,
            "message": f"Marble head portrait generated: {character.title()} — {hair_colour} hair, {pose} pose, {mood} mood. Saved to {path}",
        }
    except Exception as e:
        return {"status": "error", "error": str(e), "prompt": prompt}


def generate_editorial_collage(
    character: str = "marc",
    hair_colour: str = "espresso",
    hair_style: str = "wavy_side_sweep",
    series_number: int = 1,
    composition_variant: str = "coral_disc_center",
    tool_context: Optional[Context] = None,
) -> dict:
    """Generate a numbered editorial collage poster in the Krea marble style.

    Atelier Zero v7 colors: Paper #EFE7D2 ground, Coral #FF5757 sun disc,
    Mustard #E9B94A accent, Ink #15140F details. Layered, weathered, editorial
    — never bright corporate.

    Args:
        character: leo, miles, marc, or ray.
        hair_colour: Per-character colour key.
        hair_style: Per-character style key.
        series_number: Sequential poster number (1-99).
        composition_variant: coral_disc_center, coral_disc_left, coral_disc_right.
    """
    prompt = build_editorial_collage_prompt(character, hair_colour, hair_style, series_number, composition_variant)

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
            "character": character,
            "message": f"Editorial collage No.{series_number:02d} generated. {character.title()} — {hair_colour} hair. Saved to {path}",
        }
    except Exception as e:
        return {"status": "error", "error": str(e), "prompt": prompt}


def generate_social_media_asset(
    character: str = "marc",
    hair_colour: str = "espresso",
    hair_style: str = "wavy_side_sweep",
    platform: str = "feed",
    campaign_type: str = "general",
    pose: str = "front",
    mood: str = "gallery",
    tool_context: Optional[Context] = None,
) -> dict:
    """Generate a platform-specific social media image for Hair Solutions Co.

    Args:
        character: leo, miles, marc, or ray.
        hair_colour: Per-character colour key.
        hair_style: Per-character style key.
        platform: feed (1:1), story (9:16), reel (9:16), carousel (4:5).
        campaign_type: general, black_friday, product_launch, editorial.
        pose: front, 34l, 34r, profile, down, up.
        mood: gallery, authority, golden, lineup.
    """
    prompt = build_social_media_prompt(character, hair_colour, hair_style, platform, campaign_type, pose, mood)

    try:
        client = genai.Client()
        response = client.models.generate_content(
            model="gemini-3.1-flash-image",
            contents=genai_types.Content(role="user", parts=[genai_types.Part.from_text(text=prompt)]),
            config=genai_types.GenerateContentConfig(response_modalities=["IMAGE", "TEXT"]),
        )
        path = _save_image(response, f"social_{platform}_{campaign_type}")
        return {
            "status": "generated",
            "image_path": path,
            "platform": platform,
            "campaign_type": campaign_type,
            "character": character,
            "message": f"Social media asset generated: {platform} {campaign_type} — {character.title()}. Saved to {path}",
        }
    except Exception as e:
        return {"status": "error", "error": str(e), "prompt": prompt}


def generate_marketing_image(
    description: str,
    use_marble_head: bool = True,
    character: str = "marc",
    hair_colour: str = "espresso",
    campaign_type: str = "general",
    tool_context: Optional[Context] = None,
) -> dict:
    """Generate a general marketing image following Atelier Zero v7 brand rules.

    Args:
        description: What the image should depict or communicate.
        use_marble_head: Whether to use a marble head mascot as the subject.
        character: Which marble head character (if use_marble_head=True).
        hair_colour: Hair colour key for the marble head.
        campaign_type: general, black_friday, product_launch, instagram, email.
    """
    brand_rules = (
        f"Brand system: Atelier Zero v7. Canvas: {PAPER}. Primary accent: {CORAL} (spot color, "
        f"used sparingly — NEVER as body text or surface fill). Dark ground: {INK}. "
        f"Typography: Inter Tight for display, Inter for body, Playfair Display italic for "
        f"emphasis (family switch, never bold-inside-bold). "
        f"Film grain texture on all backgrounds (σ≈1.0). No gradients, no glows, no shadows "
        f"on light surfaces. One Ink section max. "
        f"Voice: calm, direct, educational, specific. Sentence case. No hype, no pity, no shame, "
        f"no medical framing, no emoji, no exclamation marks. "
    )

    if campaign_type == "black_friday":
        brand_rules += (
            f"Campaign exception: Coral-forward. Dark, premium atmosphere. "
            f"Editorial urgency allowed but never desperate. "
        )

    if use_marble_head:
        char_desc = CHARACTERS.get(character, "")
        colours = HAIR_COLOURS.get(character, {})
        colour_desc = colours.get(hair_colour, hair_colour)
        identity = f" {MILES_IDENTITY_CLAUSE}" if character == "miles" else ""
        subject = (
            f"Subject: A Carrara marble bust — {BASE_DNA} {char_desc}.{identity} "
            f"{colour_desc}. Blank carved eyes, no pupils. Real human hair meeting the stone. "
            f"Matte fractured shoulder truncation. "
        )
    else:
        subject = ""

    prompt = (
        f"A photorealistic marketing image for Hair Solutions Co. {brand_rules} "
        f"{subject}"
        f"Creative direction: {description}. "
        f"Photorealistic, 8K, editorial quality. No text on the image. "
        f"NEGATIVE: {NEGATIVE} gradients, glows, corporate stock photo, bright saturated palette, "
        f"plastic sheen, cartoon, illustration, text overlay, watermark, unapproved fonts."
    )

    try:
        client = genai.Client()
        response = client.models.generate_content(
            model="gemini-3.1-flash-image",
            contents=genai_types.Content(role="user", parts=[genai_types.Part.from_text(text=prompt)]),
            config=genai_types.GenerateContentConfig(response_modalities=["IMAGE", "TEXT"]),
        )
        path = _save_image(response, f"marketing_{campaign_type}")
        return {
            "status": "generated",
            "image_path": path,
            "campaign_type": campaign_type,
            "message": f"Marketing image generated: {campaign_type}. Saved to {path}",
        }
    except Exception as e:
        return {"status": "error", "error": str(e), "prompt": prompt}


def get_brand_spec(
    element: str = "",
    tool_context: Optional[Context] = None,
) -> dict:
    """Look up Atelier Zero v7 brand specifications.

    Args:
        element: What to look up — "colors", "typography", "marble_heads", "composition",
                 "voice", or empty for overview.
    """
    specs = {
        "colors": {
            "canvas": {"Paper": PAPER, "Paper Warm": "#ECE4CF", "Paper Dark": "#DDD2B6"},
            "surfaces": {"Bone (raised)": BONE},
            "text": {"Ink": INK, "Ink Soft": INK_SOFT, "Ink Mute": INK_MUTE, "Ink Faint": INK_FAINT},
            "accents": {
                "Coral (primary spot)": CORAL,
                "Coral Soft (on dark)": CORAL_SOFT,
                "Mustard (focus halo)": MUSTARD,
                "Olive (utility)": OLIVE,
            },
            "coral_rules": "SPOT COLOR ONLY. 5 roles: display periods, section eyebrows, sequence numerals, active state, one primary button per page. NEVER body text, NEVER surface fill, NEVER twice in one viewport.",
        },
        "typography": {
            "display": "Inter Tight 96px/800",
            "headings": "Inter Tight H1 72px · H2 48px · H3 28px · H4 19px",
            "body": "Inter 16px/400 — lead 19px/400",
            "emphasis": "Playfair Display italic — FAMILY SWITCH, never bold-inside-bold",
            "metadata": "JetBrains Mono 11px/600 UPPERCASE",
            "rule": "Display leading is sub-1.0. The coral period on headlines. Micro-caps carry metadata.",
        },
        "marble_heads": {
            "characters": {
                "leo": "26, The Comeback — youthful, smooth jaw, soft cheekbones, social-first",
                "miles": "34, The Regular — Black man, broad nose, full lips, strong brow, wide cheekbones, broad jaw. IDENTITY CLAUSE MANDATORY.",
                "marc": "42, The Professional — composed, defined jaw, expression lines, site default",
                "ray": "63, The Statesman — distinguished, character lines, strong brow, nasolabial folds",
            },
            "prompt_formula": "BASE + CHARACTER + HAIR + POSE + MOOD + NEGATIVE",
            "poses": list(POSES.keys()),
            "bust_treatments": list(BUST_TREATMENTS.keys()),
            "moods": list(MOODS.keys()),
        },
        "composition": {
            "collage": "Square 1:1 plates, 4-8px radius. Corner registration marks. Gallery plates: floating micro-caps chip top-left.",
            "elevation": "No shadows on light-canvas cards. Lightness step IS elevation. Shadows only inside Ink panel (cards rotated ±2°).",
            "film_grain": "σ≈1.0 on all Paper surfaces. Flat fill loses the paper reading.",
            "coral_budget": "5 roles max. Two Corals never compete in one viewport region.",
            "ink_limit": "One Ink (dark) section max per composition.",
        },
        "voice": {
            "tone": "Calm, direct, educational, specific. Sentence case.",
            "never": "Hype, pity, shame, urgency, scarcity, medical framing, emoji, exclamation marks, guarantees, unsupported claims.",
            "exception": "Campaign urgency (Black Friday) is allowed but never desperate.",
        },
    }

    if element and element in specs:
        return {"status": "found", element: specs[element]}
    elif element:
        return {"status": "not_found", "available": list(specs.keys())}
    return {"status": "overview", **specs}
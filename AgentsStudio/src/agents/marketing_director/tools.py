"""Tools for the Marketing Image Generation Director.

Generates original, on-brand marketing visuals and copy using Atelier Zero v7
and the Carrara marble head concept. Every marble head is a fresh creation
unless the user names a specific character (Leo, Miles, Marc, Ray).
Reference images (Krea reference board, marble bust sheets/cutouts, and approved logos)
are loaded automatically and passed to Nano Banana 2 so visual prompts do not rely
on raw hex strings.
"""

import asyncio
import os
import time
from typing import Optional

from google.adk import Context
from google import genai
from google.genai import types as genai_types

from ..shared.rag import (
    MARKETING_BRAND_RAG_CORPUS,
    create_marketing_brand_rag_tool,
    retrieve_rag_sync,
)
from ..shared.references import select_marketing_references


# ── Brand Color Constants (for get_brand_spec lookup) ─────────────────────

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
    "human-hair men's hair system with individually visible strands and a natural "
    "graduated front hairline meeting the stone. Sharp focus, 8k detail, professional "
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


def _resolve_character(face_description: str) -> tuple[str, str]:
    """Return (resolved_face_description, matched_character_key)."""
    name_lower = face_description.strip().lower()
    for key in KNOWN_CHARACTERS:
        if name_lower == key or name_lower.startswith(f"{key} ") or f" {key} " in f" {name_lower} ":
            face = KNOWN_CHARACTERS[key] + (f" {MILES_IDENTITY}" if key == "miles" else "")
            if len(face_description.strip()) > len(key):
                face = f"{face}. Additional styling: {face_description}"
            return face, key
    return face_description, ""


# ── Prompt builders (hex-free; visual references carry the palette) ──────

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
    """Build an editorial collage prompt in the Krea marble style (no raw hex strings)."""
    comp = ""
    if composition_hint:
        comp = f" Composition direction: {composition_hint}."

    return (
        f"Using the attached Krea reference board for exact paper palette, film grain, "
        f"disc textures, and layered collage aesthetic, create a numbered editorial "
        f"collage poster, vertical 4:5 aspect ratio. "
        f"The ground is aged warm paper with subtle film-grain texture. "
        f"A large textured warm coral sun disc sits prominently behind the subject, "
        f"partially obscured. A smaller muted mustard ochre accent disc adds depth. "
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
        f"look — NOT a bright corporate palette. The coral sun disc is prominent even when "
        f"partly hidden. Photorealistic, 8K, editorial print quality. "
        f"\n\nNEGATIVE: human skin, skin tone, flesh tones, eyes with pupils, painted face, "
        f"glossy plastic, shiny surface, wig cap, lace edge, clothing, jewelry, cartoon, "
        f"bright saturated corporate colors, museum product photography, text-heavy layout, "
        f"marketing copy in the image body, hex codes, synthetic hair, helmet hair, plastic hair."
    )


def build_social_prompt(
    face_description: str,
    platform: str = "feed",
    campaign: str = "",
    composition_hint: str = "",
) -> str:
    """Build a platform-specific social media image prompt (no raw hex strings)."""
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
            "Dark charcoal ink ground, premium atmosphere. Dramatic single key light "
            "carving the facial features from deep shadow. A single warm coral accent "
            "element reserved in negative space. Editorial urgency, never desperate. "
        )
    elif campaign == "product_launch":
        campaign_prompt = (
            "Clean gallery-style composition with generous negative space on warm aged paper. "
            "Soft diffused daylight. Airy, minimal, contemporary. "
        )
    elif campaign == "editorial":
        campaign_prompt = (
            "Layered, art-directed composition on warm aged paper. Dramatic lighting. "
            "Museum-grade atmosphere. "
        )

    comp = ""
    if composition_hint:
        comp = f" Additional direction: {composition_hint}."

    return (
        f"A photorealistic social media image, {dim}, for Hair Solutions Co. "
        f"{campaign_prompt}"
        f"The main subject is a classical Carrara marble bust matching the attached "
        f"stone material reference. "
        f"{MARBLE_DNA} The bust depicts {face_description}. "
        f"Background: warm aged paper tone with subtle film grain texture. "
        f"Atelier Zero v7 brand aesthetic — warm, editorial, calm, never corporate. "
        f"No text on the image (overlays are added in design software). "
        f"Corner registration marks: 1px L-shaped brackets in deep ink at opposing corners. "
        f"{comp}"
        f"Photorealistic, 8K. "
        f"NEGATIVE: {MARBLE_NEGATIVE} text on the image, hex codes, gradients, glows, "
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
    logo_variant: str = "",
    tool_context: Optional[Context] = None,
) -> dict:
    """Generate a portrait of a unique Carrara marble head with hyper-realistic human hair.

    This is the primary tool for marble head imagery. Every call creates a NEW face
    based on your description — age, ethnicity, bone structure, expression, hair —
    unless the user explicitly names Leo, Miles, Marc, or Ray.

    Args:
        face_description: Full description of the marble bust's face. Include age,
            ethnicity, bone structure, facial features, expression, hair color, hair style.
        lighting: gallery (soft diffused), authority (dramatic single key on dark),
                  golden (warm directional sunlight), editorial (high contrast museum).
        pose: Optional. E.g. "front-facing", "three-quarter left", "profile",
              "chin raised, proud", "downcast, contemplative".
        composition: Optional creative direction for framing, crop, negative space.
        logo_variant: Optional approved logo reference ("wordmark-dark-on-light",
              "wordmark-light-on-dark", "monogram-dark-on-light", etc.).

    Returns:
        Dict with image path, reference assets used, and generation metadata.
    """
    face, char_key = _resolve_character(face_description)
    ref_parts, ref_meta = select_marketing_references(
        mode="marble",
        character_name=char_key,
        logo_variant=logo_variant,
    )

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

    ref_note = (
        f"Match the exact sculpted facial identity of {char_key.title()} in the attached character sheets. "
        if char_key
        else "Use the attached reference for Carrara marble stone veining, blank carved eyes, and fractured plinth material only — sculpt a completely NEW, unique male face matching the description. "
    )
    prompt = f"{ref_note}{MARBLE_DNA} The bust depicts {face}. {' '.join(extra)} {MARBLE_NEGATIVE}"

    try:
        client = genai.Client()
        parts = list(ref_parts) + [genai_types.Part.from_text(text=prompt)]
        response = client.models.generate_content(
            model="gemini-3.1-flash-image",
            contents=genai_types.Content(role="user", parts=parts),
            config=genai_types.GenerateContentConfig(response_modalities=["IMAGE", "TEXT"]),
        )
        path = _save_image(response, "marble_head")
        return {
            "status": "generated",
            "image_path": path,
            "face": face_description[:100],
            "character": char_key or "unique",
            "lighting": lighting,
            "reference_assets": ref_meta,
            "message": f"Marble head generated ({len(ref_meta)} reference image(s) attached). Saved to {path}",
        }
    except Exception as e:
        return {"status": "error", "error": str(e)}


def generate_editorial_collage(
    face_description: str,
    series_number: int = 1,
    composition: str = "",
    logo_variant: str = "",
    tool_context: Optional[Context] = None,
) -> dict:
    """Generate a numbered editorial collage poster in the Krea marble style.

    Automatically attaches the Krea REFERENCE_BOARD.png and matching marble reference
    images so the palette (Aged Paper ground, Coral sun disc, Mustard accent, Ink details)
    comes directly from the visual reference without raw hex codes in the prompt.

    Args:
        face_description: Description of the marble bust's face — age, ethnicity,
            features, hair. The agent invents a NEW face each time unless a known
            character (Leo, Miles, Marc, Ray) is named.
        series_number: Sequential poster number for the editorial series (1-99).
        composition: Optional creative direction for collage layout, disc placement,
            wedge angle, lighting mood.
        logo_variant: Optional approved logo reference to include.

    Returns:
        Dict with image path, reference assets used, and generation metadata.
    """
    face, char_key = _resolve_character(face_description)
    ref_parts, ref_meta = select_marketing_references(
        mode="collage",
        character_name=char_key,
        logo_variant=logo_variant,
    )

    prompt = build_collage_prompt(face, series_number, composition)

    try:
        client = genai.Client()
        parts = list(ref_parts) + [genai_types.Part.from_text(text=prompt)]
        response = client.models.generate_content(
            model="gemini-3.1-flash-image",
            contents=genai_types.Content(role="user", parts=parts),
            config=genai_types.GenerateContentConfig(response_modalities=["IMAGE", "TEXT"]),
        )
        path = _save_image(response, f"collage_no{series_number:02d}")
        return {
            "status": "generated",
            "image_path": path,
            "series_number": series_number,
            "character": char_key or "unique",
            "reference_assets": ref_meta,
            "message": (
                f"Editorial collage No.{series_number:02d} generated with Krea reference board "
                f"({len(ref_meta)} reference asset(s)). Saved to {path}"
            ),
        }
    except Exception as e:
        return {"status": "error", "error": str(e)}


def generate_social_asset(
    face_description: str,
    platform: str = "feed",
    campaign: str = "",
    composition: str = "",
    logo_variant: str = "",
    tool_context: Optional[Context] = None,
) -> dict:
    """Generate a platform-specific social media image.

    Args:
        face_description: Description of the marble bust's face.
        platform: feed (1:1), story (9:16), reel (9:16), carousel (4:5).
        campaign: general, black_friday, product_launch, editorial.
        composition: Optional creative direction.
        logo_variant: Optional approved logo reference to attach.

    Returns:
        Dict with image path, reference assets used, and generation metadata.
    """
    face, char_key = _resolve_character(face_description)
    mode = "collage" if campaign == "editorial" else "social"
    ref_parts, ref_meta = select_marketing_references(
        mode=mode,
        character_name=char_key,
        logo_variant=logo_variant,
    )

    prompt = build_social_prompt(face, platform, campaign, composition)

    try:
        client = genai.Client()
        parts = list(ref_parts) + [genai_types.Part.from_text(text=prompt)]
        response = client.models.generate_content(
            model="gemini-3.1-flash-image",
            contents=genai_types.Content(role="user", parts=parts),
            config=genai_types.GenerateContentConfig(response_modalities=["IMAGE", "TEXT"]),
        )
        path = _save_image(response, f"social_{platform}_{campaign or 'general'}")
        return {
            "status": "generated",
            "image_path": path,
            "platform": platform,
            "campaign": campaign or "general",
            "character": char_key or "unique",
            "reference_assets": ref_meta,
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
    logo_variant: str = "",
    tool_context: Optional[Context] = None,
) -> dict:
    """Generate a general campaign/marketing visual following Atelier Zero v7 rules.

    Args:
        description: What the image should depict, the concept, the mood.
        campaign_type: general, black_friday, product_launch, instagram, email.
        use_marble_head: If True, includes a marble head as the subject.
        face_description: If use_marble_head is True, describe the face.
        composition: Optional creative direction.
        logo_variant: Optional approved logo variant to attach.

    Returns:
        Dict with image path, reference assets used, and generation metadata.
    """
    brand_rules = (
        "Brand system: Atelier Zero v7. Warm aged paper canvas, warm bone raised surfaces, "
        "deep charcoal ink ground, and a single warm coral spot accent used sparingly. "
        "Film grain on all backgrounds. No gradients, no glows, no shadows on light surfaces. "
        "One dark ink section max per composition. Warm editorial print aesthetic. "
    )

    if campaign_type == "black_friday":
        brand_rules += (
            "Campaign exception: Coral-forward. Dark, premium atmosphere. "
            "Editorial urgency allowed but never desperate. "
            "Dramatic single key light, deep shadows. "
        )
    elif campaign_type == "product_launch":
        brand_rules += "Clean, gallery-style. Generous negative space. Airy, minimal. "

    char_key = ""
    subject = ""
    if use_marble_head:
        if face_description:
            face, char_key = _resolve_character(face_description)
        else:
            face = "a unique, never-before-seen male face appropriate to the creative direction"
        subject = (
            f"Subject: A classical Carrara marble bust with blank carved eyes, "
            f"fractured shoulder truncation, hyper-realistic human hair with individual "
            f"strands and natural graduated hairline. The bust depicts {face}. "
        )

    ref_parts, ref_meta = select_marketing_references(
        mode="campaign" if use_marble_head else "none",
        character_name=char_key,
        logo_variant=logo_variant,
    )

    comp = ""
    if composition:
        comp = f" Composition: {composition}."

    prompt = (
        f"A photorealistic marketing image for Hair Solutions Co. {brand_rules}"
        f"{subject}"
        f"Creative direction: {description}.{comp} "
        f"Photorealistic, 8K, editorial quality. No text on the image. "
        f"NEGATIVE: {MARBLE_NEGATIVE} gradients, glows, corporate stock photo, "
        f"bright saturated palette, cartoon, illustration, text overlay, hex codes, watermark."
    )

    try:
        client = genai.Client()
        parts = list(ref_parts) + [genai_types.Part.from_text(text=prompt)]
        response = client.models.generate_content(
            model="gemini-3.1-flash-image",
            contents=genai_types.Content(role="user", parts=parts),
            config=genai_types.GenerateContentConfig(response_modalities=["IMAGE", "TEXT"]),
        )
        path = _save_image(response, f"campaign_{campaign_type}")
        return {
            "status": "generated",
            "image_path": path,
            "campaign_type": campaign_type,
            "character": char_key or ("unique" if use_marble_head else "none"),
            "reference_assets": ref_meta,
            "message": f"Campaign visual generated: {campaign_type}. Saved to {path}",
        }
    except Exception as e:
        return {"status": "error", "error": str(e)}


def write_marketing_copy(
    brief: str,
    copy_type: str = "email",
    campaign: str = "general",
    tool_context: Optional[Context] = None,
) -> dict:
    """Write on-brand Hair Solutions Co. marketing copy using the Gemini 3.5 Flash copywriter
    grounded in the Tier 1 ``marketing-brand`` RAG corpus.

    Use this tool whenever the user asks for email copy (subject line, preheader, body),
    website section copy, product descriptions, or social captions.

    Args:
        brief: What the copy should communicate (product, audience, angle).
        copy_type: "email", "web_section", "social_caption", "headline", or "ad_copy".
        campaign: Campaign context (e.g. "general", "rebrand_launch", "black_friday", "product_launch").

    Returns:
        Dict with the generated copy, RAG sources consulted, and compliance check.
    """
    try:
        contexts = retrieve_rag_sync(
            MARKETING_BRAND_RAG_CORPUS,
            f"{brief} {copy_type} {campaign}",
            similarity_top_k=5,
        )
    except Exception:
        contexts = []
    context_text = "\n\n".join(
        f"[Source: {c.get('source_uri', '')}]\n{c.get('text', '')}" for c in contexts
    )

    system_prompt = (
        "You are the Hair Solutions Co. Copywriter (Atelier Zero v7).\n"
        "Write calm, direct, educational, specific copy in sentence case.\n"
        "Use Playfair Display italic switches (*italic*) for emphasis — never bold-inside-bold or ALL CAPS hype.\n"
        "Display headlines end with a period.\n"
        "NEVER use exclamation marks (!), emojis, or banned wording: "
        "'undetectable', '100% natural', 'guaranteed', 'perfect', 'medical grade', "
        "'hypoallergenic', 'dermatologist tested', 'clinically tested', 'safe for sensitive skin', "
        "'non-irritating', 'wig', 'toupee', 'hairpiece', 'OneHead', or 'LordHair'.\n"
        "Say 'looks natural when fitted well' instead of 'undetectable'.\n"
        "Ground all product specs, prices (USD only), lifespans, and storefront facts strictly in the retrieved Tier 1 context below.\n\n"
        f"TIER 1 APPROVED CONTEXT:\n{context_text}"
    )

    user_prompt = (
        f"Copy type: {copy_type}\n"
        f"Campaign: {campaign}\n"
        f"Brief: {brief}\n\n"
        "Write the requested copy now."
    )

    try:
        client = genai.Client()
        resp = client.models.generate_content(
            model="gemini-3.5-flash",
            contents=user_prompt,
            config=genai_types.GenerateContentConfig(
                system_instruction=system_prompt,
                thinking_config=genai_types.ThinkingConfig(thinking_level="MINIMAL"),
            ),
        )
        copy_out = (resp.text or "").strip().replace("!", ".")
        return {
            "status": "generated",
            "copy_type": copy_type,
            "campaign": campaign,
            "model": "gemini-3.5-flash",
            "rag_sources": [c.get("source_uri", "") for c in contexts],
            "copy": copy_out,
        }
    except Exception as e:
        return {"status": "error", "error": str(e)}


def get_brand_spec(
    element: str = "",
    tool_context: Optional[Context] = None,
) -> dict:
    """Look up Atelier Zero brand specifications from ascensio-digital-solutions/brand-design-system.

    Args:
        element: What to look up — "colors", "typography", "marble_concept",
                 "composition", "collage_language", "voice", "social", "email",
                 "avatars", "logos", or empty for overview.
    """
    specs = {
        "authority_repo": "/Users/vincent/06_code/brand-design-system (github.com/ascensio-digital-solutions/brand-design-system)",
        "colors": {
            "primitives": {
                "paper": PAPER,
                "paper-warm": "#ECE4CF",
                "paper-dark": "#DDD2B6",
                "bone": BONE,
                "ink": INK,
                "ink-soft": "#2A2620",
                "ink-mute": "#5A5448",
                "ink-faint": "#8B8676",
                "coral": CORAL,
                "coral-soft": CORAL_SOFT,
                "mustard": MUSTARD,
                "olive": OLIVE,
            },
            "modes": ["Paper (default)", "Warm", "Deep", "Ink (dark)"],
            "coral_rules": (
                "Primary action and recognition signal (<10% of composition). "
                "Primary CTA is always a Coral (#FF5757) pill with Ink (#15140F) text on both light and dark surfaces (Coral never inverts on dark). "
                "Never use Coral body text on Paper (2.52:1 fails contrast). Never more than one Coral CTA per decision area."
            ),
            "mustard_and_olive": "Mustard (#E9B94A) is strictly focus outer ring and caution (plus the Krea collage disc in marble editorial art). Olive (#6E7448) is utility/success.",
        },
        "typography": {
            "display": "Inter Tight 96→46px, weight 800, line-height 94.08→45.08px, tracking -2.88→-1.38px",
            "headings": "Inter Tight H1 72→38px (800) · H2 48→30px (800) · H3 28→22px (700) · H4 19px (700)",
            "body": "Inter Lead 19→16px (400) · Body 16px/25.6px (400)",
            "eyebrow": "Inter Tight 12px/16.8px (600, UPPERCASE, tracking +2.64px)",
            "emphasis": "Playfair Display 500 italic — ONLY one inline phrase inside H1/H2 (<em>), pull-quote emphasis (Coral Soft on Ink), Serif Note (22px), or Price (26px). Never a full serif heading.",
            "metadata": "JetBrains Mono 11px/16.5px (600, tracking +0.88px)",
            "buttons": "Inter Tight 15px (regular) / 13px (small), weight 600, tracking +0.3px",
        },
        "marble_concept": {
            "material": "White Carrara marble, grey veining, subsurface translucency, matte fractured shoulder edge",
            "eyes": "Softly carved blank — NO pupils, NO eyelashes, NO human expression through eyes",
            "hair": "Hyper-realistic human hair, individual strands visible, natural irregular hairline where it meets the stone. The ONLY living material.",
            "never": "Human skin, flesh tones, painted faces, glossy plastic, wig caps, lace edges, clothing, jewelry",
            "known_characters": "Leo (26), Miles (34, Black), Marc (42), Ray (63) — only use when explicitly named",
        },
        "composition": {
            "container": "1480px max-width (1440px Figma canvas with 96px desktop / 24px mobile gutter). Section vertical gap: 96px desktop / 72px mobile.",
            "radius": "none 0px · field-multiline 4px · inset 8px · option 12px · nested 16px · card 20px · plate 24px · pill 999px",
            "elevation": "Raised cards use Bone (#F7F1DE), 20px radius, 1px hairline (ink @ 16%), and shadow/card (0 30px 60px -30px rgba(21,20,15,0.18)). Nested small surfaces (12px) are flat.",
            "dark_sections": "Single dark ground: Ink (#15140F). Surrounded by light sections — never two dark sections adjacent.",
            "film_grain": "Documented paper grain (--az-grain) on Paper surfaces. No decorative gradients or glows.",
        },
        "collage_language": {
            "ground": "Aged Paper ground with film grain (loaded via Krea REFERENCE_BOARD.png)",
            "coral_disc": "Prominent textured Coral sun disc partly behind the bust",
            "mustard_disc": "Smaller Mustard accent disc for depth",
            "elements": "Graphite cloud engravings, fine orbital pencil lines, sparse halftone dots",
            "wedge": "Cracked-concrete torn-paper wedge crossing a lower corner",
            "numbering": "Small sequential No.01, No.02... near upper right in clean serif",
            "mood": "Warm, weathered, layered editorial — never bright corporate",
        },
        "social": {
            "governing_principles": [
                "1. One idea per asset (no combo posts).",
                "2. The product, the person, or the message — never all three in one frame.",
                "3. Restraint scales (max one headline + one short supporting line per static frame).",
            ],
            "canvases": {
                "feed_square": "1080×1080 (160px inset)",
                "feed_portrait": "1080×1350 (160px top/bottom, 80px sides)",
                "story": "1080×1920 (safe zone: 250px top, 340px bottom)",
                "reel": "1080×1920 (safe zone: 285px top, 440px bottom, 160px right)",
            },
            "grid_rule": "9-Tile Grid Rule: no two Ink (full-dark) tiles touch; balance Paper/Bone hero moments, product moments, and human/lifestyle moments.",
        },
        "email": {
            "layout": "600px single-column flush stack inside EmailFrame (zero gap between blocks; separate adjacent blocks by changing surface).",
            "surfaces": "Main surfaces: Paper (#EFE7D2), Bone (#F7F1DE), Ink (#15140F), or White (#FFFFFF in email/ React package only). Bone and Paper never touch directly — separate with Ink.",
            "order": "frame (Preheader/Header) → opener (HeroTextLed / HeroMarble / HeroPhotoLed) → letter → substance → proof → ask (single Coral ActionMainAsk button) → footer.",
            "wordmark": "Letterforms in Ink (#15140F) on light or Bone (#F7F1DE) on Ink; the 'co' suffix is always Coral (#FF5757). Never place wordmark on Coral.",
        },
        "avatars": {
            "Daniel (first-timer)": "Research-heavy, discreet, cautious. Needs education before commerce, honest comparison, low-pressure support.",
            "Marcus (experienced wearer)": "Spec-literate, price-aware, impatient with vagueness. Talk shop with materials, measurements, and mechanisms.",
            "Ryan (active professional)": "Lifestyle-led, pragmatic, reliability-focused. Lead with routine simplicity for work, travel, exercise, heat, water.",
        },
        "logos": {
            "masterfile_approved": "/Users/vincent/01_hair_solutions_co/design/brand/logos/masterfile-approved/ (7 hash-verified files in manifests/logos.json)",
            "v5_trimmed": "/Users/vincent/06_code/brand-design-system/atelier_zero_design_system_artifact/project/assets/Logos/ (wordmark-ink.png, wordmark-bone.png, monogram-ink.png, monogram-bone.png)",
        },
        "voice": {
            "promise": "Regain your hair—and yourself.",
            "relationship": "'We' as the informed studio speaking to 'you' as an adult decision-maker. Relief, not rescue.",
            "tone": "Calm, direct, educational, specific. Sentence case. Explain the tradeoff and give one clear next step.",
            "never": "Pity, shame, rescue language, urgency, scarcity, hype, medical framing, emoji, exclamation marks (!), 'wig'/'toupee'/'hairpiece', or unverified claims.",
        },
    }

    if element and element in specs:
        return {"status": "found", element: specs[element]}
    elif element:
        return {"status": "not_found", "available": list(specs.keys())}
    return {"status": "overview", **specs}

from enum import Enum
from typing import List, Optional
from pydantic import BaseModel, Field

class CaptureType(str, Enum):
    camera_photo = "camera_photo"
    screenshot = "screenshot"
    screen_recording = "screen_recording"
    downloaded_image = "downloaded_image"
    meme = "meme"
    scanned_document = "scanned_document"
    graphic_design = "graphic_design"
    ai_generated = "ai_generated"
    unknown = "unknown"

class Domain(str, Enum):
    personal = "personal"
    business = "business"
    knowledge = "knowledge"

class Category(str, Enum):
    # ── PILLAR 1: PERSONAL LIFE & MEMORIES ──
    people = "personal/people"
    events = "personal/events"
    travel = "personal/travel"
    nature = "personal/nature"
    food = "personal/food"
    pets_animals = "personal/pets_animals"
    home_daily = "personal/home_daily"
    sports_hobbies = "personal/sports_hobbies"
    personal_health = "personal/health_medical"
    personal_bills = "personal/bills_receipts"
    personal_other = "personal/other"
    
    # Personal Noise & Review
    screenshots_grindr = "personal/screenshots/grindr"
    screenshots_whatsapp = "personal/screenshots/whatsapp"
    screenshots_shopping = "personal/screenshots/shopping"
    screenshots_personal = "personal/screenshots/other"
    accidental_blurry = "personal/rejects/accidental_blurry"
    memes_downloads = "personal/rejects/memes_downloads"
    
    # Private Quarantine
    intimate = "06_private_quarantine/intimate"
    identity_documents = "06_private_quarantine/identity_documents"
    
    # ── PILLAR 2: CORE BUSINESS OPERATIONS (Hair Solutions Co. & Ascensio) ──
    products = "business/01_products"
    specs = "business/02_specs"
    business_people = "business/03_people"
    lifestyle = "business/04_lifestyle"
    education = "business/05_education"
    web = "business/06_web"
    brand = "business/07_brand"
    marketing = "business/08_marketing"
    reference = "business/09_reference"
    shopify = "business/shopify"
    operations = "business/operations"
    
    # ── PILLAR 3: KNOWLEDGE & SWIPE FILE ──
    knowledge_ai = "knowledge/ai_and_automation"
    knowledge_design = "knowledge/design_and_branding"
    knowledge_ui = "knowledge/ui_and_web_design"
    knowledge_marketing = "knowledge/marketing_and_growth"
    knowledge_code = "knowledge/development_and_code"
    
    needs_review = "00_needs_human_review"

class BusinessEvidence(str, Enum):
    hair_system_visible = "hair_system_visible"
    swatch = "swatch"
    product_packaging = "product_packaging"
    shopify_ui = "shopify_ui"
    supplier_chat = "supplier_chat"
    before_after_context = "before_after_context"

class Sensitivity(str, Enum):
    none = "none"
    intimate = "intimate"
    identity_document = "identity_document"
    financial_document = "financial_document"

class Quality(str, Enum):
    keeper = "keeper"
    ok = "ok"
    weak = "weak"
    reject = "reject"

class ClassificationResult(BaseModel):
    capture_type: CaptureType = Field(description="The type of capture")
    domain: Domain = Field(description="Strict 3 pillars: 'personal', 'business', or 'knowledge' (Swipe File). Never ambiguous!")
    category: Optional[Category] = Field(description="The assigned folder category based on 3-pillar taxonomy")
    app_name: Optional[str] = Field(default=None, description="If a screenshot or app capture, the detected app (e.g. Grindr, WhatsApp, Instagram, Facebook, Amazon, eBay, Shopify, Claude, etc.)")
    creator_handle: Optional[str] = Field(default=None, description="If a social media post/reel/story screenshot (e.g. Instagram, X, TikTok), the visible creator @handle or page name")
    subject_or_tool_discussed: Optional[str] = Field(default=None, description="If a screenshot or slide discussing an app, AI tool, software, or topic, name the specific tool/subject (e.g. 'Claude + Metricool', 'Shopify CRO')")
    is_shopping: bool = Field(default=False, description="True if this is an online shopping item, product listing, e-commerce store, cart, or price tag (e.g. Amazon, eBay, retail shop)")
    business_evidence: Optional[List[BusinessEvidence]] = Field(default=None, description="Visual evidence for business classification, if domain is business")
    hairline_presentation: Optional[str] = Field(default=None, description="If domain is business (hair system): 'clearlyVisible', 'partiallyVisible', 'notVisible', or 'unclear'")
    business_quality: Optional[str] = Field(default=None, description="If domain is business: 'strong', 'usable', 'weak', or 'needsReview'")
    photo_role: Optional[str] = Field(default=None, description="If domain is business: 'beforeCandidate', 'afterCandidate', 'comparisonCandidate', 'other', or 'unclear'")
    sensitivity: Sensitivity = Field(description="Is the content sensitive?")
    quality: Quality = Field(description="The quality of the image")
    quality_issues: Optional[List[str]] = Field(default=None, description="Issues like blurry, dark, accidental")
    tags: List[str] = Field(default=[], description="Up to 8 lowercase tags using Framebase namespace:value slugs where applicable (e.g. app:instagram, tool:claude, tool:metricool, channel:instagram, product:hair-system, status:review, topic:automation)")
    has_vincent: Optional[bool] = Field(default=False, description="True ONLY if Vincent's real human face/body is a primary subject of the photo (portrait, selfie, group shot). MUST be False for tiny 20px app navigation avatars or story bubbles!")
    confidence: float = Field(description="Confidence score from 0.0 to 1.0")
    rationale: str = Field(description="A brief explanation (<=240 chars) of the classification, including creator/tool if screenshot")

def get_final_category(result: ClassificationResult, year: Optional[int] = None) -> Category:
    """Apply strict rules to determine the final category under the 3 pillars."""
    if result.sensitivity == Sensitivity.intimate:
        return Category.intimate
    
    if result.sensitivity == Sensitivity.identity_document:
        return Category.identity_documents

    if result.quality == Quality.reject or (result.quality_issues and "accidental" in result.quality_issues):
        return Category.accidental_blurry

    # Pillar 2: Business
    if result.domain == Domain.business:
        if result.category == Category.shopify or (result.app_name and "shopify" in result.app_name.lower()):
            return Category.shopify
        if result.category in (Category.products, Category.specs, Category.business_people, Category.operations):
            return result.category
        if result.business_evidence:
            return Category.products
        return Category.operations

    # Pillar 3: Knowledge (Swipe File)
    if result.domain == Domain.knowledge:
        tags_str = " ".join(result.tags).lower()
        tool = (result.subject_or_tool_discussed or "").lower()
        full_text = f"{tags_str} {tool} {result.rationale.lower()}"
        if any(k in full_text for k in ["ai", "claude", "prompt", "agent", "llm", "automation", "n8n", "chatgpt"]):
            return Category.knowledge_ai
        if any(k in full_text for k in ["ui", "ux", "landing", "web design", "website", "hero"]):
            return Category.knowledge_ui
        if any(k in full_text for k in ["typography", "font", "palette", "pantone", "color", "graphic", "branding", "logo"]):
            return Category.knowledge_design
        if any(k in full_text for k in ["marketing", "growth", "copy", "hook", "carousel", "ad", "startup"]):
            return Category.knowledge_marketing
        if any(k in full_text for k in ["code", "developer", "python", "swift", "github", "git", "api"]):
            return Category.knowledge_code
        return Category.knowledge_ai

    # Pillar 1: Personal
    if result.capture_type == CaptureType.screenshot:
        if result.category in (
            Category.screenshots_grindr,
            Category.screenshots_whatsapp,
            Category.screenshots_shopping,
        ):
            return result.category
        return Category.screenshots_personal
        
    if result.capture_type in (CaptureType.meme, CaptureType.downloaded_image):
        return Category.memes_downloads

    # Try mapping to enum directly if present
    try:
        return Category(result.category)
    except (ValueError, TypeError):
        return Category.personal_other

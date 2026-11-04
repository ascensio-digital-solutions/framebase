from enum import Enum
from typing import List, Literal, Optional
from pydantic import BaseModel, Field, model_validator


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
    hair_solutions_co = "hair_solutions_co"
    knowledge_and_tools = "knowledge_and_tools"


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


class KnowledgeOpportunity(BaseModel):
    is_actionable_repo_or_tool: bool = Field(
        default=False,
        description="True if this screenshot features an actionable software tool, open-source GitHub repo, CRM workflow, or AI agent architecture",
    )
    tool_or_repo_name: Optional[str] = Field(
        default=None,
        description="Specific name of the software tool, library, or GitHub repository (e.g. 'Attio CRM', 'HubSpot Workflows', 'n8n', 'DeepSeek-V4')",
    )
    github_or_url: Optional[str] = Field(
        default=None,
        description="Visible or canonical GitHub repo path or website URL if identifiable (e.g. 'https://github.com/...', 'hubspot.com')",
    )
    license_type: Literal["open_source_free", "freemium", "paid", "unknown"] = Field(
        default="unknown",
        description="License or pricing model of the tool/repo",
    )
    category_subfolder: Literal[
        "open-source-repos",
        "crm-and-sales",
        "ai-agents-and-workflows",
        "ui-ux-and-web",
        "marketing-and-copy",
        "general-reference",
    ] = Field(
        default="general-reference",
        description="Target knowledge subfolder based on primary utility",
    )
    why_relevant_to_vincent: Optional[str] = Field(
        default=None,
        description="1-sentence summary of why Vincent would care (e.g., e-commerce/CRM pipeline automation for Hair Solutions Co., open-source AI agent tool, etc.)",
    )


class PhotoClassification(BaseModel):
    capture_type: CaptureType = Field(
        default=CaptureType.camera_photo,
        description="The type of capture",
    )
    domain: Domain = Field(
        description="Strict 3 pillars: 'personal', 'hair_solutions_co' (or 'business'), or 'knowledge_and_tools' (or 'knowledge'). Never ambiguous!"
    )
    category: Optional[Category] = Field(
        default=None,
        description="The assigned folder category based on 3-pillar taxonomy",
    )
    privacy_flag: Literal["safe", "intimate", "identity_document", "financial_document"] = Field(
        default="safe",
        description="Privacy gatekeeper flag: 'safe', 'intimate', 'identity_document', or 'financial_document'",
    )
    subject_count: Literal["none", "single_person", "multiple_people"] = Field(
        default="none",
        description="Number of visible human subjects in the photo: 'none', 'single_person', or 'multiple_people'",
    )
    model_shot_type: Literal[
        "before_bald_thinning",
        "before_after_split",
        "headshot_hairline",
        "editorial_lifestyle",
        "install_cut_in",
        "not_model",
    ] = Field(
        default="not_model",
        description="For solo hair system model photos: specific shot classification. Must be 'not_model' if not demonstrating hair replacement or if multiple people.",
    )
    hair_color_family: Literal[
        "black",
        "dark_brown",
        "medium_brown",
        "light_brown",
        "blonde",
        "red_auburn",
        "grey_silver",
        "grey_blend",
        "multiple_swatches",
        "not_applicable",
    ] = Field(
        default="not_applicable",
        description="Dominant hair color family if hair system, model, or swatch is visible",
    )
    hair_color_code: Optional[str] = Field(
        default=None,
        description="Standard hair system color code if visible or identifiable (e.g., '#1B', '#22', '#1B20')",
    )
    swatch_sub_type: Literal[
        "circle-swatches",
        "ring-swatches",
        "color-charts",
        "grey-percentage",
        "curl-pattern",
        "base-material",
        "none",
    ] = Field(
        default="none",
        description="If a spec/swatch image, the specific swatch sub-type",
    )
    knowledge_opportunity: Optional[KnowledgeOpportunity] = Field(
        default=None,
        description="Populated for screenshots/knowledge items to extract actionable repos, tools, CRMs, or workflows",
    )
    app_name: Optional[str] = Field(
        default=None,
        description="If a screenshot or app capture, the detected app (e.g. Grindr, WhatsApp, Instagram, Facebook, Amazon, eBay, Shopify, HubSpot, Claude, etc.)",
    )
    creator_handle: Optional[str] = Field(
        default=None,
        description="If a social media post/reel/story screenshot (e.g. Instagram, X, TikTok), the visible creator @handle or page name",
    )
    subject_or_tool_discussed: Optional[str] = Field(
        default=None,
        description="If a screenshot or slide discussing an app, AI tool, software, or topic, name the specific tool/subject (e.g. 'Claude + Metricool', 'Shopify CRO')",
    )
    is_shopping: bool = Field(
        default=False,
        description="True if this is an online shopping item, product listing, e-commerce store, cart, or price tag (e.g. Amazon, eBay, retail shop)",
    )
    business_evidence: Optional[List[BusinessEvidence]] = Field(
        default=None,
        description="Visual evidence for business classification, if domain is business/hair_solutions_co",
    )
    hairline_presentation: Optional[str] = Field(
        default=None,
        description="If domain is business/hair_solutions_co (hair system): 'clearlyVisible', 'partiallyVisible', 'notVisible', or 'unclear'",
    )
    business_quality: Optional[str] = Field(
        default=None,
        description="If domain is business/hair_solutions_co: 'strong', 'usable', 'weak', or 'needsReview'",
    )
    photo_role: Optional[str] = Field(
        default=None,
        description="If domain is business/hair_solutions_co: 'beforeCandidate', 'afterCandidate', 'comparisonCandidate', 'other', or 'unclear'",
    )
    sensitivity: Sensitivity = Field(
        default=Sensitivity.none,
        description="Is the content sensitive?",
    )
    quality: Quality = Field(
        default=Quality.ok,
        description="The quality of the image",
    )
    quality_issues: Optional[List[str]] = Field(
        default=None,
        description="Issues like blurry, dark, accidental",
    )
    tags: List[str] = Field(
        default_factory=list,
        description="Up to 8 lowercase tags using Framebase namespace:value slugs where applicable (e.g. app:instagram, tool:claude, product:hair-system, base:swiss-lace, hairline:clearly-visible)",
    )
    has_vincent: Optional[bool] = Field(
        default=False,
        description="True ONLY if Vincent's real human face/body is a primary subject of the photo (portrait, selfie, group shot). MUST be False for tiny 20px app navigation avatars or story bubbles!",
    )
    confidence: float = Field(
        default=0.9,
        description="Confidence score from 0.0 to 1.0",
    )
    rationale: str = Field(
        default="",
        description="A brief explanation (<=240 chars) of the classification, including creator/tool if screenshot",
    )

    @model_validator(mode="after")
    def sync_privacy_and_sensitivity(self) -> "PhotoClassification":
        if self.sensitivity == Sensitivity.intimate and self.privacy_flag == "safe":
            self.privacy_flag = "intimate"
        elif self.sensitivity == Sensitivity.identity_document and self.privacy_flag == "safe":
            self.privacy_flag = "identity_document"
        elif self.sensitivity == Sensitivity.financial_document and self.privacy_flag == "safe":
            self.privacy_flag = "financial_document"

        if self.privacy_flag == "intimate" and self.sensitivity == Sensitivity.none:
            self.sensitivity = Sensitivity.intimate
        elif self.privacy_flag == "identity_document" and self.sensitivity == Sensitivity.none:
            self.sensitivity = Sensitivity.identity_document
        elif self.privacy_flag == "financial_document" and self.sensitivity == Sensitivity.none:
            self.sensitivity = Sensitivity.financial_document
        return self


# Backward compatibility alias for existing scripts
ClassificationResult = PhotoClassification


def requires_gemini_review(result: ClassificationResult) -> bool:
    """Legacy helper determining if a local classification needs Gemini review."""
    if result.confidence < 0.85:
        return True
    if result.domain in (Domain.business, Domain.hair_solutions_co, Domain.knowledge, Domain.knowledge_and_tools):
        return True
    if result.sensitivity != Sensitivity.none or result.privacy_flag != "safe":
        return True
    return False


def get_final_category(result: ClassificationResult, year: Optional[int] = None) -> Category:
    """Apply strict rules to determine the final category under the 3 pillars."""
    if result.sensitivity == Sensitivity.intimate or result.privacy_flag == "intimate":
        return Category.intimate

    if result.sensitivity == Sensitivity.identity_document or result.privacy_flag == "identity_document":
        return Category.identity_documents

    if result.quality == Quality.reject or (result.quality_issues and "accidental" in result.quality_issues):
        return Category.accidental_blurry

    # Pillar 2: Business / Hair Solutions Co.
    if result.domain in (Domain.business, Domain.hair_solutions_co):
        if result.category == Category.shopify or (result.app_name and "shopify" in result.app_name.lower()):
            return Category.shopify
        if result.category in (Category.products, Category.specs, Category.business_people, Category.operations):
            return result.category
        if result.swatch_sub_type != "none":
            return Category.specs
        if result.subject_count == "single_person" and result.model_shot_type != "not_model":
            return Category.business_people
        if result.business_evidence:
            return Category.products
        return Category.operations

    # Pillar 3: Knowledge (Swipe File)
    if result.domain in (Domain.knowledge, Domain.knowledge_and_tools):
        tags_str = " ".join(result.tags).lower()
        tool = (result.subject_or_tool_discussed or "").lower()
        full_text = f"{tags_str} {tool} {result.rationale.lower()}"
        if result.knowledge_opportunity:
            sub = result.knowledge_opportunity.category_subfolder
            if sub in ("open-source-repos", "ai-agents-and-workflows", "crm-and-sales"):
                return Category.knowledge_ai
            if sub == "ui-ux-and-web":
                return Category.knowledge_ui
            if sub == "marketing-and-copy":
                return Category.knowledge_marketing
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
        if result.category is not None:
            return Category(result.category)
    except (ValueError, TypeError):
        pass
    return Category.personal_other

import asyncio
import os
import sys
import json
import sqlite3
from pathlib import Path
from dotenv import load_dotenv
import httpx
from PIL import Image
import io
import base64

SCRIPT_DIR = Path(__file__).parent
load_dotenv("/Users/vincent/.env")
load_dotenv(SCRIPT_DIR / ".env")

sys.path.append(str(SCRIPT_DIR))
from taxonomy import ClassificationResult, Category, get_final_category
from run_openrouter_qwen32b_classifier import prepare_image, OPENROUTER_URL, DEFAULT_MODEL

TEST_IDS = [39259, 34228, 397, 35508, 35904, 36330, 35422, 35434]

async def test_photos():
    api_key = os.environ.get("OPENROUTER_API_KEY")
    if not api_key:
        print("Missing OPENROUTER_API_KEY")
        return

    conn = sqlite3.connect(str(SCRIPT_DIR / "state.sqlite"))
    c = conn.cursor()
    c.execute(f"SELECT id, filename, file_path, qwen_category, json_extract(qwen_json, '$.has_vincent') FROM inventory WHERE id IN ({','.join(map(str, TEST_IDS))})")
    rows = c.fetchall()
    conn.close()

    schema_json = json.dumps(ClassificationResult.model_json_schema())

    print(f"\n{'='*80}")
    print(f"TESTING {len(rows)} PROBLEMATIC PHOTOS WITH REFINED PROMPT")
    print(f"{'='*80}\n")

    async with httpx.AsyncClient(timeout=90.0) as client:
        for row in rows:
            row_id, filename, file_path_str, old_cat, old_has_v = row
            img_path = Path(file_path_str)
            if not img_path.exists():
                print(f"Missing: {img_path}")
                continue

            img_b64, pil_img, meta_screenshot = prepare_image(img_path)

            prompt = (
                f"Analyze this image and classify it strictly according to this JSON schema: {schema_json}.\n\n"
                "CRITICAL TAXONOMY & CLASSIFICATION RULES:\n"
                "1. VINCENT (THE LIBRARY OWNER):\n"
                "   - has_vincent must ONLY be true if Vincent's human FACE is physically visible in the photo.\n"
                "   - NEVER set has_vincent=true just because the name 'Vincent' or 'Vincent Laroche' is written as text on an invoice, bank statement, WhatsApp message, email, or profile. Text mentions are NOT a human face!\n\n"
                "2. FINANCES, BILLS & INVOICES:\n"
                "   - Any invoice, utility bill (water, electric, gas), receipt, Boleto, Pix transfer receipt, bank transfer, bank statement (e.g. Nubank, Revolut, Mercado Pago, Neon, PicPay), tax form, or payment confirmation:\n"
                "     MUST be classified as category='finances/bills_invoices' with sensitivity='financial_document'.\n"
                "   - Do NOT classify bills or invoices as business screenshots or personal portraits.\n\n"
                "3. SHOPIFY & STORE BUILDING KNOWLEDGE:\n"
                "   - Any screenshot, slide, or post discussing Shopify store architecture, ideal product page (PDP) structure, e-commerce conversion rate optimization (CRO), e-commerce navigation, Shopify themes/apps, or how to build an online store:\n"
                "     MUST be classified as category='business/shopify', domain='business', app_name='Shopify', tags=['shopify', 'ecommerce', ...].\n\n"
                "4. USER'S BUSINESS (HAIR SOLUTIONS CO) VS PERSONAL CONSUMER ITEMS:\n"
                "   - The user's ONLY business is 'Hair Solutions Co' (men's hair replacement systems, toupees, hair pieces, wig lace, base cap construction, hair density swatches, hair factory/supplier chats like OneHead, and client hair before/afters).\n"
                "     ONLY these hair system items can be classified as business/01_products or business/*!\n"
                "   - ALL OTHER physical products or consumer goods are strictly PERSONAL:\n"
                "     * Household appliances (water heaters like Rinnai, air conditioners, furniture) -> personal/home_daily\n"
                "     * Pharmacy medications, blister packs, pill bottles, ointments, creams (e.g. Fucidine, Cimecort) -> personal/home_daily\n"
                "     * Clothing, shoe or brand tags (Adidas, Nike, Zara) -> personal/home_daily or personal/people\n"
                "     * Smartwatch bands, Apple Watch straps, jewelry, personal gadgets -> personal/home_daily\n"
                "     * Gym, fitness, sports, lifting weights -> personal/sports_hobbies\n"
                "     * Food, meals, cooking, restaurants, groceries -> personal/food\n"
                "     Do NOT classify appliances, medicines, or watch straps as business/01_products!\n\n"
                "5. SCREENSHOT APPS HIERARCHY:\n"
                "   - If capture_type is 'screenshot':\n"
                "     * If financial invoice/bill/bank transfer -> category='finances/bills_invoices'\n"
                "     * If discussing Shopify architecture/stores -> category='business/shopify'\n"
                "     * If retail shopping store (Amazon, Mercado Livre, Shopee, Zara, AliExpress) -> category='99_noise_and_review/screenshots/shopping', is_shopping=true\n"
                "     * If Instagram post/story/reel -> category='99_noise_and_review/screenshots/instagram', app_name='Instagram'\n"
                "     * If WhatsApp chat -> category='99_noise_and_review/screenshots/whatsapp', app_name='WhatsApp'\n"
                "     * If Grindr chat/profile -> category='99_noise_and_review/screenshots/grindr', app_name='Grindr'\n"
                "     * Other personal screenshot -> category='99_noise_and_review/screenshots/personal_other'\n"
                "     * Other business SaaS / software tools -> category='99_noise_and_review/screenshots/business'\n"
                "   - A physical camera photo of handwritten notes or paper is NEVER a screenshot. Use capture_type='camera_photo' or 'scanned_document'.\n\n"
                "Return ONLY the valid JSON object conforming to the schema."
            )

            payload = {
                "model": DEFAULT_MODEL,
                "messages": [
                    {
                        "role": "user",
                        "content": [
                            {"type": "text", "text": prompt},
                            {"type": "image_url", "image_url": {"url": f"data:image/jpeg;base64,{img_b64}"}}
                        ]
                    }
                ],
                "response_format": {"type": "json_object"},
                "temperature": 0.0,
                "max_tokens": 512
            }

            headers = {
                "Authorization": f"Bearer {api_key}",
                "Content-Type": "application/json",
                "HTTP-Referer": "https://github.com/vincent",
                "X-Title": "Media Workshop Photo Classifier"
            }

            resp = await client.post(OPENROUTER_URL, headers=headers, json=payload, timeout=60.0)
            if resp.status_code == 200:
                raw_json = resp.json()["choices"][0]["message"]["content"]
                parsed = json.loads(raw_json)
                res_obj = ClassificationResult(**parsed)
                final_cat = get_final_category(res_obj)
                
                print(f"[{row_id}] {filename}:")
                print(f"   OLD Category: {old_cat} | OLD has_vincent: {old_has_v}")
                print(f"   NEW Category: {final_cat.value if final_cat else res_obj.category.value}")
                print(f"   NEW has_vincent: {res_obj.has_vincent} | app_name: {res_obj.app_name}")
                print(f"   Rationale: {res_obj.rationale}")
                print("-" * 60)

if __name__ == "__main__":
    asyncio.run(test_photos())

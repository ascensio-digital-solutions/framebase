import json
import base64
import os
import argparse
from pathlib import Path
from pydantic import ValidationError
from typing import Optional
import urllib.request
from google import genai
from google.genai import types

from taxonomy import ClassificationResult, requires_gemini_review, Domain, Category
from pillow_heif import register_heif_opener

register_heif_opener()

def classify_with_spacebunny(image_path: Path, has_vincent: bool = False) -> Optional[ClassificationResult]:
    """
    Call Space Bunny Alpha via OpenRouter API.
    """
    import io
    from PIL import Image
    
    with Image.open(image_path) as img:
        img.thumbnail((1536, 1536), Image.Resampling.LANCZOS)
        if img.mode != "RGB":
            img = img.convert("RGB")
        buffer = io.BytesIO()
        img.save(buffer, format="JPEG", quality=85)
        img_b64 = base64.b64encode(buffer.getvalue()).decode('utf-8')
        
    url = "https://openrouter.ai/api/v1/chat/completions"
    api_key = os.environ.get("OPENROUTER_API_KEY")
    if not api_key:
        print("OPENROUTER_API_KEY environment variable missing.")
        return None
        
    schema = ClassificationResult.model_json_schema()
    
    vincent_context = ""
    if has_vincent:
        vincent_context = "\nCRITICAL NOTE: Facial recognition has confirmed that 'Vincent' (the owner) is in this photo. When describing the photo or generating tags, assume the main subject/person is Vincent (e.g. 'Vincent with friends', 'Vincent selfie')."
    
    payload = {
        "model": "stealth/space-bunny-alpha",
        "messages": [
            {
                "role": "user",
                "content": [
                    {"type": "text", "text": f"Analyze this image and classify it strictly according to this JSON schema: {json.dumps(schema)}.{vincent_context}"},
                    {"type": "image_url", "image_url": {"url": f"data:image/jpeg;base64,{img_b64}"}}
                ]
            }
        ],
        "response_format": {"type": "json_object"},
        "temperature": 0.0
    }
    
    req = urllib.request.Request(
        url,
        data=json.dumps(payload).encode('utf-8'),
        headers={
            'Content-Type': 'application/json',
            'Authorization': f'Bearer {api_key}',
            'HTTP-Referer': 'https://ascensio.ai',
            'X-Title': 'Media Workshop'
        }
    )
    
    try:
        response = urllib.request.urlopen(req, timeout=120)
        result = json.loads(response.read().decode('utf-8'))
        response_text = result['choices'][0]['message']['content']
        
        # Sometimes models wrap JSON in markdown block
        response_text = response_text.replace("```json", "").replace("```", "").strip()
        
        try:
            data = json.loads(response_text)
            return ClassificationResult(**data)
        except (json.JSONDecodeError, ValidationError) as e:
            print(f"Failed to parse Space Bunny output: {e}")
            return None
            
    except Exception as e:
        print(f"Space Bunny request failed: {e}")
        return None

def classify_with_gemini(image_path: Path, thinking_level: str = "high") -> Optional[ClassificationResult]:
    """
    Call Gemini 3.8 Flash with the schema using the standard API.
    """
    api_key = os.environ.get("GEMINI_API_KEY")
    if not api_key:
        print("GEMINI_API_KEY environment variable missing.")
        return None
        
    client = genai.Client(api_key=api_key)
    
    try:
        image = client.files.upload(file=str(image_path))
        
        response = client.models.generate_content(
            model='gemini-3.8-flash',
            contents=[
                "Analyze this image and classify it.", 
                image
            ],
            config=types.GenerateContentConfig(
                response_mime_type="application/json",
                response_schema=ClassificationResult,
                thinking_config=types.ThinkingConfig(
                    thinking_budget_tokens=1024, # reasonable budget
                ) if thinking_level != "none" else None
            )
        )
        
        try:
            data = json.loads(response.text)
            return ClassificationResult(**data)
        except (json.JSONDecodeError, ValidationError) as e:
            print(f"Failed to parse Gemini output: {e}")
            return None
    except Exception as e:
        print(f"Gemini request failed: {e}")
        return None

def main():
    parser = argparse.ArgumentParser(description="Classify a photo using Hybrid Qwen+Gemini pipeline")
    parser.add_argument("image_path", type=str, help="Path to the image to classify")
    parser.add_argument("--force-gemini", action="store_true", help="Skip Qwen and go straight to Gemini")
    args = parser.parse_args()
    
    image_path = Path(args.image_path)
    if not image_path.exists():
        print("File not found.")
        return
        
    if not args.force_gemini:
        print("Running initial triage with local Qwen...")
        result = classify_with_ollama(image_path)
        
        if result:
            print("\n--- Qwen Classification ---")
            print(result.model_dump_json(indent=2))
            
            if requires_gemini_review(result):
                print("\n[!] Qwen is uncertain or flagged as business. Routing to Gemini...")
            else:
                print("\n[+] Qwen classification accepted.")
                return
        else:
            print("\n[!] Qwen classification failed. Falling back to Gemini...")
            
    print("\nRunning classification with Gemini 3.8 Flash...")
    gemini_result = classify_with_gemini(image_path)
    if gemini_result:
        print("\n--- Gemini Classification ---")
        print(gemini_result.model_dump_json(indent=2))
    else:
        print("\n[-] Gemini classification failed.")

if __name__ == "__main__":
    main()

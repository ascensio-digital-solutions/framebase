import os
import sqlite3
import json
import base64
import io
import urllib.request
from pathlib import Path
from pydantic import ValidationError
from PIL import Image
from pillow_heif import register_heif_opener
from tqdm import tqdm
from datetime import datetime
from dotenv import load_dotenv

load_dotenv("/Users/vincent/.env")

register_heif_opener()

from taxonomy import ClassificationResult

def classify_with_ollama(image_path: Path) -> ClassificationResult | None:
    import ollama
    try:
        with Image.open(image_path) as img:
            img.thumbnail((1536, 1536), Image.Resampling.LANCZOS)
            if img.mode != "RGB":
                img = img.convert("RGB")
            buffer = io.BytesIO()
            img.save(buffer, format="JPEG", quality=85)
            img_bytes = buffer.getvalue()
    except Exception as e:
        print(f"Failed to process image {image_path} for Ollama: {e}")
        return None
    schema = ClassificationResult.model_json_schema()
    try:
        response = ollama.chat(
            model='qwen3.8:27b-mlx',
            messages=[
                {
                    'role': 'user',
                    'content': f"Analyze this image and classify it strictly according to this JSON schema: {json.dumps(schema)}",
                    'images': [img_bytes]
                }
            ],
            options={'temperature': 0.0}
        )
        msg = response['message']['content']
        if "```json" in msg:
            msg = msg.split("```json")[1].split("```")[0].strip()
        elif "```" in msg:
            msg = msg.split("```")[1].split("```")[0].strip()
        data = json.loads(msg)
        return ClassificationResult(**data)
    except Exception as e:
        print(f"Ollama failed for {image_path}: {e}")
        return None

DB_PATH = Path(__file__).parent.parent / "state_copy.sqlite"

def classify_with_openrouter(image_path: Path, model="stealth/space-bunny-alpha") -> dict:
    api_key = os.environ.get("OPENROUTER_API_KEY")
    if not api_key:
        return {"error": "Missing OPENROUTER_API_KEY"}
        
    try:
        with Image.open(image_path) as img:
            img.thumbnail((1536, 1536), Image.Resampling.LANCZOS)
            if img.mode != "RGB":
                img = img.convert("RGB")
            buffer = io.BytesIO()
            img.save(buffer, format="JPEG", quality=85)
            img_b64 = base64.b64encode(buffer.getvalue()).decode('utf-8')
            
        schema = ClassificationResult.model_json_schema()
        
        payload = {
            "model": model,
            "messages": [
                {
                    "role": "user",
                    "content": [
                        {"type": "text", "text": f"Analyze this image and classify it strictly according to this JSON schema: {json.dumps(schema)}"},
                        {"type": "image_url", "image_url": {"url": f"data:image/jpeg;base64,{img_b64}"}}
                    ]
                }
            ],
            "response_format": {"type": "json_object"}
        }
        
        req = urllib.request.Request(
            "https://openrouter.ai/api/v1/chat/completions",
            data=json.dumps(payload).encode('utf-8'),
            headers={
                'Content-Type': 'application/json',
                'Authorization': f'Bearer {api_key}',
                'HTTP-Referer': 'https://localhost',
                'X-Title': 'Media Classifier Test'
            }
        )
        
        response = urllib.request.urlopen(req, timeout=120)
        result = json.loads(response.read().decode('utf-8'))
        
        msg = result['choices'][0]['message']['content']
        # Extract JSON if markdown code blocks were used
        if "```json" in msg:
            msg = msg.split("```json")[1].split("```")[0].strip()
        elif "```" in msg:
            msg = msg.split("```")[1].split("```")[0].strip()
            
        data = json.loads(msg)
        validated = ClassificationResult(**data)
        return {"result": validated, "raw": msg}
        
    except Exception as e:
        return {"error": str(e)}

def main():
    if not os.environ.get("OPENROUTER_API_KEY"):
        print("ERROR: OPENROUTER_API_KEY environment variable is not set.")
        print("Please run with: OPENROUTER_API_KEY='sk-or-v1-...' uv run compare_models.py")
        return
        
    if not DB_PATH.exists():
        print("Database not found. Wait for inventory to complete if it hasn't.")
        return
        
    conn = sqlite3.connect(DB_PATH, timeout=30)
    c = conn.cursor()
    
    # Grab 100 random images that are normal photos (not videos/sidecars)
    c.execute("""
        SELECT id, file_path 
        FROM inventory 
        WHERE is_sidecar = 0 
          AND is_live_video = 0
          AND extension IN ('.heic', '.jpg', '.jpeg', '.png')
        ORDER BY RANDOM() 
        LIMIT 20
    """)
    rows = c.fetchall()
    
    print(f"Starting comparison test on {len(rows)} random images...")
    
    html = """
    <html>
    <head>
        <title>Qwen 3.8 vs Space Bunny Alpha Comparison</title>
        <style>
            body { font-family: sans-serif; background: #1a1a1a; color: #eee; margin: 20px; }
            table { width: 100%; border-collapse: collapse; margin-top: 20px; }
            th, td { border: 1px solid #444; padding: 10px; vertical-align: top; }
            th { background: #333; }
            img { max-width: 300px; height: auto; border-radius: 4px; }
            .json-block { background: #111; padding: 10px; border-radius: 4px; font-family: monospace; font-size: 12px; white-space: pre-wrap; overflow-x: auto;}
            .error { color: #ff5555; }
        </style>
    </head>
    <body>
        <h1>Model Vision Comparison: Qwen3.8:27b (Local) vs Space Bunny Alpha (OpenRouter)</h1>
        <p>Generated at: {timestamp}</p>
        <table>
            <tr>
                <th>Image</th>
                <th>Qwen3.8:27b-mlx (Local Ollama)</th>
                <th>Space Bunny Alpha (OpenRouter)</th>
            </tr>
    """
    
    html = html.replace("{timestamp}", datetime.now().strftime("%Y-%m-%d %H:%M:%S"))
    
    for row_id, path_str in tqdm(rows):
        path = Path(path_str)
        if not path.exists():
            continue
            
        try:
            with Image.open(path) as img_thumb:
                img_thumb.thumbnail((300, 300), Image.Resampling.LANCZOS)
                if img_thumb.mode != "RGB":
                    img_thumb = img_thumb.convert("RGB")
                thumb_buffer = io.BytesIO()
                img_thumb.save(thumb_buffer, format="JPEG", quality=80)
                img_b64 = base64.b64encode(thumb_buffer.getvalue()).decode('utf-8')
                img_src = f"data:image/jpeg;base64,{img_b64}"
        except Exception as e:
            img_src = ""
            print(f"Failed to generate thumbnail for {path}: {e}")
        
        # 1. Run Qwen
        qwen_res = classify_with_ollama(path)
        qwen_html = ""
        if qwen_res:
            qwen_html = f"<div class='json-block'>{qwen_res.model_dump_json(indent=2)}</div>"
        else:
            qwen_html = "<span class='error'>Failed or Invalid JSON</span>"
            
        # 2. Run Space Bunny
        sb_res = classify_with_openrouter(path)
        sb_html = ""
        if "error" in sb_res:
            sb_html = f"<span class='error'>Error: {sb_res['error']}</span>"
        else:
            sb_html = f"<div class='json-block'>{sb_res['result'].model_dump_json(indent=2)}</div>"
            
        html += f"""
            <tr>
                <td>
                    <img src="{img_src}" loading="lazy" /><br/>
                    <small>{path.name}</small>
                </td>
                <td>{qwen_html}</td>
                <td>{sb_html}</td>
            </tr>
        """
        
    html += """
        </table>
    </body>
    </html>
    """
    
    out_path = Path("comparison_report.html")
    with open(out_path, "w") as f:
        f.write(html)
        
    print(f"Comparison complete! Open {out_path.absolute()} in your browser to view the side-by-side results.")

if __name__ == "__main__":
    main()

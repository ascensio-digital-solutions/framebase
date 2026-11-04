import os
import glob
import base64
import requests
from datetime import datetime
from pathlib import Path
from tqdm import tqdm

# The folder where your Apple Shortcut will dump the day's screenshots
ANALYSIS_FOLDER = "/Users/vincent/Documents/Screenshots"
REPORT_OUTPUT_DIR = "/Users/vincent/04_systems/media_workshop/reports"

# The "memory" and context we pass to the AI model
SYSTEM_PROMPT = """You are an expert AI assistant that analyzes daily iPhone screenshots captured by the user.
Look at the phone screenshot and explain what it is.
Is it a mobile app (Instagram, WhatsApp, mobile Safari, Notes, Banking/Pix)?
Is it a shopping item or reference for Hair Solutions Co or personal projects?
Describe exactly what is shown on the phone screen, extract any key text or data, and provide concise, actionable takeaways.
Be concise, accurate, and insightful."""

def is_phone_screenshot(img_path: Path) -> bool:
    name_lower = img_path.name.lower()
    if (
        name_lower.startswith("cleanshot")
        or name_lower.startswith("screen shot")
        or name_lower.startswith("screenshot 20")
        or name_lower.startswith("screen recording")
    ):
        return False
    try:
        import subprocess
        res = subprocess.run(
            ["/usr/bin/sips", "-g", "pixelWidth", "-g", "pixelHeight", str(img_path)],
            capture_output=True,
            text=True,
            timeout=5,
        )
        if res.returncode == 0:
            w, h = None, None
            for line in res.stdout.splitlines():
                if "pixelWidth:" in line:
                    w = int(line.split(":")[1].strip())
                elif "pixelHeight:" in line:
                    h = int(line.split(":")[1].strip())
            if w and h:
                if h <= w:
                    return False
                ratio = h / w
                return 1.6 <= ratio <= 2.5
    except Exception:
        pass
    return name_lower.startswith("img_") or name_lower.startswith("screenshot_")

def encode_image_to_base64(image_path):
    with open(image_path, "rb") as image_file:
        return base64.b64encode(image_file.read()).decode('utf-8')

def analyze_with_vision_model(base64_img):
    openrouter_api_key = os.getenv("OPENROUTER_API_KEY")
    if not openrouter_api_key:
        return "Error: OPENROUTER_API_KEY environment variable not set."
        
    url = "https://openrouter.ai/api/v1/chat/completions"
    headers = {
        "Authorization": f"Bearer {openrouter_api_key}",
        "Content-Type": "application/json"
    }
    
    payload = {
        # Note: Replace 'space-bunny-alpha' if the actual OpenRouter model ID differs.
        "model": "space-bunny-alpha",
        "messages": [
            {
                "role": "user",
                "content": [
                    {
                        "type": "text",
                        "text": SYSTEM_PROMPT
                    },
                    {
                        "type": "image_url",
                        "image_url": {
                            "url": f"data:image/jpeg;base64,{base64_img}"
                        }
                    }
                ]
            }
        ]
    }
    
    try:
        response = requests.post(url, headers=headers, json=payload)
        response.raise_for_status()
        return response.json()['choices'][0]['message']['content']
    except Exception as e:
        return f"Error analyzing image: {str(e)}\nResponse: {response.text if 'response' in locals() else ''}"

def main():
    analysis_dir = Path(ANALYSIS_FOLDER)
    report_dir = Path(REPORT_OUTPUT_DIR)
    
    analysis_dir.mkdir(parents=True, exist_ok=True)
    report_dir.mkdir(parents=True, exist_ok=True)
    
    # Get all images created in the last 24 hours
    valid_extensions = {'.png', '.jpg', '.jpeg'}
    images = []
    now = datetime.now().timestamp()
    for f in analysis_dir.iterdir():
        if f.suffix.lower() in valid_extensions:
            try:
                # Get creation time (st_birthtime on macOS)
                creation_time = f.stat().st_birthtime
                if (now - creation_time) <= 86400 and is_phone_screenshot(f): # 24 hours in seconds
                    images.append(f)
            except AttributeError:
                # Fallback if st_birthtime is somehow unavailable
                if (now - f.stat().st_mtime) <= 86400 and is_phone_screenshot(f):
                    images.append(f)
    
    if not images:
        print(f"No screenshots found in {ANALYSIS_FOLDER} for today.")
        return
        
    print(f"Found {len(images)} screenshots to analyze.")
    
    results = []
    
    for img_path in tqdm(images, desc="Analyzing screenshots"):
        b64 = encode_image_to_base64(img_path)
        analysis = analyze_with_vision_model(b64)
        
        results.append({
            'filename': img_path.name,
            'analysis': analysis
        })
        
    # Generate Markdown Report
    date_str = datetime.now().strftime("%Y-%m-%d")
    report_path = report_dir / f"screenshot_report_{date_str}.md"
    
    with open(report_path, "w") as f:
        f.write(f"# Daily Screenshot Report - {date_str}\n\n")
        f.write("Here is the breakdown of what you captured today:\n\n")
        
        for res in results:
            f.write(f"### {res['filename']}\n")
            f.write(f"{res['analysis']}\n\n")
            
        f.write("---\n")
        f.write("*End of report.*")
        
    print(f"\nAnalysis complete! Report saved to {report_path}")
    
    # Optional: Clear the folder after analysis so it's ready for tomorrow
    # for img in images:
    #     img.unlink()

if __name__ == "__main__":
    main()

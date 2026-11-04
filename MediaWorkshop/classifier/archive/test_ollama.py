import base64
import json
import urllib.request
from pathlib import Path
import sys

def test_ollama_vision(image_path_str):
    image_path = Path(image_path_str)
    if not image_path.exists():
        print(f"File not found: {image_path}")
        return

    with open(image_path, "rb") as f:
        img_b64 = base64.b64encode(f.read()).decode('utf-8')

    url = "http://localhost:11434/api/generate"
    payload = {
        "model": "qwen3.5:35b",
        "prompt": "Describe what is in this image. Is it a business product photo, a receipt, a selfie, a landscape, or something else?",
        "images": [img_b64],
        "stream": False
    }

    req = urllib.request.Request(
        url,
        data=json.dumps(payload).encode('utf-8'),
        headers={'Content-Type': 'application/json'}
    )

    print(f"Sending {image_path.name} to Ollama qwen3.8:27b-mlx...")
    try:
        response = urllib.request.urlopen(req)
        result = json.loads(response.read().decode('utf-8'))
        print("\nResponse from Qwen:")
        print(result.get('response', 'No response field in output'))
    except Exception as e:
        print(f"Error communicating with Ollama: {e}")

if __name__ == "__main__":
    test_photo = "/Users/vincent/04_systems/media_workshop/iPhoto export 2010-2026/2026/personal/0C18B9B5-4629-46D5-BE9D-1981DAE1EAC5.jpg"
    test_ollama_vision(test_photo)

import os
import json
import urllib.request
from dotenv import load_dotenv

load_dotenv("/Users/vincent/.env")
api_key = os.environ.get("OPENROUTER_API_KEY")

if not api_key:
    print("No key found!")
    exit(1)

payload = {
    "model": "stealth/space-bunny-alpha",
    "messages": [
        {"role": "user", "content": "hello, are you online?"}
    ]
}

req = urllib.request.Request(
    "https://openrouter.ai/api/v1/chat/completions",
    data=json.dumps(payload).encode('utf-8'),
    headers={
        'Content-Type': 'application/json',
        'Authorization': f'Bearer {api_key}',
    }
)

try:
    res = urllib.request.urlopen(req)
    out = json.loads(res.read().decode('utf-8'))
    print("SUCCESS!")
    print(out['choices'][0]['message']['content'])
except Exception as e:
    print(f"FAILED: {e}")

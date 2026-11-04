import urllib.request
import json
import os
from dotenv import load_dotenv
load_dotenv("/Users/vincent/.env")
api_key = os.environ.get("OPENROUTER_API_KEY")
payload = {
    "model": "meta-llama/llama-3.2-11b-vision-instruct:free",
    "messages": [
        {"role": "user", "content": "hello"}
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
    print(res.read())
except urllib.error.HTTPError as e:
    print(f"Error: {e.code} - {e.read().decode('utf-8')}")
except Exception as e:
    print(f"Error: {e}")

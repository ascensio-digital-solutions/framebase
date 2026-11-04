import urllib.request, json
res = urllib.request.urlopen("https://openrouter.ai/api/v1/models")
data = json.loads(res.read())
for m in data['data']:
    if 'bunny' in m['id'].lower() or 'bunny' in m['name'].lower():
        print(m['id'], m['name'])

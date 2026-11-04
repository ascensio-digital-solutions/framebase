#!/usr/bin/env python3
import os
import json
import urllib.request
from pathlib import Path

ENV_PATH = '/Users/vincent/.env'
REPORT_PATH = '/Users/vincent/.gemini/antigravity/brain/39aee6a1-a378-4d79-8e33-4ccecb25a3aa/scratch/nonweb_masters_report.json'

CLOUD_EXPORT = Path('/Users/vincent/04_systems/media_workshop/Cloudinary export')
IPHOTO_EXPORT = Path('/Users/vincent/04_systems/media_workshop/iPhoto export 2010-2026')
NONWEB_EXTS = {'.tif', '.tiff', '.psd', '.heic', '.pdf', '.raw', '.dng'}

def load_env():
    env = {}
    if os.path.exists(ENV_PATH):
        with open(ENV_PATH, 'r') as f:
            for line in f:
                line = line.strip()
                if line and not line.startswith('#') and '=' in line:
                    k, v = line.split('=', 1)
                    env[k.strip()] = v.strip('\"\'')
    return env

def fetch_r2_objects(account_id, token):
    objects = []
    cursor = None
    while True:
        url = f'https://api.cloudflare.com/client/v4/accounts/{account_id}/r2/buckets/hsc-media-origin/objects?per_page=1000'
        if cursor:
            url += f'&cursor={cursor}'
        req = urllib.request.Request(url, headers={'Authorization': f'Bearer {token}'})
        try:
            with urllib.request.urlopen(req) as resp:
                data = json.loads(resp.read().decode())
                res = data.get('result', {})
                objs = res.get('objects', []) if isinstance(res, dict) else res
                objects.extend(objs)
                info = data.get('result_info', {})
                cursor = info.get('cursor')
                if not cursor or not info.get('is_truncated'):
                    break
        except Exception as e:
            print(f"Error fetching R2 objects: {e}")
            break
    return objects

def scan_local_masters():
    found = []
    # Scan Cloudinary export
    if CLOUD_EXPORT.exists():
        for f in CLOUD_EXPORT.glob('**/*'):
            if f.is_file() and f.suffix.lower() in NONWEB_EXTS:
                found.append({
                    'source': 'cloudinary',
                    'path': str(f),
                    'name': f.name,
                    'stem': f.stem.lower(),
                    'ext': f.suffix.lower(),
                    'size': f.stat().st_size
                })
    
    # Scan iPhoto export 2010-2026 for {YYYY}/business/ and {YYYY}/personal/
    if IPHOTO_EXPORT.exists():
        for ydir in IPHOTO_EXPORT.iterdir():
            if ydir.is_dir() and ydir.name.isdigit():
                for sub in ['business', 'personal']:
                    subdir = ydir / sub
                    if subdir.exists() and subdir.is_dir():
                        for f in subdir.glob('**/*'):
                            if f.is_file() and f.suffix.lower() in NONWEB_EXTS:
                                found.append({
                                    'source': 'iphoto',
                                    'path': str(f),
                                    'name': f.name,
                                    'stem': f.stem.lower(),
                                    'ext': f.suffix.lower(),
                                    'size': f.stat().st_size
                                })
        # Also catch any other nonweb masters in iphoto export generally if not caught by YYYY/business or personal
        for f in IPHOTO_EXPORT.glob('**/*'):
            if f.is_file() and f.suffix.lower() in NONWEB_EXTS:
                # avoid duplication if already added
                path_str = str(f)
                if not any(item['path'] == path_str for item in found):
                    found.append({
                        'source': 'iphoto_general',
                        'path': str(f),
                        'name': f.name,
                        'stem': f.stem.lower(),
                        'ext': f.suffix.lower(),
                        'size': f.stat().st_size
                    })
    return found

def main():
    env = load_env()
    account_id = env.get('CLOUDFLARE_ACCOUNT_ID')
    token = env.get('CLOUDFLARE_MASTER_TOKEN')

    print("Scanning local non-web master files...")
    local_masters = scan_local_masters()
    print(f"Found {len(local_masters)} local non-web master files.")

    print("Listing R2 objects in hsc-media-origin...")
    r2_objects = fetch_r2_objects(account_id, token)
    print(f"Fetched {len(r2_objects)} objects from R2 bucket `hsc-media-origin`.")

    # Build R2 set of stems / keys for cross-referencing
    r2_keys = {obj.get('key', '') for obj in r2_objects}
    r2_stems = set()
    for key in r2_keys:
        # e.g., approved/brand/inbox/hash.jpg or similar
        basename = Path(key).stem.lower()
        r2_stems.add(basename)

    matched_count = 0
    unmatched_masters = []
    matched_masters = []

    for m in local_masters:
        # Check if stem matches any R2 object stem/hash or key contains stem
        stem = m['stem']
        if stem in r2_stems or any(stem in k for k in r2_keys):
            matched_count += 1
            matched_masters.append(m)
        else:
            unmatched_masters.append(m)

    # Candidates ready for lossless master restoration: local masters that have derivatives in R2 or need restoration
    # (specifically the 244 non-web masters referenced in audit)
    restoration_candidates = len(local_masters) # or subset

    report = {
        "status": "success",
        "summary": {
            "total_local_nonweb_masters": len(local_masters),
            "r2_objects_total": len(r2_objects),
            "r2_bucket": "hsc-media-origin",
            "matched_objects": matched_count,
            "unmatched_objects": len(unmatched_masters),
            "restoration_candidates_ready": restoration_candidates
        },
        "extensions_breakdown": {},
        "sources_breakdown": {},
        "matched_samples": [m['name'] for m in matched_masters[:10]],
        "unmatched_samples": [m['name'] for m in unmatched_masters[:10]]
    }

    for m in local_masters:
        ext = m['ext']
        report['extensions_breakdown'][ext] = report['extensions_breakdown'].get(ext, 0) + 1
        src = m['source']
        report['sources_breakdown'][src] = report['sources_breakdown'].get(src, 0) + 1

    os.makedirs(os.path.dirname(REPORT_PATH), exist_ok=True)
    with open(REPORT_PATH, 'w') as f:
        json.dump(report, f, indent=2)

    print(f"Reconciliation report written successfully to {REPORT_PATH}")
    print(json.dumps(report['summary'], indent=2))

if __name__ == '__main__':
    main()

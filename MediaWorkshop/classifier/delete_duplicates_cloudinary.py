import json
import os

results_file = 'deduplication_results_cloudinary.json'

print(f"Loading {results_file}...")
with open(results_file, 'r') as f:
    data = json.load(f)

duplicates = data.get('exact_groups', []) + data.get('near_groups', [])
deleted_count = 0
kept_count = 0

for group in duplicates:
    if len(group) < 2:
        continue
    
    # Filter only files that still exist
    existing_files = [f for f in group if os.path.exists(f)]
    
    if len(existing_files) < 2:
        continue
        
    # Sort by modification time, newest first
    existing_files.sort(key=lambda f: os.path.getmtime(f), reverse=True)
    
    newest = existing_files[0]
    to_delete = existing_files[1:]
    
    print(f"Group: keeping newest ({os.path.basename(newest)})")
    
    for df in to_delete:
        try:
            os.remove(df)
            deleted_count += 1
            print(f"  Deleted: {os.path.basename(df)}")
        except Exception as e:
            print(f"  Error deleting {df}: {e}")
            
    kept_count += 1

print(f"\nDone! Deleted {deleted_count} files across {kept_count} duplicate groups.")

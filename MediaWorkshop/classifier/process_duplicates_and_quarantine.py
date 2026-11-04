import json
import os
import sqlite3
import shutil
from pathlib import Path
import logging

logging.basicConfig(level=logging.INFO, format='%(message)s')

DB_PATH = Path("state.sqlite")
QUARANTINE_DIR = Path("/Users/vincent/04_systems/media_workshop/iPhoto export 2010-2026/_quarantined")
RESULTS_FILE = 'deduplication_results.json'

conn = sqlite3.connect(DB_PATH)
c = conn.cursor()

# 1. Move Quarantined files
QUARANTINE_DIR.mkdir(exist_ok=True, parents=True)
c.execute("SELECT id, file_path FROM inventory WHERE local_only = 1")
quarantined_rows = c.fetchall()

moved = 0
for row_id, path_str in quarantined_rows:
    path = Path(path_str)
    if not path.exists():
        continue
    
    new_path = QUARANTINE_DIR / path.name
    counter = 1
    while new_path.exists():
        new_path = QUARANTINE_DIR / f"{path.stem}_{counter}{path.suffix}"
        counter += 1
        
    shutil.move(str(path), str(new_path))
    c.execute("UPDATE inventory SET file_path = ? WHERE id = ?", (str(new_path), row_id))
    moved += 1

logging.info(f"Moved {moved} files to {QUARANTINE_DIR}")

# 2. Delete Duplicates
with open(RESULTS_FILE, 'r') as f:
    data = json.load(f)

duplicates = data.get('exact_groups', []) + data.get('near_groups', [])
deleted_count = 0
kept_count = 0

for group in duplicates:
    if len(group) < 2:
        continue
    
    existing_files = [f for f in group if os.path.exists(f)]
    if len(existing_files) < 2:
        continue
        
    # Sort by modification time, newest first
    existing_files.sort(key=lambda f: os.path.getmtime(f), reverse=True)
    
    newest = existing_files[0]
    to_delete = existing_files[1:]
    
    for df in to_delete:
        try:
            os.remove(df)
            c.execute("DELETE FROM inventory WHERE file_path = ?", (df,))
            deleted_count += 1
        except Exception as e:
            logging.error(f"  Error deleting {df}: {e}")
            
    kept_count += 1

conn.commit()
conn.close()
logging.info(f"Deleted {deleted_count} duplicate files across {kept_count} groups.")

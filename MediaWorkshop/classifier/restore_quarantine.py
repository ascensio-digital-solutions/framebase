import sqlite3
import shutil
from pathlib import Path

DB_PATH = Path("state.sqlite")
QUARANTINE_DIR = Path("/Users/vincent/04_systems/media_workshop/Cloudinary export/06_private_quarantine")
ROOT_DIR = Path("/Users/vincent/04_systems/media_workshop/iPhoto export 2010-2026")

conn = sqlite3.connect(DB_PATH)
c = conn.cursor()

count = 0
for file_path in QUARANTINE_DIR.iterdir():
    if not file_path.is_file():
        continue
    
    # Look up original path in DB by matching the filename.
    # We use file_path ending with the name.
    c.execute("SELECT file_path FROM inventory WHERE file_path LIKE ?", (f"%{file_path.name}",))
    row = c.fetchone()
    if row:
        original_path = Path(row[0])
        # Move back to original path
        original_path.parent.mkdir(parents=True, exist_ok=True)
        shutil.move(str(file_path), str(original_path))
        count += 1
    else:
        print(f"Could not find original path for {file_path.name}")

# Also reset local_only for everything just in case
c.execute("UPDATE inventory SET local_only = 0, nudenet_score = 0")
conn.commit()
conn.close()

print(f"Restored {count} files from quarantine.")

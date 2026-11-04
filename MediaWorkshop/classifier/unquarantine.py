import sqlite3
import shutil
from pathlib import Path

DB_PATH = Path("state.sqlite")
ROOT_DIR = Path("/Users/vincent/04_systems/media_workshop/iPhoto export 2010-2026")

conn = sqlite3.connect(DB_PATH)
c = conn.cursor()

c.execute("SELECT id, file_path, year, local_only FROM inventory WHERE local_only = 1")
rows = c.fetchall()

success = 0
for pid, p_path_str, year, local_only in rows:
    original_path = Path(p_path_str)
    
    # Where apply.py moved it
    quarantine_path = ROOT_DIR / str(year) / "quarantine" / original_path.name
    
    if quarantine_path.exists():
        original_path.parent.mkdir(parents=True, exist_ok=True)
        try:
            shutil.move(str(quarantine_path), str(original_path))
            # Also reset local_only
            c.execute("UPDATE inventory SET local_only = 0, nudenet_score = 0 WHERE id = ?", (pid,))
            success += 1
            
            # Now sidecars
            c.execute("SELECT id, file_path FROM inventory WHERE parent_id = ?", (pid,))
            for cid, c_path_str in c.fetchall():
                c_original_path = Path(c_path_str)
                c_quarantine = ROOT_DIR / str(year) / "quarantine" / c_original_path.name
                if c_quarantine.exists():
                    shutil.move(str(c_quarantine), str(c_original_path))
                    c.execute("UPDATE inventory SET local_only = 0, nudenet_score = 0 WHERE id = ?", (cid,))
        except Exception as e:
            print(f"Failed: {e}")

conn.commit()
conn.close()
print(f"Restored {success} quarantined parent items.")

import os
import shutil
import sqlite3
from pathlib import Path
from tqdm import tqdm

DB_PATH = Path(__file__).parent / "state.sqlite"
ROOT_DIR = Path("/Users/vincent/04_systems/media_workshop/iPhoto export 2010-2026")

def main():
    print("Flattening library back to ROOT/YEAR structure...")
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    
    c.execute("SELECT id, file_path, year, filename FROM inventory WHERE year IS NOT NULL")
    rows = c.fetchall()
    
    moved_count = 0
    for row_id, file_path_str, year, filename in tqdm(rows, desc="Moving files"):
        old_path = Path(file_path_str)
        if not old_path.exists():
            continue
            
        new_path = ROOT_DIR / str(year) / filename
        
        if old_path == new_path:
            continue
            
        new_path.parent.mkdir(parents=True, exist_ok=True)
        
        # Handle filename collisions (unlikely since filenames were unique inside the year, but just in case)
        if new_path.exists():
            base = new_path.stem
            ext = new_path.suffix
            counter = 1
            while new_path.exists():
                new_path = new_path.with_name(f"{base}_{counter}{ext}")
                counter += 1
                
        shutil.move(str(old_path), str(new_path))
        
        # Update database so we don't lose NudeNet scores or inventory!
        c.execute("UPDATE inventory SET file_path = ?, current_folder = ? WHERE id = ?", (str(new_path), None, row_id))
        moved_count += 1
        
    conn.commit()
    conn.close()
    print(f"Moved {moved_count} files.")
    
    print("Cleaning up old category folders...")
    for year_dir in ROOT_DIR.iterdir():
        if year_dir.is_dir() and year_dir.name.isdigit():
            # Delete subdirectories (which are the categories)
            for sub_dir in list(year_dir.iterdir()):
                if sub_dir.is_dir():
                    try:
                        shutil.rmtree(sub_dir)
                        print(f"Deleted folder: {sub_dir.relative_to(ROOT_DIR)}")
                    except Exception as e:
                        print(f"Could not delete {sub_dir}: {e}")

if __name__ == "__main__":
    main()

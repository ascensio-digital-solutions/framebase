import os
import sqlite3
import shutil
from pathlib import Path
from PIL import Image
from tqdm import tqdm

DB_PATH = Path(__file__).parent.parent / "state.sqlite"
ROOT_DIR = Path("/Users/vincent/04_systems/media_workshop/iPhoto export 2010-2026")

def is_screenshot(path_str):
    filename = Path(path_str).name.lower()
    
    # 1. Mac screenshots and explicitly named screenshots
    if "screenshot" in filename:
        return True
        
    # 2. Only check PNGs for Apple's hidden EXIF tag
    if not filename.endswith('.png'):
        return False
        
    try:
        with Image.open(path_str) as img:
            # Check XMP metadata
            xmp = img.info.get('XML:com.adobe.xmp', '')
            if isinstance(xmp, str) and 'Screenshot' in xmp:
                return True
            elif isinstance(xmp, bytes) and b'Screenshot' in xmp:
                return True
                
            # Check raw EXIF bytes
            exif_bytes = img.info.get('exif', b'')
            if b'Screenshot' in exif_bytes:
                return True
    except Exception:
        pass
        
    return False

def main():
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    
    # Find all PNGs and explicitly named screenshots
    c.execute("""
        SELECT id, file_path, year 
        FROM inventory 
        WHERE (extension LIKE '.png' OR filename LIKE '%Screenshot%')
          AND is_sidecar = 0
    """)
    candidates = c.fetchall()
    
    screenshots_to_move = []
    
    print(f"Scanning {len(candidates)} potential screenshots...")
    for row_id, file_path, year in tqdm(candidates):
        if os.path.exists(file_path) and is_screenshot(file_path):
            screenshots_to_move.append((row_id, file_path, year))
            
    print(f"\nFound {len(screenshots_to_move)} confirmed screenshots.")
    
    if not screenshots_to_move:
        print("Nothing to move.")
        return
        
    moved_count = 0
    for row_id, file_path, year in tqdm(screenshots_to_move, desc="Moving files"):
        old_path = Path(file_path)
        if not old_path.exists():
            continue
            
        # Create year/Screenshots directory
        dest_dir = ROOT_DIR / str(year) / "Screenshots"
        dest_dir.mkdir(parents=True, exist_ok=True)
        
        new_path = dest_dir / old_path.name
        
        # Handle duplicates if they exist in the destination
        counter = 1
        while new_path.exists():
            new_path = dest_dir / f"{old_path.stem}_{counter}{old_path.suffix}"
            counter += 1
            
        # Move the file
        shutil.move(str(old_path), str(new_path))
        
        # Update database
        c.execute("""
            UPDATE inventory 
            SET file_path = ?, current_folder = 'Screenshots' 
            WHERE id = ?
        """, (str(new_path), row_id))
        
        moved_count += 1
        
        # Check for and move any associated sidecars
        c.execute("SELECT id, file_path FROM inventory WHERE parent_id = ?", (row_id,))
        sidecars = c.fetchall()
        for sid, sidecar_path in sidecars:
            old_sidecar = Path(sidecar_path)
            if old_sidecar.exists():
                new_sidecar = dest_dir / old_sidecar.name
                shutil.move(str(old_sidecar), str(new_sidecar))
                c.execute("""
                    UPDATE inventory 
                    SET file_path = ?, current_folder = 'Screenshots' 
                    WHERE id = ?
                """, (str(new_sidecar), sid))
                moved_count += 1
                
        if moved_count % 50 == 0:
            conn.commit()
            
    conn.commit()
    conn.close()
    
    print(f"\nSuccessfully moved {moved_count} files into year/Screenshots/ folders.")

if __name__ == "__main__":
    main()

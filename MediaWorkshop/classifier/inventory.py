import os
import sqlite3
import hashlib
from pathlib import Path
from PIL import Image
from PIL.ExifTags import TAGS
from pillow_heif import register_heif_opener
import json
import logging
from tqdm import tqdm

# Register HEIF opener for Apple photos
register_heif_opener()

logging.basicConfig(level=logging.INFO, format='%(levelname)s: %(message)s')

DB_PATH = Path(__file__).parent / "state.sqlite"
ROOT_DIR = Path("/Users/vincent/04_systems/media_workshop/iPhoto export 2010-2026")

def init_db():
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute('''
        CREATE TABLE IF NOT EXISTS inventory (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            file_path TEXT UNIQUE,
            filename TEXT,
            extension TEXT,
            sha256 TEXT,
            file_size INTEGER,
            year INTEGER,
            current_folder TEXT,
            
            exif_datetime TEXT,
            exif_camera TEXT,
            width INTEGER,
            height INTEGER,
            
            is_sidecar BOOLEAN DEFAULT 0,
            is_live_video BOOLEAN DEFAULT 0,
            parent_id INTEGER,
            
            local_only BOOLEAN DEFAULT 0,
            nudenet_score REAL,
            
            qwen_category TEXT,
            qwen_confidence REAL,
            qwen_json TEXT,
            
            gemini_category TEXT,
            gemini_confidence REAL,
            gemini_json TEXT,
            
            final_domain TEXT,
            final_category TEXT,
            processed BOOLEAN DEFAULT 0
        )
    ''')
    conn.commit()
    return conn

def hash_file(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        while chunk := f.read(8192):
            h.update(chunk)
    return h.hexdigest()

def extract_exif(path: Path):
    exif_data = {
        'datetime': None,
        'camera': None,
        'width': None,
        'height': None
    }
    
    try:
        with Image.open(path) as img:
            exif_data['width'] = img.width
            exif_data['height'] = img.height
            
            exif = img.getexif()
            if exif:
                for tag_id, value in exif.items():
                    tag = TAGS.get(tag_id, tag_id)
                    if tag == 'DateTimeOriginal' or tag == 'DateTime':
                        exif_data['datetime'] = str(value)
                    elif tag == 'Model':
                        exif_data['camera'] = str(value).strip('\x00')
    except Exception as e:
        # Ignore errors for non-images (videos, sidecars)
        pass
        
    return exif_data

def main():
    conn = init_db()
    c = conn.cursor()
    
    # Collect all files first for tqdm
    logging.info("Scanning directory...")
    all_files = []
    for root, _, files in os.walk(ROOT_DIR):
        for f in files:
            if f == ".DS_Store" or f.endswith(".log") or f.endswith(".py"):
                continue
            all_files.append(Path(root) / f)
            
    logging.info(f"Found {len(all_files)} files. Hashing and extracting metadata...")
    
    for path in tqdm(all_files):
        # Check if already processed
        c.execute("SELECT id FROM inventory WHERE file_path = ?", (str(path),))
        if c.fetchone():
            continue
            
        ext = path.suffix.lower()
        size = path.stat().st_size
        sha = hash_file(path)
        
        year_folder = None
        current_folder = None
        # Path logic: iPhoto export 2010-2026 / 2026 / personal / filename
        parts = path.relative_to(ROOT_DIR).parts
        if len(parts) >= 2:
            try:
                year_folder = int(parts[0])
            except ValueError:
                pass
            current_folder = "/".join(parts[1:-1])
            
        exif = extract_exif(path)
        
        is_sidecar = 1 if ext == '.aae' else 0
        
        c.execute('''
            INSERT INTO inventory (
                file_path, filename, extension, sha256, file_size, year, current_folder,
                exif_datetime, exif_camera, width, height, is_sidecar
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        ''', (
            str(path), path.name, ext, sha, size, year_folder, current_folder,
            exif['datetime'], exif['camera'], exif['width'], exif['height'], is_sidecar
        ))
        
        # Commit every 1000 files to avoid massive memory usage
        if c.lastrowid % 1000 == 0:
            conn.commit()
            
    conn.commit()
    
    # Simple pairing for Live Photos (Same name, .mov instead of .heic)
    logging.info("Linking sidecars and Live Photo videos...")
    c.execute("SELECT id, file_path FROM inventory WHERE extension IN ('.mov', '.mp4')")
    videos = c.fetchall()
    for vid, vpath in videos:
        base = Path(vpath).stem
        # Look for image with same stem
        c.execute("SELECT id FROM inventory WHERE file_path LIKE ? AND extension IN ('.heic', '.jpg', '.jpeg', '.dng')", (f"%/{base}.%",))
        parent = c.fetchone()
        if parent:
            c.execute("UPDATE inventory SET is_live_video = 1, parent_id = ? WHERE id = ?", (parent[0], vid))
            
    c.execute("SELECT id, file_path FROM inventory WHERE is_sidecar = 1")
    sidecars = c.fetchall()
    for sid, spath in sidecars:
        base = Path(spath).stem
        c.execute("SELECT id FROM inventory WHERE file_path LIKE ? AND extension IN ('.heic', '.jpg', '.jpeg', '.dng')", (f"%/{base}.%",))
        parent = c.fetchone()
        if parent:
            c.execute("UPDATE inventory SET parent_id = ? WHERE id = ?", (parent[0], sid))
            
    conn.commit()
    conn.close()
    logging.info("Inventory complete!")

if __name__ == "__main__":
    main()

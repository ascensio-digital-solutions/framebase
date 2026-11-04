import os
import sqlite3
import shutil
import re
from pathlib import Path
from PIL import Image
from pillow_heif import register_heif_opener
from tqdm import tqdm
import reverse_geocoder as rg
from PIL.ExifTags import GPSTAGS, IFD

register_heif_opener()

DB_PATH = Path(__file__).parent.parent / "state.sqlite"
ROOT_DIR = Path("/Users/vincent/04_systems/media_workshop/iPhoto export 2010-2026")

def get_decimal_from_dms(dms, ref):
    try:
        degrees = float(dms[0])
        minutes = float(dms[1])
        seconds = float(dms[2])
        decimal = degrees + minutes/60 + seconds/3600
        if ref in ['S', 'W']:
            decimal = -decimal
        return decimal
    except:
        return None

def get_exif_location(image_path):
    try:
        with Image.open(image_path) as img:
            exif = img.getexif()
            if not exif:
                return None
                
            gps_ifd = exif.get_ifd(IFD.GPSInfo)
            if not gps_ifd:
                return None
                
            gps_info = {}
            for key in gps_ifd.keys():
                decode = GPSTAGS.get(key, key)
                gps_info[decode] = gps_ifd[key]
                
            if 'GPSLatitude' in gps_info and 'GPSLongitude' in gps_info:
                lat = get_decimal_from_dms(gps_info['GPSLatitude'], gps_info.get('GPSLatitudeRef', 'N'))
                lon = get_decimal_from_dms(gps_info['GPSLongitude'], gps_info.get('GPSLongitudeRef', 'E'))
                if lat is not None and lon is not None:
                    return lat, lon
    except Exception:
        pass
    return None

KNOWN_LOCATIONS = [
    "los angeles", "paris", "new york", "london", "tokyo", "rome", "berlin", 
    "madrid", "barcelona", "amsterdam", "venice", "florence", "milano", 
    "las vegas", "san francisco", "miami", "chicago", "seattle", "austin", "mexico city"
]

def find_location_in_filename(filename):
    lower_name = filename.lower().replace("_", " ").replace("-", " ")
    for loc in KNOWN_LOCATIONS:
        if loc in lower_name:
            return loc.title()
    return None

def main():
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    
    # Add columns if they don't exist
    try:
        c.execute("ALTER TABLE inventory ADD COLUMN city TEXT")
        c.execute("ALTER TABLE inventory ADD COLUMN country TEXT")
    except sqlite3.OperationalError:
        pass
        
    c.execute("SELECT id, file_path, year, filename FROM inventory WHERE local_only = 0 AND current_folder IS NULL AND is_sidecar = 0")
    rows = c.fetchall()
    
    moved_count = 0
    for row_id, file_path_str, year, filename in tqdm(rows, desc="Filtering Locations"):
        path = Path(file_path_str)
        if not path.exists():
            continue
            
        city = find_location_in_filename(filename)
        country = None
        
        # Only check GPS if filename didn't give it away
        if not city:
            coords = get_exif_location(path)
            if coords:
                lat, lon = coords
                result = rg.search((lat, lon), verbose=False)
                if result:
                    city = result[0]['name']
                    country = result[0]['cc']
                    
        if city:
            c.execute("UPDATE inventory SET city = ?, country = ?, processed = 1 WHERE id = ?", 
                     (city, country, row_id))
            moved_count += 1
            
            # Also update associated sidecars/videos
            c.execute("SELECT id FROM inventory WHERE parent_id = ?", (row_id,))
            sidecars = c.fetchall()
            for sid, in sidecars:
                c.execute("UPDATE inventory SET city = ?, country = ?, processed = 1 WHERE id = ?", 
                         (city, country, sid))
            
            # Commit periodically
            if moved_count % 100 == 0:
                conn.commit()
                             
    conn.commit()
    conn.close()
    print(f"\nLocation filter complete! Sorted {moved_count} items by location (skipping AI scans for these!).")

if __name__ == "__main__":
    main()

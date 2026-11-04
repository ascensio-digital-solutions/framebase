import sqlite3
import hashlib
import argparse
from pathlib import Path
from collections import defaultdict
from tqdm import tqdm
from PIL import Image
from pillow_heif import register_heif_opener
register_heif_opener()
import json
import logging
from imagededup.methods import PHash

logging.basicConfig(level=logging.INFO, format='%(levelname)s: %(message)s')

DB_PATH = Path(__file__).parent / "state.sqlite"

def get_images_from_db(limit=None, year=None):
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    query = """
        SELECT id, file_path 
        FROM inventory 
        WHERE local_only = 0 
          AND is_sidecar = 0 
          AND is_live_video = 0
          AND extension IN ('.heic', '.jpg', '.jpeg', '.png')
    """
    if year:
        query += f" AND file_path LIKE '%/{year}/%'"
    if limit:
        query += f" LIMIT {limit}"
    c.execute(query)
    rows = c.fetchall()
    conn.close()
    return rows

def compute_exact_hash(path):
    try:
        with open(path, "rb") as f:
            return hashlib.sha256(f.read()).hexdigest()
    except Exception:
        return None

def main():
    parser = argparse.ArgumentParser(description="Three-tier Deduplication Pipeline")
    parser.add_argument("--phash-threshold", type=int, default=3, help="Hamming distance for near duplicates")
    parser.add_argument("--calibrate", action="store_true", help="Run calibration on a small set to find optimal thresholds")
    parser.add_argument("--limit", type=int, help="Limit the number of images to process (useful for testing)")
    parser.add_argument("--year", type=str, help="Only process images from a specific year (e.g. 2018)")
    parser.add_argument("--input-dir", type=str, help="Run on a specific directory instead of querying the SQLite DB")
    parser.add_argument("--output-suffix", type=str, default="", help="Suffix for the output JSON file")
    args = parser.parse_args()
    
    if args.calibrate:
        logging.info("Calibration mode: Not yet implemented. Please edit script to test known duplicates.")
        return
        
    logging.info("Starting Tier 1: Exact byte duplicates (SHA-256)")
    
    if args.input_dir:
        dir_path = Path(args.input_dir)
        logging.info(f"Scanning directory: {dir_path}")
        # Find all files with image extensions
        extensions = {'.heic', '.jpg', '.jpeg', '.png'}
        images_rows = []
        for p in dir_path.rglob('*'):
            if p.is_file() and p.suffix.lower() in extensions:
                images_rows.append((None, str(p)))
        if args.limit:
            images_rows = images_rows[:args.limit]
    else:
        images_rows = get_images_from_db(limit=args.limit, year=args.year)
    
    exact_groups = defaultdict(list)
    for row_id, path_str in tqdm(images_rows, desc="Hashing files (Tier 1)"):
        h = compute_exact_hash(path_str)
        if h:
            exact_groups[h].append(path_str)
            
    # Survivors: take the first item of each exact group
    survivors = [g[0] for g in exact_groups.values()]
    logging.info(f"Tier 1 finished. {len(images_rows)} images reduced to {len(survivors)} unique exact files.")
    
    logging.info("Starting Tier 2: Near-duplicates (pHash via imagededup)")
    phasher = PHash()
    
    encodings = {}
    for path_str in tqdm(survivors, desc="Computing pHash (Tier 2)"):
        try:
            h = phasher.encode_image(image_file=path_str)
            if h:
                encodings[path_str] = h
        except Exception:
            pass
            
    logging.info("Finding pHash duplicates...")
    phash_duplicates = phasher.find_duplicates(encoding_map=encodings, max_distance_threshold=args.phash_threshold)
    
    # Group the results uniquely
    near_groups = []
    seen_phash = set()
    
    for path, dups in phash_duplicates.items():
        if path in seen_phash or not dups:
            continue
        group = [path] + dups
        near_groups.append(group)
        seen_phash.update(group)
        
    logging.info(f"Tier 2 finished. {len(survivors)} images reduced to {len(encodings.keys()) - len(seen_phash) + len(near_groups)} distinct files.")
    
    results = {
        "exact_groups": [g for g in exact_groups.values() if len(g) > 1],
        "near_groups": near_groups
    }
    
    out_name = f"deduplication_results{args.output_suffix}.json"
    out_path = Path(out_name)
    with open(out_path, "w") as f:
        json.dump(results, f, indent=2)
        
    logging.info(f"Pipeline complete! Results saved to {out_path.name}")
    logging.info(f"Exact duplicates found: {sum(len(g)-1 for g in results['exact_groups'])}")
    logging.info(f"Near duplicates found: {sum(len(g)-1 for g in results['near_groups'])}")

if __name__ == "__main__":
    main()

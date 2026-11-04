import sqlite3
import argparse
from pathlib import Path
from nudenet import NudeDetector
from transformers import pipeline
from tqdm import tqdm
import logging
from PIL import Image
from pillow_heif import register_heif_opener
register_heif_opener()

logging.basicConfig(level=logging.INFO, format='%(levelname)s: %(message)s')

DB_PATH = Path(__file__).parent / "state.sqlite"

def main():
    parser = argparse.ArgumentParser(description="Run combined NudeNet + Falconsai privacy gate")
    parser.add_argument("--threshold", type=float, default=0.45, help="Confidence threshold for female anatomy")
    args = parser.parse_args()
    
    if not DB_PATH.exists():
        logging.error("Database not found. Please run inventory.py first.")
        return
        
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    
    logging.info("Initializing NudeNet (Body Part Detection)...")
    detector = NudeDetector()
    
    logging.info("Initializing Falconsai (Binary Confirmation)...")
    classifier = pipeline("image-classification", model="Falconsai/nsfw_image_detection")
    
    c.execute("""
        SELECT id, file_path 
        FROM inventory 
        WHERE local_only = 0 
          AND is_sidecar = 0 
          AND is_live_video = 0
          AND extension IN ('.heic', '.jpg', '.jpeg', '.png')
    """)
    images = c.fetchall()
    
    logging.info(f"Running privacy gate on {len(images)} images...")
    
    flagged_count = 0
    explicit_labels_female = set()
    explicit_labels_male = {'MALE_GENITALIA_EXPOSED', 'ANUS_EXPOSED'}
    
    for row_id, path_str in tqdm(images):
        path = Path(path_str)
        try:
            with Image.open(path) as img:
                if img.mode != "RGB":
                    img = img.convert("RGB")
                
                ext = path.suffix.lower()
                if ext in ['.heic', '.dng']:
                    temp_path = Path("/tmp/nudenet_temp.jpg")
                    img.save(temp_path, format="JPEG", quality=85)
                    detections = detector.detect(str(temp_path))
                    if temp_path.exists():
                        temp_path.unlink()
                else:
                    detections = detector.detect(str(path))
                
                # Step 1: NudeNet body part detection with bias compensation
                max_score = 0.0
                is_candidate = False
                
                for det in detections:
                    label = det.get('class', det.get('label', ''))
                    score = det['score']
                    
                    if label in explicit_labels_female and score > args.threshold:
                        is_candidate = True
                        if score > max_score:
                            max_score = score
                            
                    elif label in explicit_labels_male and score > (args.threshold / 3.0):
                        is_candidate = True
                        if score > max_score:
                            max_score = score
                
                # Step 2: If NudeNet flags it, use Falconsai to confirm context (not art/medical)
                if is_candidate:
                    vit_result = classifier(img)
                    is_nsfw = False
                    for res in vit_result:
                        if res['label'] == 'nsfw' and res['score'] > 0.5:
                            is_nsfw = True
                            break
                            
                    if is_nsfw:
                        c.execute("UPDATE inventory SET local_only = 1, nudenet_score = ? WHERE id = ?", (max_score, row_id))
                        flagged_count += 1
                
            if row_id % 500 == 0:
                conn.commit()
                
        except Exception as e:
            logging.warning(f"Failed to process {path}: {e}")
            pass
            
    conn.commit()
    conn.close()
    logging.info(f"Privacy gate complete! Flagged {flagged_count} images for local-only quarantine.")

if __name__ == "__main__":
    main()

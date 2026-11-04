import os
import sqlite3
import shutil
import cv2
import numpy as np
from pathlib import Path
from PIL import Image
from pillow_heif import register_heif_opener
from tqdm import tqdm
from insightface.app import FaceAnalysis

register_heif_opener()

DB_PATH = Path(__file__).parent / "state.sqlite"
ROOT_DIR = Path("/Users/vincent/04_systems/media_workshop/iPhoto export 2010-2026")
REF_DIR = Path(__file__).parent / "reference_faces"

def load_reference_embeddings(app):
    embeddings = []
    if not REF_DIR.exists():
        REF_DIR.mkdir()
        print(f"Created {REF_DIR}. Please add some photos of Vincent to it!")
        return embeddings
        
    for p in REF_DIR.glob("*.*"):
        if p.suffix.lower() in [".jpg", ".jpeg", ".png", ".heic"]:
            try:
                # Load with PIL, convert to cv2 RGB
                with Image.open(p) as img:
                    img_rgb = img.convert('RGB')
                    img_cv2 = np.array(img_rgb)
                    img_cv2 = img_cv2[:, :, ::-1].copy() # RGB to BGR for insightface
                    
                faces = app.get(img_cv2)
                if faces:
                    embeddings.append(faces[0].normed_embedding)
                    print(f"Loaded face from {p.name}")
                else:
                    print(f"Warning: No face found in reference image {p.name}")
            except Exception as e:
                print(f"Error loading {p.name}: {e}")
    return embeddings

def is_vincent(face_embedding, ref_embeddings, threshold=0.45):
    # InsightFace threshold is usually around 0.4 - 0.5 for cosine similarity.
    # Higher means stricter. We'll use 0.45 which is fairly strict for Buffalo_S
    for ref in ref_embeddings:
        sim = np.dot(face_embedding, ref)
        if sim > threshold:
            return True
    return False

def main():
    # Initialize InsightFace using buffalo_s for speed
    print("Loading AI Face Recognition Model...")
    app = FaceAnalysis(name='buffalo_s') 
    app.prepare(ctx_id=0, det_size=(640, 640)) # 0 means CPU
    
    ref_embeddings = load_reference_embeddings(app)
    if not ref_embeddings:
        print("\nNo reference embeddings found.")
        print(f"-> Please add 5-10 clear photos of your face to: {REF_DIR}")
        print("-> Then run this script again.")
        return
        
    print(f"\nLoaded {len(ref_embeddings)} reference faces. Ready to scan inventory for Vincent.")
    
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    
    # Check if has_vincent column exists
    try:
        c.execute("ALTER TABLE inventory ADD COLUMN has_vincent INTEGER DEFAULT 0")
    except sqlite3.OperationalError:
        pass
    
    c.execute("SELECT id, file_path, year, filename FROM inventory WHERE local_only = 0 AND current_folder IS NULL AND is_sidecar = 0")
    rows = c.fetchall()
    
    moved_count = 0
    for row_id, file_path_str, year, filename in tqdm(rows, desc="Filtering Faces"):
        path = Path(file_path_str)
        if not path.exists() or path.suffix.lower() not in [".jpg", ".jpeg", ".png", ".heic"]:
            continue
            
        try:
            with Image.open(path) as img:
                img_rgb = img.convert('RGB')
                # Resize if too large to speed up (max 1500px)
                if max(img_rgb.size) > 1500:
                    img_rgb.thumbnail((1500, 1500))
                
                img_cv2 = np.array(img_rgb)
                img_cv2 = img_cv2[:, :, ::-1].copy()
                
            faces = app.get(img_cv2)
            found_vincent = False
            for face in faces:
                if is_vincent(face.normed_embedding, ref_embeddings):
                    found_vincent = True
                    break
                    
            if found_vincent:
                # Just tag it in the database so the AI knows Vincent is in the photo
                c.execute("UPDATE inventory SET has_vincent = 1 WHERE id = ?", (row_id,))
                moved_count += 1
                
                # Tag sidecars
                c.execute("SELECT id FROM inventory WHERE parent_id = ?", (row_id,))
                sidecars = c.fetchall()
                for (sid,) in sidecars:
                    c.execute("UPDATE inventory SET has_vincent = 1 WHERE id = ?", (sid,))
                                 
        except Exception as e:
            pass # ignore corrupt or unreadable images
            
    conn.commit()
    conn.close()
    print(f"\nFace filter complete! Found Vincent in {moved_count} photos. Database updated.")

if __name__ == "__main__":
    main()

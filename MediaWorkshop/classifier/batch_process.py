import sqlite3
import time
import argparse
from pathlib import Path
import logging
from tqdm import tqdm

from classify_hybrid import classify_with_ollama, classify_with_gemini
from taxonomy import requires_gemini_review

logging.basicConfig(level=logging.INFO, format='%(levelname)s: %(message)s')
DB_PATH = Path(__file__).parent / "state.sqlite"

def main():
    parser = argparse.ArgumentParser(description="Run batch processing of inventory using hybrid classification")
    parser.add_argument("--limit", type=int, default=None, help="Process max N images")
    parser.add_argument("--gemini-only", action="store_true", help="Skip Qwen and only use Gemini")
    args = parser.parse_args()
    
    if not DB_PATH.exists():
        logging.error("Database not found. Please run inventory.py first.")
        return
        
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    
    # Select images that are NOT processed, NOT flagged by nudenet (local_only=0), 
    # NOT sidecars and NOT videos. (We can handle videos separately).
    query = """
        SELECT id, file_path 
        FROM inventory 
        WHERE processed = 0 
          AND local_only = 0 
          AND is_sidecar = 0 
          AND is_live_video = 0
          AND extension IN ('.heic', '.jpg', '.jpeg', '.png')
        ORDER BY id ASC
    """
    if args.limit:
        query += f" LIMIT {args.limit}"
        
    c.execute(query)
    rows = c.fetchall()
    
    if not rows:
        logging.info("No unprocessed images found. All done!")
        return
        
    logging.info(f"Processing {len(rows)} images...")
    
    for row_id, path_str in tqdm(rows):
        path = Path(path_str)
        if not path.exists():
            logging.warning(f"File not found: {path}")
            continue
            
        qwen_cat = None
        qwen_conf = None
        qwen_json = None
        
        gemini_cat = None
        gemini_conf = None
        gemini_json = None
        
        final_domain = None
        final_category = None
        
        need_gemini = args.gemini_only
        
        if not args.gemini_only:
            result = classify_with_ollama(path)
            if result:
                qwen_cat = result.category.value
                qwen_conf = result.confidence
                qwen_json = result.model_dump_json()
                
                final_domain = result.domain.value
                final_category = result.category.value
                
                if requires_gemini_review(result):
                    need_gemini = True
            else:
                need_gemini = True
                
        if need_gemini:
            # We want to pause slightly to avoid API rate limits, but `google-genai` handles some
            gemini_result = classify_with_gemini(path)
            if gemini_result:
                gemini_cat = gemini_result.category.value
                gemini_conf = gemini_result.confidence
                gemini_json = gemini_result.model_dump_json()
                
                final_domain = gemini_result.domain.value
                final_category = gemini_result.category.value
            
            time.sleep(1) # simple rate limit buffer
            
        if final_domain is None:
            final_domain = "unknown"
            final_category = "unknown"
            
        c.execute("""
            UPDATE inventory 
            SET qwen_category = ?, qwen_confidence = ?, qwen_json = ?,
                gemini_category = ?, gemini_confidence = ?, gemini_json = ?,
                final_domain = ?, final_category = ?, processed = 1
            WHERE id = ?
        """, (
            qwen_cat, qwen_conf, qwen_json,
            gemini_cat, gemini_conf, gemini_json,
            final_domain, final_category, row_id
        ))
        
        conn.commit()
        
    conn.close()
    logging.info("Batch processing finished.")

if __name__ == "__main__":
    main()

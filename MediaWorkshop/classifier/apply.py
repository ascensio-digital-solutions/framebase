import sqlite3
import argparse
import json
import shutil
import os
from pathlib import Path

DB_PATH = Path(__file__).parent / "state.sqlite"
ROOT_DIR = Path("/Users/vincent/04_systems/media_workshop/iPhoto export 2010-2026")
JOURNAL_PATH = Path(__file__).parent / "journal.json"

def apply_moves():
    if not DB_PATH.exists():
        print("Database not found.")
        return
        
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    
    # We select processed images, plus quarantined (local_only)
    # Then we also select sidecars/videos and join on parent to get their destination
    
    c.execute("""
        SELECT id, file_path, year, final_domain, final_category, local_only
        FROM inventory
        WHERE is_sidecar = 0 AND is_live_video = 0 AND (processed = 1 OR local_only = 1)
    """)
    parents = c.fetchall()
    
    moves = []
    
    def get_dest_folder(year, domain, category, local_only):
        if local_only:
            return ROOT_DIR / str(year) / "quarantine"
        if not domain or not category:
            return ROOT_DIR / str(year) / "unsorted"
            
        # domain -> personal, category -> personal/home_daily
        # We just use category as it includes domain usually, or just replace / with OS sep
        cat_parts = category.split("/")
        return ROOT_DIR / str(year) / Path(*cat_parts)

    for pid, p_path_str, year, dom, cat, local_only in parents:
        p_path = Path(p_path_str)
        if not p_path.exists():
            continue
            
        dest_folder = get_dest_folder(year, dom, cat, local_only)
        dest_path = dest_folder / p_path.name
        
        if p_path != dest_path:
            moves.append((p_path, dest_path))
            
        # Now get its children (sidecars, live videos)
        c.execute("SELECT file_path FROM inventory WHERE parent_id = ?", (pid,))
        children = c.fetchall()
        for (c_path_str,) in children:
            c_path = Path(c_path_str)
            if c_path.exists():
                c_dest = dest_folder / c_path.name
                if c_path != c_dest:
                    moves.append((c_path, c_dest))
                    
    conn.close()
    
    if not moves:
        print("No files to move.")
        return
        
    print(f"Planning to move {len(moves)} files.")
    
    journal = []
    
    for src, dest in moves:
        if not src.exists():
            continue
        dest.parent.mkdir(parents=True, exist_ok=True)
        
        try:
            shutil.move(str(src), str(dest))
            journal.append({"src": str(src), "dest": str(dest)})
        except Exception as e:
            print(f"Failed to move {src} -> {dest}: {e}")
            
    # Save journal
    if journal:
        existing_journal = []
        if JOURNAL_PATH.exists():
            with open(JOURNAL_PATH, "r") as f:
                existing_journal = json.load(f)
        existing_journal.extend(journal)
        with open(JOURNAL_PATH, "w") as f:
            json.dump(existing_journal, f, indent=2)
            
    print(f"Successfully moved {len(journal)} files. Journal updated.")

def undo_moves():
    if not JOURNAL_PATH.exists():
        print("No journal found to undo.")
        return
        
    with open(JOURNAL_PATH, "r") as f:
        journal = json.load(f)
        
    if not journal:
        print("Journal is empty.")
        return
        
    print(f"Undoing {len(journal)} moves...")
    
    failed = []
    success = 0
    
    # Reverse order for safety
    for entry in reversed(journal):
        src = Path(entry["src"])
        dest = Path(entry["dest"])
        
        if dest.exists():
            src.parent.mkdir(parents=True, exist_ok=True)
            try:
                shutil.move(str(dest), str(src))
                success += 1
            except Exception as e:
                print(f"Failed to undo {dest} -> {src}: {e}")
                failed.append(entry)
        else:
            print(f"File missing at destination, cannot undo: {dest}")
            failed.append(entry)
            
    with open(JOURNAL_PATH, "w") as f:
        json.dump(failed, f, indent=2)
        
    print(f"Undo complete. {success} reverted, {len(failed)} failed (left in journal).")

if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--undo", action="store_true", help="Revert moves using journal.json")
    args = parser.parse_args()
    
    if args.undo:
        undo_moves()
    else:
        apply_moves()

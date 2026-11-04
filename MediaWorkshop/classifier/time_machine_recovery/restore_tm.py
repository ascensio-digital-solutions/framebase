import os
import shutil
import sys
from pathlib import Path

# Paths
TM_ROOT = "/Volumes/.timemachine/6CC2A3E1-D838-477D-B0FA-B5293811F212/2026-10-03-232339.backup/2026-10-03-232339.backup/Macintosh HD - Data/Users/vincent/04_systems/media_workshop/iPhoto export 2010-2026"
DEST_ROOT = "/Users/vincent/04_systems/media_workshop/iPhoto export 2010-2026"
MISSING_LIST = "/Users/vincent/04_systems/media_workshop/tools/photo_classifier/deleted_photos_list.txt"

def restore_missing_files():
    if not os.path.exists(TM_ROOT):
        print(f"ERROR: Cannot access Time Machine backup at {TM_ROOT}")
        print("Please ensure your Terminal app has Full Disk Access in System Settings > Privacy & Security.")
        sys.exit(1)
        
    print("Parsing missing files list...")
    missing_files = []
    current_year = None
    
    with open(MISSING_LIST, 'r') as f:
        for line in f:
            line = line.strip()
            if line.startswith("--- YEAR"):
                current_year = line.split(" ")[2]
            elif line and not line.startswith("Total"):
                if current_year:
                    missing_files.append((line, current_year))
                    
    print(f"Loaded {len(missing_files)} missing files to recover.")
    
    print("Scanning Time Machine backup (this may take a minute)...")
    tm_file_map = {}
    
    def walk_error(err):
        print(f"\nERROR reading Time Machine backup: {err}")
        print("This usually means Terminal does NOT have Full Disk Access.")
        print("Please go to System Settings > Privacy & Security > Full Disk Access, and ensure Terminal is toggled ON.")
        sys.exit(1)
        
    for root, dirs, files in os.walk(TM_ROOT, onerror=walk_error):
        # The year folder is directly under TM_ROOT, so we can extract it
        try:
            rel_path = os.path.relpath(root, TM_ROOT)
            year = rel_path.split(os.sep)[0] if rel_path != "." else None
        except Exception:
            year = None
            
        for name in files:
            # We map (filename, year) -> full TM path
            if year:
                tm_file_map[(name, year)] = os.path.join(root, name)
            
    print(f"Found {len(tm_file_map)} files in Time Machine backup.")
    
    print("Starting recovery...")
    recovered = 0
    not_found = 0
    
    for filename, year in missing_files:
        if (filename, year) in tm_file_map:
            source_path = tm_file_map[(filename, year)]
            dest_dir = os.path.join(DEST_ROOT, year)
            os.makedirs(dest_dir, exist_ok=True)
            dest_path = os.path.join(dest_dir, filename)
            
            try:
                # Force overwrite to fix any mismatches from previous run
                shutil.copy2(source_path, dest_path)
                recovered += 1
            except Exception as e:
                print(f"Failed to copy {filename}: {e}")
        else:
            print(f"Could not find {filename} (Year: {year}) in Time Machine backup.")
            not_found += 1
            
    print("\n--- Recovery Summary ---")
    print(f"Recovered: {recovered}")
    print(f"Not Found: {not_found}")
    print(f"Total Expected: {len(missing_files)}")
    print("------------------------")

if __name__ == "__main__":
    restore_missing_files()

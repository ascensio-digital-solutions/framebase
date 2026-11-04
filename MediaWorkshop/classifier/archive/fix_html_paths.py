import sqlite3
import re
from pathlib import Path
from urllib.parse import unquote, quote

DB_PATH = Path("/Users/vincent/04_systems/media_workshop/tools/photo_classifier/state.sqlite")
HTML_PATH = Path("/Users/vincent/04_systems/media_workshop/tools/photo_classifier/comparison_report.html")

def main():
    if not HTML_PATH.exists():
        print("HTML file not found.")
        return
        
    with open(HTML_PATH, "r", encoding="utf-8") as f:
        html = f.read()
        
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    
    # Find all image paths
    # <img src="file:///..."
    pattern = r'src="(file:///[^"]+)"'
    
    def replace_path(match):
        old_url = match.group(1)
        old_path_str = unquote(old_url.replace("file://", ""))
        filename = Path(old_path_str).name
        
        # Look up new path in DB
        c.execute("SELECT file_path FROM inventory WHERE filename = ?", (filename,))
        result = c.fetchone()
        if result:
            new_path_str = result[0]
            new_url = "file://" + quote(new_path_str)
            return f'src="{new_url}"'
        return match.group(0) # Keep old if not found
        
    # Also replace hrefs
    def replace_href(match):
        old_url = match.group(1)
        old_path_str = unquote(old_url.replace("file://", ""))
        filename = Path(old_path_str).name
        
        c.execute("SELECT file_path FROM inventory WHERE filename = ?", (filename,))
        result = c.fetchone()
        if result:
            new_path_str = result[0]
            new_url = "file://" + quote(new_path_str)
            return f'href="{new_url}"'
        return match.group(0)

    new_html = re.sub(pattern, replace_path, html)
    new_html = re.sub(r'href="(file:///[^"]+)"', replace_href, new_html)
    
    with open(HTML_PATH, "w", encoding="utf-8") as f:
        f.write(new_html)
        
    conn.close()
    print("Fixed HTML image paths!")

if __name__ == "__main__":
    main()

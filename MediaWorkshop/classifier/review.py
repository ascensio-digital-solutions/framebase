import sqlite3
import argparse
from pathlib import Path

DB_PATH = Path(__file__).parent / "state.sqlite"

HTML_TEMPLATE = """
<!DOCTYPE html>
<html>
<head>
    <title>Media Classification Review</title>
    <style>
        body { font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, Helvetica, Arial, sans-serif; background: #1a1a1a; color: #fff; margin: 20px; }
        .grid { display: flex; flex-wrap: wrap; gap: 10px; }
        .card { background: #2a2a2a; border-radius: 8px; padding: 10px; width: 250px; }
        img { width: 100%; height: auto; border-radius: 4px; }
        .label { font-size: 12px; margin-top: 5px; color: #aaa; word-break: break-all; }
        .domain { font-weight: bold; color: #4CAF50; }
        .business { color: #2196F3; }
        .quarantine { color: #F44336; }
        h2 { border-bottom: 1px solid #444; padding-bottom: 5px; margin-top: 40px; }
    </style>
</head>
<body>
    <h1>Classification Review</h1>
    <p>Review the categorized images below. Quarantine items are skipped and hidden.</p>
    
    {content}
</body>
</html>
"""

def generate_html(limit=500):
    if not DB_PATH.exists():
        print("Database not found.")
        return
        
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    
    c.execute("""
        SELECT final_domain, final_category, file_path, qwen_confidence, gemini_confidence 
        FROM inventory 
        WHERE processed = 1 AND local_only = 0
        ORDER BY final_domain, final_category, id
        LIMIT ?
    """, (limit,))
    
    rows = c.fetchall()
    
    # Group by category
    grouped = {}
    for r in rows:
        dom, cat, path, qconf, gconf = r
        if cat not in grouped:
            grouped[cat] = []
        grouped[cat].append((dom, path, qconf, gconf))
        
    content = ""
    for cat, items in grouped.items():
        content += f"<h2>Category: {cat}</h2>\n<div class='grid'>\n"
        for dom, path, qconf, gconf in items:
            dom_class = "business" if dom == "business" else "domain"
            
            # File URI for local viewing
            file_uri = Path(path).as_uri()
            
            # Show which model gave confidence
            conf_str = f"Q:{qconf}" if qconf else ""
            if gconf:
                conf_str += f" G:{gconf}"
                
            content += f"""
            <div class="card">
                <a href="{file_uri}" target="_blank">
                    <img src="{file_uri}" loading="lazy" />
                </a>
                <div class="label <span class='{dom_class}'>{dom}</span></div>
                <div class="label">{Path(path).name}</div>
                <div class="label">Conf: {conf_str}</div>
            </div>
            """
        content += "</div>\n"
        
    html = HTML_TEMPLATE.replace("{content}", content)
    out_path = Path("review.html")
    with open(out_path, "w") as f:
        f.write(html)
        
    print(f"Generated review.html with {len(rows)} images.")

if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--limit", type=int, default=1000)
    args = parser.parse_args()
    generate_html(args.limit)

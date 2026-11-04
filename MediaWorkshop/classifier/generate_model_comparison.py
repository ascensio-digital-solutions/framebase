import sqlite3
import json
import base64
import io
from pathlib import Path
from datetime import datetime
from PIL import Image
from pillow_heif import register_heif_opener

register_heif_opener()

DB_PATH = Path(__file__).parent / "state.sqlite"
REPORT_PATH = Path(__file__).parent / "model_comparison_report.html"

def generate_report():
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()

    c.execute("""
        SELECT 
            id, file_path, filename,
            gemini_category, gemini_confidence, gemini_json,
            qwen_category, qwen_confidence, qwen_json
        FROM inventory
        WHERE gemini_json IS NOT NULL AND qwen_json IS NOT NULL
        ORDER BY id ASC
    """)
    rows = c.fetchall()

    # Get overall counts
    c.execute("SELECT count(*) FROM inventory WHERE gemini_json IS NOT NULL")
    gemini_count = c.fetchone()[0]

    c.execute("SELECT count(*) FROM inventory WHERE qwen_json IS NOT NULL")
    qwen_count = c.fetchone()[0]

    c.execute("SELECT count(*) FROM inventory WHERE local_only = 0 AND is_sidecar = 0 AND is_live_video = 0")
    total_count = c.fetchone()[0]

    conn.close()

    both_count = len(rows)
    domain_matches = 0
    cat_matches = 0

    table_rows = []

    for row in rows:
        row_id, path_str, filename, g_cat, g_conf, g_json_str, q_cat, q_conf, q_json_str = row
        path = Path(path_str)

        g_data = json.loads(g_json_str) if g_json_str else {}
        q_data = json.loads(q_json_str) if q_json_str else {}

        g_domain = g_data.get("domain", "unknown")
        q_domain = q_data.get("domain", "unknown")

        same_domain = (g_domain == q_domain)
        same_cat = (g_cat == q_cat)

        if same_domain:
            domain_matches += 1
        if same_cat:
            cat_matches += 1

        # Generate small thumbnail
        img_src = ""
        if path.exists():
            try:
                with Image.open(path) as img:
                    img.thumbnail((240, 240), Image.Resampling.LANCZOS)
                    if img.mode != "RGB":
                        img = img.convert("RGB")
                    buf = io.BytesIO()
                    img.save(buf, format="JPEG", quality=75)
                    img_b64 = base64.b64encode(buf.getvalue()).decode('utf-8')
                    img_src = f"data:image/jpeg;base64,{img_b64}"
            except Exception:
                pass

        match_badge = "✅ MATCH" if same_cat else ("⚠️ SAME DOMAIN" if same_domain else "❌ MISMATCH")
        match_color = "#28a745" if same_cat else ("#ffc107" if same_domain else "#dc3545")

        g_rationale = g_data.get("rationale", "")
        q_rationale = q_data.get("rationale", "")

        g_tags = ", ".join(g_data.get("tags", []))
        q_tags = ", ".join(q_data.get("tags", []))

        table_rows.append(f"""
        <tr>
            <td style="text-align: center;">
                {f'<img src="{img_src}" style="max-width: 200px; max-height: 200px; border-radius: 6px; box-shadow: 0 2px 8px rgba(0,0,0,0.4);"/>' if img_src else ''}
                <div style="font-size: 11px; margin-top: 6px; color: #888;">{filename}</div>
                <div style="display: inline-block; padding: 2px 8px; border-radius: 12px; font-size: 11px; font-weight: bold; background: {match_color}; color: #fff; margin-top: 4px;">{match_badge}</div>
            </td>
            <td>
                <div style="font-size: 14px; font-weight: bold; color: #4dabf7;">{g_cat}</div>
                <div style="font-size: 12px; color: #aaa; margin: 4px 0;">Domain: <b>{g_domain}</b> | Conf: {g_conf:.2f}</div>
                <div style="font-size: 12px; color: #ddd; background: #222; padding: 6px; border-radius: 4px; margin-top: 4px;">{g_rationale}</div>
                <div style="font-size: 11px; color: #888; margin-top: 4px;">Tags: {g_tags}</div>
            </td>
            <td>
                <div style="font-size: 14px; font-weight: bold; color: #51cf66;">{q_cat}</div>
                <div style="font-size: 12px; color: #aaa; margin: 4px 0;">Domain: <b>{q_domain}</b> | Conf: {q_conf:.2f}</div>
                <div style="font-size: 12px; color: #ddd; background: #222; padding: 6px; border-radius: 4px; margin-top: 4px;">{q_rationale}</div>
                <div style="font-size: 11px; color: #888; margin-top: 4px;">Tags: {q_tags}</div>
            </td>
        </tr>
        """)

    domain_pct = (domain_matches / both_count * 100) if both_count > 0 else 0
    cat_pct = (cat_matches / both_count * 100) if both_count > 0 else 0

    html = f"""<!DOCTYPE html>
<html>
<head>
    <meta charset="utf-8">
    <title>Model Comparison: Gemini 2.5 Flash vs Qwen 3.8 (27B MLX)</title>
    <style>
        body {{ font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif; background: #121212; color: #eee; margin: 0; padding: 24px; }}
        h1 {{ margin-top: 0; color: #fff; }}
        .stats {{ display: flex; gap: 16px; margin: 20px 0; }}
        .card {{ background: #1e1e1e; border: 1px solid #333; border-radius: 8px; padding: 16px; min-width: 180px; }}
        .card .num {{ font-size: 28px; font-weight: bold; color: #fff; }}
        .card .label {{ font-size: 12px; color: #888; text-transform: uppercase; margin-top: 4px; }}
        table {{ width: 100%; border-collapse: collapse; margin-top: 24px; background: #181818; border-radius: 8px; overflow: hidden; }}
        th, td {{ border: 1px solid #2a2a2a; padding: 12px; vertical-align: top; }}
        th {{ background: #222; text-align: left; font-size: 13px; text-transform: uppercase; color: #aaa; }}
    </style>
</head>
<body>
    <h1>Vision Model Comparison Report</h1>
    <div style="color: #888; font-size: 13px;">Generated on {datetime.now().strftime("%Y-%m-%d %H:%M:%S")}</div>

    <div class="stats">
        <div class="card">
            <div class="num">{total_count:,}</div>
            <div class="label">Total Photos</div>
        </div>
        <div class="card">
            <div class="num" style="color: #4dabf7;">{gemini_count:,}</div>
            <div class="label">Gemini 2.5 Flash Processed</div>
        </div>
        <div class="card">
            <div class="num" style="color: #51cf66;">{qwen_count:,}</div>
            <div class="label">Qwen 3.8 Processed</div>
        </div>
        <div class="card">
            <div class="num">{both_count:,}</div>
            <div class="label">Overlap (Both Classified)</div>
        </div>
        <div class="card">
            <div class="num" style="color: #fcc419;">{cat_pct:.1f}%</div>
            <div class="label">Exact Category Match</div>
        </div>
        <div class="card">
            <div class="num" style="color: #fcc419;">{domain_pct:.1f}%</div>
            <div class="label">Domain Match</div>
        </div>
    </div>

    <table>
        <thead>
            <tr>
                <th style="width: 220px;">Image</th>
                <th style="width: 45%;">Gemini 2.5 Flash</th>
                <th style="width: 45%;">Qwen 3.8 (27B MLX Local)</th>
            </tr>
        </thead>
        <tbody>
            {''.join(table_rows)}
        </tbody>
    </table>
</body>
</html>
"""

    with open(REPORT_PATH, "w") as f:
        f.write(html)

    print(f"Report generated at: {REPORT_PATH} ({both_count} comparison pairs)")

if __name__ == "__main__":
    generate_report()

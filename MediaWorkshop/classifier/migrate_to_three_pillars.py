#!/usr/bin/env python3
"""
Migrate state.sqlite to the strict 3-Pillar Architecture:
1. Personal Life & Memories (domain: personal)
2. Core Business Operations (domain: business)
3. Knowledge & Swipe File (domain: knowledge)
Eliminates 'ambiguous' and rolls finances into personal bills or business operations.
"""

import sqlite3
import json
from pathlib import Path

DB_PATH = Path(__file__).parent / "state.sqlite"

def migrate():
    conn = sqlite3.connect(str(DB_PATH), timeout=60.0)
    c = conn.cursor()

    c.execute("""
        SELECT id, filename, gemini_category, gemini_json 
        FROM inventory 
        WHERE gemini_json IS NOT NULL
    """)
    rows = c.fetchall()

    print(f"Auditing {len(rows)} classified rows...")

    updated_count = 0
    counts = {"personal": 0, "business": 0, "knowledge": 0}

    for r_id, fn, cat, gjson in rows:
        try:
            d = json.loads(gjson)
        except Exception:
            continue

        dom = d.get("domain")
        rat = (d.get("rationale") or "").lower()
        tool = (d.get("subject_or_tool_discussed") or "").lower()
        tags_str = " ".join(d.get("tags", [])).lower()
        app = (d.get("app_name") or "").lower()
        full_text = f"{cat} {dom} {rat} {tool} {tags_str} {app}"

        # 1. Resolve domain (Eliminate ambiguous!)
        new_dom = dom
        if dom == "ambiguous" or dom is None:
            if any(k in full_text for k in [
                "design", "typography", "font", "palette", "color", "claude", "ai", 
                "prompt", "agent", "ui", "ux", "web", "marketing", "startup", 
                "branding", "developer", "code", "python", "software", "app", "tool",
                "carousel", "instagram", "hook", "conversion", "landing"
            ]) and "accidental" not in full_text and "blurry" not in full_text:
                new_dom = "knowledge"
            elif any(k in full_text for k in ["hair", "toupee", "swatch", "onehead", "bono", "shopify"]):
                new_dom = "business"
            else:
                new_dom = "personal"

        # 2. Resolve category under 3 pillars
        new_cat = cat

        # Eliminate standalone finances pillar
        if "finances" in str(cat):
            if any(k in full_text for k in ["medical", "prescription", "hospital", "doctor", "comparecimento"]):
                new_cat = "personal/health_medical"
                new_dom = "personal"
            elif any(k in full_text for k in ["saas", "stripe", "server", "business", "invoice", "company", "vps", "hostinger"]):
                new_cat = "business/operations"
                new_dom = "business"
            else:
                new_cat = "personal/bills_receipts"
                new_dom = "personal"

        # Route knowledge swipe file
        elif new_dom == "knowledge" or "screenshots/instagram" in str(cat):
            if any(k in full_text for k in ["hair", "toupee", "swatch", "onehead", "bono", "shopify"]):
                new_dom = "business"
                new_cat = "business/shopify" if "shopify" in full_text else "business/01_products"
            elif any(k in full_text for k in [
                "design", "typography", "font", "palette", "pantone", "color", "graphic", "branding", "logo",
                "ai", "claude", "prompt", "agent", "llm", "automation", "n8n", "chatgpt",
                "ui", "ux", "landing", "web design", "website", "hero",
                "marketing", "growth", "copy", "hook", "carousel", "ad", "startup",
                "code", "developer", "python", "swift", "github", "git", "api"
            ]) and "accidental" not in full_text and "blurry" not in full_text:
                new_dom = "knowledge"
                if any(k in full_text for k in ["ai", "claude", "prompt", "agent", "llm", "automation", "n8n", "chatgpt"]):
                    new_cat = "knowledge/ai_and_automation"
                elif any(k in full_text for k in ["ui", "ux", "landing", "web design", "website", "hero"]):
                    new_cat = "knowledge/ui_and_web_design"
                elif any(k in full_text for k in ["typography", "font", "palette", "pantone", "color", "graphic", "branding", "logo"]):
                    new_cat = "knowledge/design_and_branding"
                elif any(k in full_text for k in ["marketing", "growth", "copy", "hook", "carousel", "ad", "startup"]):
                    new_cat = "knowledge/marketing_and_growth"
                elif any(k in full_text for k in ["code", "developer", "python", "swift", "github", "git", "api"]):
                    new_cat = "knowledge/development_and_code"
                else:
                    new_cat = "knowledge/ai_and_automation"
            else:
                new_dom = "personal"
                new_cat = "personal/screenshots/other"

        # Update JSON record
        d["domain"] = new_dom
        d["category"] = new_cat

        if new_dom in counts:
            counts[new_dom] += 1

        new_json_str = json.dumps(d)
        c.execute("""
            UPDATE inventory 
            SET gemini_category = ?, gemini_json = ?
            WHERE id = ?
        """, (new_cat, new_json_str, r_id))
        updated_count += 1

    conn.commit()
    conn.close()

    print(f"\nMigration completed successfully for {updated_count} rows!")
    print("New 3-Pillar Distribution:")
    for k, v in counts.items():
        print(f"  Pillar {k.upper():12}: {v:5} ({v/updated_count*100:.1f}%)")

if __name__ == "__main__":
    migrate()


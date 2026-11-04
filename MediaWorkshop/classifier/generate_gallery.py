import json
from pathlib import Path

def generate_html(json_path, output_path):
    with open(json_path, 'r') as f:
        data = json.load(f)

    html = """
    <!DOCTYPE html>
    <html lang="en">
    <head>
        <meta charset="UTF-8">
        <meta name="viewport" content="width=device-width, initial-scale=1.0">
        <title>Deduplication Gallery</title>
        <script src="https://cdn.tailwindcss.com"></script>
        <style>
            body { background-color: #0f172a; color: #f8fafc; font-family: 'Inter', system-ui, sans-serif; }
            .img-container { position: relative; width: 100%; padding-top: 100%; overflow: hidden; border-radius: 0.75rem; background-color: #1e293b; border: 1px solid #334155; }
            .img-container img { position: absolute; top: 0; left: 0; width: 100%; height: 100%; object-fit: contain; }
            .filename { font-size: 0.8rem; color: #94a3b8; margin-top: 0.5rem; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; text-align: center;}
        </style>
    </head>
    <body class="p-4 md:p-8">
        <div class="max-w-7xl mx-auto">
            <h1 class="text-4xl md:text-5xl font-extrabold mb-2 bg-clip-text text-transparent bg-gradient-to-r from-blue-400 to-emerald-400">Deduplication Gallery</h1>
            <p class="text-slate-400 mb-10 text-lg">Review the deduplication groups detected by the 3-tier pipeline.</p>
    """

    def analyze_group(group, tier_title):
        filenames = [Path(p).name for p in group]
        lower_names = [f.lower() for f in filenames]
        
        # Check for Facetune
        if any("facetune" in f for f in lower_names):
            return "Likely a Facetune edit vs original photo."
            
        # Check for Screenshots
        if any("screen shot" in f or "screenshot" in f for f in lower_names):
            return "Likely a screenshot taken of another photo."
            
        # Check for duplicated downloads like (1)
        if any("(1)" in f or "(2)" in f or "copy" in f for f in lower_names):
            return "Likely a downloaded copy or sync duplicate."
            
        # Check for burst shots (sequential numbers)
        # Extract numbers from filenames if possible
        import re
        numbers = []
        for f in filenames:
            match = re.search(r'IMG_(\d+)', f, re.IGNORECASE)
            if match:
                numbers.append(int(match.group(1)))
        
        if len(numbers) > 1 and len(numbers) == len(filenames):
            numbers.sort()
            # Check if they are somewhat sequential
            if max(numbers) - min(numbers) <= len(numbers) + 5:
                return "Likely a burst or continuous shooting sequence."
                
        if "Tier 3" in tier_title:
            return "Semantic match: Visually identical or very similar."
        if "Tier 2" in tier_title:
            return "Near-duplicate: Minor crop, filter, or compression difference."
            
        return "Exact byte-for-byte duplicate."

    def render_section(title, description, groups, gradient_colors, tier_badge_color):
        if not groups:
            return ""
        
        section_html = f"""
            <div class="mb-16">
                <h2 class="text-3xl font-bold pb-2 mb-2 bg-clip-text text-transparent bg-gradient-to-r {gradient_colors}">{title}</h2>
                <p class="text-slate-400 mb-6 text-lg">{description} <span class="text-white font-semibold ml-2 bg-slate-800 px-3 py-1 rounded-full">{len(groups)} groups</span></p>
                <div class="space-y-8">
        """
        for i, group in enumerate(groups):
            analysis = analyze_group(group, title)
            section_html += f"""
                    <div class="bg-slate-800/50 backdrop-blur-sm rounded-2xl p-6 shadow-xl border border-slate-700/50">
                        <div class="flex items-center justify-between mb-4 border-b border-slate-700/50 pb-3">
                            <div class="flex items-center gap-3">
                                <h3 class="text-sm font-bold text-slate-300 uppercase tracking-widest">Match Group {i+1}</h3>
                                <span class="text-xs font-semibold {tier_badge_color} text-white px-3 py-1 rounded-full">{title.split(':')[0]}</span>
                            </div>
                            <span class="text-xs font-semibold bg-slate-700 text-slate-300 px-3 py-1 rounded-full">{len(group)} images</span>
                        </div>
                        <p class="text-sm text-slate-400 mb-4 italic">💡 {analysis}</p>
                        <div class="grid grid-cols-2 sm:grid-cols-3 md:grid-cols-4 lg:grid-cols-5 gap-6">
            """
            for path in group:
                file_url = f"file://{path}"
                filename = Path(path).name
                section_html += f"""
                            <div class="group">
                                <a href="{file_url}" target="_blank" class="block transition-all duration-300 transform group-hover:scale-[1.03] group-hover:shadow-2xl">
                                    <div class="img-container group-hover:border-slate-500 transition-colors">
                                        <img src="{file_url}" alt="{filename}" loading="lazy" onerror="this.src='data:image/svg+xml;base64,PHN2ZyB4bWxucz0iaHR0cDovL3d3dy53My5vcmcvMjAwMC9zdmciIHdpZHRoPSIxMDAlIiBoZWlnaHQ9IjEwMCUiPjxyZWN0IHdpZHRoPSIxMDAlIiBoZWlnaHQ9IjEwMCUiIGZpbGw9IiMzMzMiIC8+PHRleHQgeD0iNTAlIiB5PSI1MCUiIGZpbGw9IiNmZmYiIGZvbnQtZmFtaWx5PSJzYW5zLXNlcmlmIiBmb250LXNpemU9IjE0cHgiIGR5PSIuM2VtIiB0ZXh0LWFuY2hvcj0ibWlkZGxlIj5JbWFnZSBOb3QgRm91bmQ8L3RleHQ+PC9zdmc+'">
                                    </div>
                                </a>
                                <div class="filename" title="{filename}">{filename}</div>
                            </div>
                """
            section_html += """
                        </div>
                    </div>
            """
        section_html += """
                </div>
            </div>
        """
        return section_html
    html += render_section("Tier 1: Exact Duplicates", "Identical bytes matched using SHA-256.", data.get("exact_groups", []), "from-red-400 to-orange-400", "bg-red-500")
    html += render_section("Tier 2: Near Duplicates", "Minor edits, crops, and facetune matched using pHash.", data.get("near_groups", []), "from-amber-400 to-yellow-400", "bg-amber-500")

    html += """
        </div>
    </body>
    </html>
    """
    
    with open(output_path, 'w') as f:
        f.write(html)
        print(f"Generated {output_path}")
        
if __name__ == "__main__":
    import sys
    input_file = sys.argv[1] if len(sys.argv) > 1 else "deduplication_results.json"
    output_file = sys.argv[2] if len(sys.argv) > 2 else "gallery.html"
    generate_html(input_file, output_file)

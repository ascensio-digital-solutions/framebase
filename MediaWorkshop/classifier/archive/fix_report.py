import os
import re
from pathlib import Path
from tqdm import tqdm
from urllib.parse import unquote
from compare_models import classify_with_openrouter

def main():
    report_path = Path("comparison_report.html")
    with open(report_path, "r") as f:
        html = f.read()
        
    pattern = r'<img src="file://([^"]+)"'
    
    # Extract the HTML up to the start of the first row
    # We'll re-build the table from scratch with only 20 rows
    tr_pattern = r'(?s)<tr>.*?</tr>'
    tr_matches = list(re.finditer(tr_pattern, html))
    
    if not tr_matches:
        print("No table rows found in HTML.")
        return
        
    # Keep the header row
    header_tr = tr_matches[0].group(0)
    new_html = html[:tr_matches[0].start()] + header_tr
    
    limit = 20
    # Process only the first 20 rows
    for tr_match in tqdm(tr_matches[1:limit+1], desc="Running Space Bunny"):
        tr_block = tr_match.group(0)
        img_match = re.search(pattern, tr_block)
        if not img_match:
            new_html += "\n" + tr_block
            continue
            
        file_path = unquote(img_match.group(1))
        path = Path(file_path)
        
        sb_res = classify_with_openrouter(path, model="stealth/space-bunny-alpha")
        if "error" in sb_res:
            sb_html = f"<td><span class='error'>Error: {sb_res['error']}</span></td>"
        else:
            sb_html = f"<td><div class='json-block'>{sb_res['result'].model_dump_json(indent=2)}</div></td>"
            
        # Replace the Space Bunny cell. 
        # Since the cell might already have Space Bunny output (if the previous script ran on it),
        # or it might have the 404 error, we replace the entire third <td> tag.
        # Find the 3 <td> blocks in the tr_block
        td_pattern = r'(?s)<td>.*?</td>'
        td_matches = list(re.finditer(td_pattern, tr_block))
        if len(td_matches) >= 3:
            # Replace the 3rd <td> (index 2)
            third_td = td_matches[2].group(0)
            tr_block = tr_block.replace(third_td, sb_html, 1)
        
        new_html += "\n" + tr_block
        
    new_html += "\n</table>\n</body>\n</html>"
    
    with open(report_path, "w") as f:
        f.write(new_html)
        
    print(f"Report updated with {limit} images!")

if __name__ == "__main__":
    main()

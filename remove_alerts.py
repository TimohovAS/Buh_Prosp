import os
import re

src_dir = r"d:\Work\Programming\Buh_Prosp\frontend\src"

def process_file(path):
    with open(path, "r", encoding="utf-8") as f:
        content = f.read()

    # We want to replace alert(err.message) and alert(e.message) with console.error(...)
    new_content = re.sub(r"alert\(err\.message\)", "console.error(err)", content)
    new_content = re.sub(r"alert\(e\.message\)", "console.error(e)", new_content)
    
    # Also replace .catch((err) => alert(...)) if it's written in one line
    new_content = re.sub(r"\.catch\(\(e\)\s*=>\s*alert\(e\.message\)\)", ".catch(console.error)", new_content)
    new_content = re.sub(r"\.catch\(\(err\)\s*=>\s*alert\(err\.message\)\)", ".catch(console.error)", new_content)

    if new_content != content:
        with open(path, "w", encoding="utf-8") as f:
            f.write(new_content)
        print(f"Updated {path}")

for root, _, files in os.walk(src_dir):
    for f in files:
        if f.endswith(".jsx") or f.endswith(".js"):
            process_file(os.path.join(root, f))

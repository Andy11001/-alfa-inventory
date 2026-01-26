import csv
import requests
import re
import os
import json
from concurrent.futures import ThreadPoolExecutor

INPUT_CSV = os.path.join("data", "ds_model_feed.csv")
OUTPUT_JSON = os.path.join("data", "ds_versions_map.json")

# Regex patterns to find LCDV/Version codes
PATTERNS = [
    r"lcdv16=([A-Z0-9]{16})",
    r"vehicleVersionId\s*=\s*['\"]([A-Z0-9]{16})['\"]",
    r"versionCode\s*:\s*['\"]([A-Z0-9]{16})['\"]",
    r"derivedModel\s*:\s*['\"]([A-Z0-9]+)['\"]" # Sometimes useful fallback
]

def fetch_lcdv(model_name, url):
    print(f"🌐 Fetching {model_name}...")
    try:
        headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"}
        r = requests.get(url, headers=headers, timeout=10)
        content = r.text
        
        found_codes = []
        for p in PATTERNS:
            matches = re.findall(p, content)
            found_codes.extend(matches)
            
        # Filter for 16-char codes (standard LCDV)
        valid_lcdvs = [c for c in found_codes if len(c) == 16]
        
        if valid_lcdvs:
            # Pick the most frequent one or the first one
            best_code = max(set(valid_lcdvs), key=valid_lcdvs.count)
            print(f"   ✅ {model_name}: Found {best_code}")
            return model_name, best_code
        else:
            print(f"   ⚠️ {model_name}: No 16-char LCDV found. (Found partials: {found_codes[:3]})")
            return model_name, None

    except Exception as e:
        print(f"   ❌ {model_name}: Error {e}")
        return model_name, None

def main():
    if not os.path.exists(INPUT_CSV):
        print("Missing input CSV.")
        return

    tasks = []
    with open(INPUT_CSV, "r", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for row in reader:
            tasks.append((row["title"], row["url"]))

    results = {}
    with ThreadPoolExecutor(max_workers=5) as executor:
        futures = [executor.submit(fetch_lcdv, t[0], t[1]) for t in tasks]
        for f in futures:
            model, code = f.result()
            if code:
                results[model] = code
    
    # Save mapping
    with open(OUTPUT_JSON, "w", encoding="utf-8") as f:
        json.dump(results, f, indent=2)
    
    print(f"\nSaved {len(results)} version codes to {OUTPUT_JSON}")

if __name__ == "__main__":
    main()

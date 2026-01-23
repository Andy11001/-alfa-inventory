import requests
import re

url = "https://sklep.dsautomobiles.pl/sklep/"
try:
    r = requests.get(url, headers={"User-Agent": "Mozilla/5.0"})
    
    print("Searching for JSON/API patterns...")
    
    # 1. Search for JSON file references
    json_files = re.findall(r'[\w\-\/]+\.json', r.text)
    if json_files:
        print("Found JSON files:", json_files[:5])
        
    # 2. Search for wp-json (WordPress API)
    if "wp-json" in r.text:
        print("Found 'wp-json' -> Likely WordPress")
        
    # 3. Search for AJAX endpoints
    ajax_calls = re.findall(r'url\s*:\s*["\']([^"\\]+)["\\]', r.text)
    if ajax_calls:
        print("Found AJAX calls:", ajax_calls[:5])

except Exception as e:
    print(e)

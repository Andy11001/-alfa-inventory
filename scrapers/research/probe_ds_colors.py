import requests
from bs4 import BeautifulSoup
import json
import re

URL = "https://www.dsautomobiles.pl/gama/dsn4/kolekcja/dsn4-ds-performance-line.html"

def probe():
    print(f"Fetching {URL}...")
    r = requests.get(URL, headers={"User-Agent": "Mozilla/5.0"})
    if r.status_code != 200:
        print("Failed to fetch")
        return

    soup = BeautifulSoup(r.text, 'html.parser')
    
    # 1. Check for WlConfigurator
    configurators = soup.find_all(attrs={"data-app-wl": "WlConfigurator"})
    print(f"Found {len(configurators)} WlConfigurator components")
    
    # 2. Check for other components that might have color info
    # e.g. WlVisualizer
    visualizers = soup.find_all(attrs={"data-app-wl": re.compile(r"Wl.*")})
    for v in visualizers:
        name = v.get("data-app-wl")
        if name != "WlUnifiedHeader" and name != "WlFooter":
            print(f"Found Component: {name}")

    # 3. Look for color names in text
    print("\nScanning for color keywords in scripts...")
    scripts = soup.find_all("script")
    for s in scripts:
        if s.string and "color" in s.string.lower() and "ds" in s.string.lower():
             print(f"Found 'color' in script (len {len(s.string)})")
             print(s.string[:500])

if __name__ == "__main__":
    probe()
import requests
from bs4 import BeautifulSoup
import re
import json
import os
import csv
import time
from urllib.parse import urlparse, parse_qs, urljoin

# Paths
DATA_DIR = os.path.join(os.path.dirname(os.path.dirname(__file__)), "data")
MODEL_FEED_FILE = os.path.join(DATA_DIR, "ds_model_feed.csv")
OUTPUT_JSON = os.path.join(DATA_DIR, "ds_colors.json")
OUTPUT_CSV = os.path.join(DATA_DIR, "ds_color_feed.csv")

# Configuration
HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36"
}

def get_cached_path(url):
    """Generates a local filename for a URL to avoid re-downloading."""
    filename = url.replace("https://www.dsautomobiles.pl/", "").replace("/", "_").replace(".html", "") + ".html"
    return os.path.join(os.path.dirname(__file__), "cache", filename)

def extract_colors_from_html(html_content, model_url):
    """Parses HTML to find 3D visualizer data and colors."""
    soup = BeautifulSoup(html_content, 'html.parser')
    colors = {}
    base_version = None

    # 1. Look into ALL data-props for ANY app
    all_apps = soup.find_all("div", attrs={"data-props": True})
    for app in all_apps:
        try:
            props = json.loads(app.get("data-props", "{}"))
            
            # WlPreConfiguredOffers pattern
            offers = props.get("offers", [])
            for offer in offers:
                ver = offer.get("version")
                col_code = offer.get("color")
                if ver and not base_version: base_version = ver
                if col_code and col_code not in colors:
                    colors[col_code] = {"name": "Standard", "code": col_code, "version": ver}
            
            # Check for lcdv values in props
            for key in ["lcdv16", "lcdv", "version"]:
                if props.get(key) and not base_version:
                    base_version = props.get(key)

        except: pass

    # 2. Strategy: Regular expressions for visuel3d strings
    v3d_matches = re.findall(r"https://visuel3d-secure\.citroen\.com/V3DImage\.ashx\?[^\"' ]+", html_content)
    for url in v3d_matches:
        parsed = urlparse(url.replace("&amp;", "&"))
        qs = parse_qs(parsed.query)
        ver = qs.get("version", [None])[0]
        col_code = qs.get("color", [None])[0]
        if ver and not base_version: base_version = ver
        if col_code and col_code not in colors:
            colors[col_code] = {"code": col_code, "version": ver, "name": "Color"}

    # 3. Strategy: Look for lcdv16 in links (common in newsletter/configurator links)
    if not base_version:
        lcdv_match = re.search(r"lcdv16=([A-Z0-9]{16})", html_content)
        if lcdv_match:
            base_version = lcdv_match.group(1)

    # 4. Strategy: Look for Color Thumbnails
    thumbnails = soup.find_all("img", src=re.compile(r"Colors/DS_GenericThumbnailsV2"))
    if not thumbnails:
        thumbnails = soup.find_all("img", attrs={"data-src": re.compile(r"Colors/DS_GenericThumbnailsV2")})

    for thumb in thumbnails:
        src = thumb.get("src") or thumb.get("data-src")
        name = thumb.get("title") or thumb.get("alt")
        if not src: continue
        match = re.search(r"\/([A-Z0-9]+)\.png", src)
        if match:
            code = match.group(1)
            name = name.strip() if name else "Color"
            if code not in colors:
                colors[code] = {"name": name, "code": code, "version": base_version}
            else:
                if name and name != "Color": colors[code]["name"] = name

    # If we found no colors but found a base_version, try to look for a configurator link
    if not colors and base_version:
        # Some models might only have one color or hide them in sub-pages
        pass

    return colors

def fetch_or_read(url):
    """Fetches a URL or reads it from local cache/file."""
    # Mapping for debug files
    debug_map = {
        "https://www.dsautomobiles.pl/gama/ds-7/kolekcja/ds7-ds-performance-line.html": "ds7_perf_debug.html",
        "https://www.dsautomobiles.pl/gama/ds-4/diesel-petrol.html": "ds4_diesel_debug.html",
        "https://www.dsautomobiles.pl/gama/ds-7/konfigurator.html": "ds7_conf_debug.html",
        "https://www.dsautomobiles.pl/gama/ds-4/konfigurator.html": "ds4_conf_debug.html"
    }
    
    if url in debug_map and os.path.exists(debug_map[url]):
        print(f"📖 Reading debug file: {debug_map[url]}")
        with open(debug_map[url], "r", encoding="utf-8") as f:
            return f.read()

    # Special mapping for files we already know exist in root
    filename = url.split("/")[-1]
    root_path = os.path.join(os.path.dirname(os.path.dirname(__file__)), filename)
    
    if os.path.exists(root_path):
        print(f"📖 Reading local file: {root_path}")
        with open(root_path, "r", encoding="utf-8") as f:
            return f.read()

    # Otherwise fetch
    print(f"🌐 Fetching: {url}")
    try:
        r = requests.get(url, headers=HEADERS, timeout=10)
        if r.status_code == 200:
            return r.text
        else:
            print(f"❌ Failed to fetch {url}: {r.status_code}")
            return None
    except Exception as e:
        print(f"❌ Error fetching {url}: {e}")
        return None

def generate_image_url(version, color_code):
    """Constructs a high-quality image URL for the car."""
    # View 001 is typically Front-Left 3/4
    return f"https://visuel3d-secure.citroen.com/V3DImage.ashx?client=DI1&version={version}&color={color_code}&width=1200&ratio=1&view=001&format=jpg&quality=95"

def main():
    if not os.path.exists(MODEL_FEED_FILE):
        print("❌ Model feed not found. Run ds_model.py first.")
        return

    print("🎨 Starting DS Color Extraction...")
    
    # Read models from feed
    models_to_process = []
    with open(MODEL_FEED_FILE, "r", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for row in reader:
            models_to_process.append(row)

    all_colors_data = {} # { "Model Name": [ {color_data}... ] }
    csv_rows = []

    processed_urls = set()

    for model in models_to_process:
        url = model["url"]
        title = model["title"]
        
        if url in processed_urls: continue
        processed_urls.add(url)
        
        print(f"\n🚗 Processing: {title}")
        html = fetch_or_read(url)
        
        if not html:
            print("   ⚠️ No HTML content.")
            continue
            
        extracted_colors = extract_colors_from_html(html, url)
        
        if extracted_colors:
            print(f"   ✅ Found {len(extracted_colors)} colors.")
            model_colors_list = []
            
            for code, data in extracted_colors.items():
                version = data.get("version")
                # Fallback version if missing (try to infer or skip image gen)
                img_link = ""
                if version:
                    img_link = generate_image_url(version, code)
                
                color_entry = {
                    "model": title,
                    "color_name": data["name"],
                    "color_code": code,
                    "version_code": version,
                    "image_url": img_link,
                    "source_url": url
                }
                model_colors_list.append(color_entry)
                
                csv_rows.append(color_entry)
                print(f"      - {data['name']} ({code})")
            
            all_colors_data[title] = model_colors_list
        else:
            print("   ⚠️ No colors found on this page.")

    # Save JSON
    with open(OUTPUT_JSON, "w", encoding="utf-8") as f:
        json.dump(all_colors_data, f, indent=4, ensure_ascii=False)
    print(f"\n✅ Saved JSON to {OUTPUT_JSON}")

    # Save CSV
    if csv_rows:
        keys = csv_rows[0].keys()
        with open(OUTPUT_CSV, "w", encoding="utf-8", newline="") as f:
            writer = csv.DictWriter(f, fieldnames=keys)
            writer.writeheader()
            writer.writerows(csv_rows)
        print(f"✅ Saved CSV to {OUTPUT_CSV}")

if __name__ == "__main__":
    main()

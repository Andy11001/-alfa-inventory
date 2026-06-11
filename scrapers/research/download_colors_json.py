import json
import os
import sys
import requests
import re

# Import process_image logic
sys.path.append(os.path.dirname(os.path.dirname(__file__)))
from scrapers.image_processor import process_image

DATA_DIR = os.path.join(os.path.dirname(os.path.dirname(__file__)), "data")
COLORS_JSON = os.path.join(DATA_DIR, "ds_colors.json")
IMAGES_DIR = os.path.join(DATA_DIR, "images")

COLOR_CONFIG = {
    "White Pearl": (242, 242, 242),
    "Blanc Banquise": (242, 242, 242),
    "Perla Nera Black": (26, 26, 26),
    "Cristal Pearl": (209, 205, 197),
    "Crystal Pearl": (209, 205, 197),
    "Cashmere": (118, 121, 130),
    "Night Flight": (62, 65, 73),
    "Lazurite Blue": (0, 107, 125),
    "Sapphire Blue": (0, 60, 125),
    "Titanium Grey": (100, 100, 100),
    "Lacquered Grey": (120, 120, 120),
    "Palladium Grey": (128, 128, 128),
    "Topaz Blue": (0, 100, 150),
    "Alabaster White": (240, 240, 240)
}
DEFAULT_BORDER = (181, 162, 152)

def get_border_color(color_name):
    if color_name in COLOR_CONFIG:
        return COLOR_CONFIG[color_name]
    for key, val in COLOR_CONFIG.items():
        if key in color_name:
            return val
    return DEFAULT_BORDER

def normalize_model_name_for_filename(model_name):
    """
    DS N°4 HYBRID -> DSN4HYBRID
    DS 3 E-TENSE -> DS3ETENSE
    """
    name = model_name.upper()
    name = name.replace("N°", "N").replace(" ", "").replace("-", "")
    return name

def main():
    if not os.path.exists(COLORS_JSON):
        print("❌ ds_colors.json not found!")
        return

    os.makedirs(IMAGES_DIR, exist_ok=True)
    
    with open(COLORS_JSON, 'r', encoding='utf-8') as f:
        data = json.load(f)

    print(f"📂 Loaded {len(data)} models from JSON.")
    
    total_downloaded = 0
    total_skipped = 0

    for model_name, variants in data.items():
        model_part = normalize_model_name_for_filename(model_name)
        
        for variant in variants:
            color_code = variant.get("color_code")
            color_name = variant.get("color_name", "Unknown")
            img_url = variant.get("image_url")

            if not color_code or not img_url:
                continue

            filename = f"{model_part}_{color_code}.jpg"
            output_path = os.path.join(IMAGES_DIR, filename)

            if os.path.exists(output_path):
                total_skipped += 1
                continue

            print(f"⬇️ Downloading {filename} ({color_name})...")
            
            border = get_border_color(color_name)
            if process_image(img_url, output_path, border_color_rgb=border):
                total_downloaded += 1
            else:
                print(f"❌ Failed to download/process {filename}")

    print(f"\n✅ Done. Downloaded: {total_downloaded}, Skipped: {total_skipped}")

if __name__ == "__main__":
    main()

import csv
import os
import sys

# Add parent directory to path to import image_processor
sys.path.append(os.path.dirname(os.path.dirname(__file__)))
from scrapers.image_processor import process_image

DATA_DIR = os.path.join(os.path.dirname(os.path.dirname(__file__)), "data")
INPUT_CSV = os.path.join(DATA_DIR, "ds_color_feed.csv")
IMAGES_DIR = os.path.join(DATA_DIR, "images")

# Color mapping for borders
COLOR_CONFIG = {
    "White Pearl": (242, 242, 242),
    "Blanc Banquise": (242, 242, 242),
    "Perla Nera Black": (26, 26, 26),
    "Cristal Pearl": (209, 205, 197),
    "Crystal Pearl": (209, 205, 197),
    "Cashmere": (118, 121, 130),
    "Night Flight": (62, 65, 73),
    "Lazurite Blue": (0, 107, 125),
    "Sapphire Blue": (0, 60, 125), # Guess
    "Titanium Grey": (100, 100, 100), # Guess
    "Lacquered Grey": (120, 120, 120), # Guess
    "Palladium Grey": (128, 128, 128), # Guess
    "Topaz Blue": (0, 100, 150), # Guess
    "Alabaster White": (240, 240, 240) # Guess
}

DEFAULT_BORDER = (181, 162, 152) # DS Champagne/Beige

def get_border_color(color_name):
    # Try exact match
    if color_name in COLOR_CONFIG:
        return COLOR_CONFIG[color_name]
    
    # Try partial match
    for key, val in COLOR_CONFIG.items():
        if key in color_name:
            return val
            
    return DEFAULT_BORDER

def main():
    if not os.path.exists(INPUT_CSV):
        print("❌ ds_color_feed.csv not found. Run extract_ds_colors.py first.")
        return

    os.makedirs(IMAGES_DIR, exist_ok=True)

    print("🖼️ Starting DS Image Download...")
    
    with open(INPUT_CSV, "r", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        rows = list(reader)

    processed_count = 0
    updated_rows = []
    
    for row in rows:
        url = row.get("image_url")
        model = row.get("model")
        color_name = row.get("color_name")
        color_code = row.get("color_code")
        
        if not url:
            row["local_image_path"] = ""
            updated_rows.append(row)
            continue
            
        # Create a safe filename: DS_[Model]_[ColorCode].jpg
        safe_model = model.replace(" ", "").replace("°", "").replace("-", "")
        filename = f"{safe_model}_{color_code}.jpg"
        output_path = os.path.join(IMAGES_DIR, filename)
        row["local_image_path"] = f"images/{filename}"
        
        if os.path.exists(output_path):
            # print(f"⏩ Skipping {filename} (exists)")
            updated_rows.append(row)
            continue
            
        print(f"⬇️ Downloading {filename} ({color_name})...")
        border = get_border_color(color_name)
        
        if process_image(url, output_path, border_color_rgb=border):
            processed_count += 1
        else:
            print(f"❌ Failed to process {filename}")
        
        updated_rows.append(row)

    print(f"\n✅ Finished. Processed {processed_count} new images.")
    
    # Save final CSV
    FINAL_CSV = os.path.join(DATA_DIR, "ds_model_colors_final.csv")
    if updated_rows:
        fieldnames = list(updated_rows[0].keys())
        with open(FINAL_CSV, "w", encoding="utf-8", newline="") as f:
            writer = csv.DictWriter(f, fieldnames=fieldnames)
            writer.writeheader()
            writer.writerows(updated_rows)
        print(f"✅ Saved final feed to {FINAL_CSV}")

if __name__ == "__main__":
    main()

import csv
import os

DATA_DIR = os.path.join(os.path.dirname(os.path.dirname(__file__)), "data")
MODEL_FEED_CSV = os.path.join(DATA_DIR, "ds_model_feed.csv")
COLORS_CSV = os.path.join(DATA_DIR, "ds_model_colors_final.csv")
OUTPUT_CSV = os.path.join(DATA_DIR, "ds_model_colors_complete.csv")

def main():
    if not os.path.exists(MODEL_FEED_CSV) or not os.path.exists(COLORS_CSV):
        print("❌ Missing input files.")
        return

    # 1. Load Colors
    # Key: "DS 4 DIESEL" -> [color_row1, color_row2...]
    colors_by_model = {}
    
    with open(COLORS_CSV, "r", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for row in reader:
            model = row["model"]
            if model not in colors_by_model:
                colors_by_model[model] = []
            colors_by_model[model].append(row)

    print(f"🎨 Loaded verified colors for {len(colors_by_model)} models.")

    # 2. Iterate Models and Join
    final_rows = []
    
    with open(MODEL_FEED_CSV, "r", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        all_models = list(reader)

    print(f"🔄 Processing {len(all_models)} models from feed...")

    mapped_count = 0
    missing_count = 0

    for model_row in all_models:
        model_name = model_row["title"]
        
        if model_name in colors_by_model:
            # We have verified colors for this specific model
            model_colors = colors_by_model[model_name]
            # print(f"   ✅ {model_name}: Found {len(model_colors)} colors.")
            
            for color_row in model_colors:
                # Merge logic: Start with color data, add model data
                new_row = color_row.copy()
                # Add price/url info from model feed
                new_row["price_brutto"] = model_row["price_brutto"]
                new_row["installment_netto"] = model_row["installment_netto"]
                new_row["url"] = model_row["url"]
                new_row["disclaimer"] = model_row["disclaimer"]
                
                final_rows.append(new_row)
            mapped_count += 1
        else:
            print(f"   ⚠️ {model_name}: No verified colors found. Skipping.")
            missing_count += 1

    # 3. Write Output
    if final_rows:
        # Determine all fieldnames
        all_keys = set().union(*(d.keys() for d in final_rows))
        # Sort reasonably: model, color info, then price info
        ordered_keys = ["model", "color_name", "color_code", "local_image_path", "price_brutto", "installment_netto", "url"]
        remaining_keys = [k for k in all_keys if k not in ordered_keys]
        fieldnames = ordered_keys + remaining_keys
        
        with open(OUTPUT_CSV, "w", encoding="utf-8", newline="") as f:
            writer = csv.DictWriter(f, fieldnames=fieldnames)
            writer.writeheader()
            writer.writerows(final_rows)
        print(f"\n✅ Saved complete color feed to {OUTPUT_CSV} ({len(final_rows)} rows).")
        print(f"   Matched Models: {mapped_count}")
        print(f"   Models without colors: {missing_count}")
    else:
        print("\n❌ No rows generated. Check model name matching.")

if __name__ == "__main__":
    main()


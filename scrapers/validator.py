import os
import pandas as pd
import sys

DATA_DIR = os.path.join(os.path.dirname(os.path.dirname(__file__)), 'data')

def validate_csv(file_name):
    file_path = os.path.join(DATA_DIR, file_name)
    print(f"Validating {file_path}...")
    
    if not os.path.exists(file_path):
        print(f"❌ File not found: {file_path}")
        return

    try:
        df = pd.read_csv(file_path)
        print(f"✅ File loaded. Rows: {len(df)}")
        
        required_cols = ["vehicle_id", "price", "image_link"]
        missing_cols = [c for c in required_cols if c not in df.columns]
        
        if missing_cols:
            print(f"❌ Missing columns: {missing_cols}")
        else:
            print("✅ Critical columns present.")
            
        # Check for empty vehicle_ids
        empty_ids = df[df['vehicle_id'].isna() | (df['vehicle_id'] == '')]
        if not empty_ids.empty:
             print(f"❌ Found {len(empty_ids)} rows with empty vehicle_id.")
        else:
             print("✅ All vehicle_ids are present.")

    except Exception as e:
        print(f"❌ Error reading CSV: {e}")

if __name__ == "__main__":
    print("--- Validation Report ---")
    validate_csv("alfa_romeo_inventory.csv")
    validate_csv("ds_inventory.csv")
    # Add model files here when ready

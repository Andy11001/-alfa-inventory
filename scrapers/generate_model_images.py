import csv
import json
import os
import requests
import re

# Pliki wejściowe
FEED_FILE = os.path.join(os.path.dirname(os.path.dirname(__file__)), "data", "alfa_model_feed.csv")
MAPPING_FILE = os.path.join(os.path.dirname(os.path.dirname(__file__)), "data", "model_version_mapping.json")
CODES_FILE = os.path.join(os.path.dirname(os.path.dirname(__file__)), "data", "alfa_codes.json")

# Plik wyjściowy (rozszerzony feed)
OUTPUT_FILE = os.path.join(os.path.dirname(os.path.dirname(__file__)), "data", "alfa_model_variants.csv")

# Bazowy URL do obrazków (uproszczony, bez zbędnych opcji na start)
# view=EXT (zewnątrz), angle=1 (przód-bok), width=1200 (HD)
IMG_BASE_URL = "https://lb.assets.fiat.com/vl-picker-service/rest/getImage?brand=83&view=EXT&angle=1&resolution=BIG&width=1200&height=675"

def load_json(path):
    with open(path, 'r', encoding='utf-8') as f:
        return json.load(f)

def find_tech_codes(model_name, trim_name, mapping):
    """
    Szuka kodów technicznych (MVSS) pasujących do nazwy modelu i wersji.
    """
    # 1. Znajdź ID modelu (np. 626 dla Junior)
    model_ids = []
    
    # Normalizacja nazw do szukania
    target_model = model_name.upper().replace("ALFA ROMEO", "").strip()
    target_trim = trim_name.upper().strip()
    
    # Mapowanie nazw handlowych modeli na ID (proste reguły)
    model_name_map = {
        "JUNIOR": ["626", "627"], # Ibrida, Elettrica
        "TONALE": ["622", "638"], # MHEV, PHEV
        "GIULIA": ["620"],
        "STELVIO": ["630"]
    }
    
    candidates = model_name_map.get(target_model, [])
    
    # Szukamy pasującej wersji w kandydatach
    for mid in candidates:
        if mid in mapping:
            versions = mapping[mid]
            for key, name in versions.items():
                if key.startswith("_"): continue # pomiń metadane
                
                # Porównanie nazw wersji (np. "Sprint" == "Sprint")
                # Używamy "in" bo czasem jest "Ibrida Sprint" vs "Sprint"
                if target_trim in name.upper() or name.upper() in target_trim:
                    # Mamy dopasowanie!
                    # key format: Version|Series|Special
                    parts = key.split("|")
                    mvss = f"83{mid}{parts[0]}{parts[1]}{parts[2]}"
                    
                    # Domyślne felgi i wnętrze (można by je też mapować, ale na razie hardcode dla bezpieczeństwa)
                    # Junior ma specyficzne kody, inne modele inne.
                    # Bierzemy "bezpieczne" defaults lub puste (API samo dobierze domyślne dla MVSS)
                    return mvss, mid
    
    return None, None

def main():
    print("Generowanie wariantów kolorystycznych dla feedu modelowego...")
    
    feed_rows = []
    with open(FEED_FILE, 'r', encoding='utf-8') as f:
        reader = csv.DictReader(f)
        feed_rows = list(reader)
        
    mapping = load_json(MAPPING_FILE)
    codes = load_json(CODES_FILE)
    colors = codes.get("colors", {})
    
    # Wybrane kolory do sprawdzenia (żeby nie generować 1000 kombinacji na start)
    # Możemy wziąć wszystkie z codes.json, ale część może nie pasować do modelu.
    # API zwróci obrazek tak czy siak (często defaultowy biały jeśli kod błędny).
    
    variants = []
    
    total_generated = 0
    
    for row in feed_rows:
        title = row['title']
        # Parsowanie tytułu: "Alfa Romeo JUNIOR SPRINT" -> Model: JUNIOR, Wersja: SPRINT
        clean_t = title.replace("Alfa Romeo ", "").strip()
        parts = clean_t.split(" ", 1)
        
        if len(parts) < 2:
            print(f"Pominięto (format nazwy): {title}")
            continue
            
        model_name = parts[0] # JUNIOR
        trim_name = parts[1]  # SPRINT
        
        mvss, model_id = find_tech_codes(model_name, trim_name, mapping)
        
        if not mvss:
            print(f"Nie znaleziono mapowania MVSS dla: {model_name} {trim_name}")
            continue
            
        print(f"Przetwarzanie: {title} -> MVSS: {mvss}")
        
        # Generujemy wariant dla każdego znanego koloru
        for color_code, color_name in colors.items():
            # Budowanie URL
            # Dodajemy `sa=1` (Smart Availability) - czasem pomaga dobrać brakujące opcje
            img_url = f"{IMG_BASE_URL}&model={model_id}1&mmvs={mvss}&body={color_code}"
            
            # Dodatkowe parametry dla Juniora (z linku użytkownika), żeby koła i środek nie zniknęły
            if model_id in ["626", "627"]:
                 # Domyślne koła i wnętrze dla Juniora, żeby wyglądał "pełnie"
                 img_url += "&wheel=1M3&seat=033" 
            
            variant = row.copy()
            variant["mvss"] = mvss
            variant["color_code"] = color_code
            variant["color_name"] = color_name
            variant["image_link"] = img_url
            
            # Unikalne ID wariantu
            variant["variant_id"] = f"{row['vehicle_id']}-{color_code}"
            
            variants.append(variant)
            total_generated += 1

    # Zapis
    fieldnames = list(feed_rows[0].keys()) + ["mvss", "color_code", "color_name", "image_link", "variant_id"]
    
    with open(OUTPUT_FILE, 'w', newline='', encoding='utf-8') as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(variants)
        
    print(f"\nWygenerowano {total_generated} wariantów (Model + Wersja + Kolor).")
    print(f"Zapisano do: {OUTPUT_FILE}")

if __name__ == "__main__":
    main()

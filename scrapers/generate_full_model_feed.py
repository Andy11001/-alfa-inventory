import csv
import json
import os
import re

# Pliki wejściowe
import scraper_utils
FEED_FILE = os.path.join(os.path.dirname(os.path.dirname(__file__)), "data", "alfa_model_feed.csv")
IMAGES_FILE = os.path.join(os.path.dirname(os.path.dirname(__file__)), "data", "alfa_configurator_images.csv")
CODES_FILE = os.path.join(os.path.dirname(os.path.dirname(__file__)), "data", "alfa_codes.json")
MAPPING_FILE = os.path.join(os.path.dirname(os.path.dirname(__file__)), "data", "model_version_mapping.json")
LIVE_COLORS_FILE = os.path.join(os.path.dirname(os.path.dirname(__file__)), "data", "alfa_live_colors.json")

# Plik wyjściowy
OUTPUT_FILE = os.path.join(os.path.dirname(os.path.dirname(__file__)), "data", "alfa_model_final.csv")

def load_json(path):
    with open(path, 'r', encoding='utf-8') as f:
        return json.load(f)

def parse_url_params(url):
    """Rozbija URL na słownik parametrów."""
    if "?" not in url: return {}
    query = url.split("?")[1]
    params = {}
    for pair in query.split("&"):
        if "=" in pair:
            key, val = pair.split("=", 1)
            params[key] = val
    return params

def build_url(params, color_code, new_mvss=None):
    """Buduje URL obrazka na podstawie parametrów i kodu koloru."""
    new_params = params.copy()
    new_params["body"] = color_code
    if new_mvss:
        new_params["mmvs"] = new_mvss
    
    # Bazowy URL API obrazkowego Fiata
    base = "https://lb.assets.fiat.com/vl-picker-service/rest/getImage"
    query = "&".join([f"{k}={v}" for k, v in new_params.items()])
    return f"{base}?{query}"

def find_mvss(title, mapping, live_colors_db=None, forced_mid=None):
    """
    Dopasowuje nazwę z cennika do kodu MVSS.
    
    :param forced_mid: Jeśli podano (np. "622"), funkcja szuka TYLKO w tym modelu.
    """
    title_upper = title.upper()
    matches = []
    
    # Modele do sprawdzenia
    MODELS = ["620", "622", "626", "627", "630", "638"]
    
    # Jeśli mamy wykryty kod modelu ze strony, ograniczamy poszukiwania
    if forced_mid and forced_mid in MODELS:
        target_models = [forced_mid]
    else:
        target_models = MODELS
    
    for mid in target_models:
        if mid not in mapping: continue
        versions = mapping[mid]
        
        # Filtrowanie wersji modelu (Precyzyjne dobieranie napędu jeśli brak forced_mid)
        # Jeśli forced_mid jest podane, ufamy że to ten model, ale wciąż sprawdzamy wersje silnikowe
        if not forced_mid:
            model_name = versions.get("_model_name", "").upper()
            match_model = False
            
            if "JUNIOR" in title_upper:
                if "ELETTRICA" in title_upper:
                    if mid == "627": match_model = True
                elif mid == "626": # Ibrida (domyślny Junior)
                    match_model = True
                    
            elif "TONALE" in title_upper:
                if "PHEV" in title_upper or "PLUG-IN" in title_upper:
                    if mid == "638": match_model = True
                elif mid == "622": # MHEV / Diesel (domyślne Tonale)
                    match_model = True
                    
            elif "STELVIO" in title_upper and mid == "630": match_model = True
            elif "GIULIA" in title_upper and mid == "620": match_model = True
            
            if not match_model: continue

        GENERIC_NAMES = ["JUNIOR", "TONALE", "STELVIO", "GIULIA", "BASE", "STANDARD"]
        valid_versions = [(k, v) for k, v in versions.items() if not k.startswith("_")]
        
        # Sortowanie: Najpierw NIE-generyczne, potem najdłuższe
        sorted_versions = sorted(
            valid_versions,
            key=lambda x: (x[1].upper() in GENERIC_NAMES, -len(x[1]))
        )
        
        for key, name in sorted_versions:
            if name.upper() in title_upper:
                mvss = f"83{mid}{key.replace('|', '')}"
                
                # Obliczamy "wagę" matcha
                is_live = 1 if live_colors_db and mvss in live_colors_db else 0
                is_generic = 1 if name.upper() in GENERIC_NAMES else 0
                name_len = len(name)
                
                matches.append({
                    'mvss': mvss,
                    'is_live': is_live,
                    'is_generic': is_generic,
                    'name_len': name_len,
                    'mid': mid
                })
    
    if not matches:
        return None, None
        
    # Najpierw LIVE, potem NIE-generyczne, potem najdłuższe
    best = sorted(
        matches, 
        key=lambda x: (-x['is_live'], x['is_generic'], -x['name_len'])
    )[0]
    
    return best['mvss'], best['mid']

def get_model_info(title):
    """Zwraca (model, trim, link) na podstawie tytułu."""
    title_u = title.upper()
    model = ""
    link = "https://www.alfaromeo.pl/"
    trim = "Standard"
    
    if "JUNIOR" in title_u:
        model = "Junior"
        link = "https://www.alfaromeo.pl/modele/junior"
        if "IBRIDA" in title_u: link = "https://www.alfaromeo.pl/modele/junior-ibrida"
        if "ELETTRICA" in title_u: link = "https://www.alfaromeo.pl/modele/junior-elettrica"
    elif "TONALE" in title_u:
        model = "Tonale"
        link = "https://www.alfaromeo.pl/modele/tonale"
        if "PHEV" in title_u or "PLUG-IN" in title_u: link = "https://www.alfaromeo.pl/modele/tonale-plug-in-hybrid"
    elif "STELVIO" in title_u:
        model = "Stelvio"
        link = "https://www.alfaromeo.pl/modele/stelvio"
    elif "GIULIA" in title_u:
        model = "Giulia"
        link = "https://www.alfaromeo.pl/modele/giulia"
        
    # Trim detection (simplified)
    trims = ["VELOCE", "SPRINT", "TI", "SPECIALE", "TRIBUTO", "INTENSA", "QUADRIFOGLIO"]
    for t in trims:
        if t in title_u:
            trim = t.capitalize()
            # Special case for multi-word trims
            if trim == "Speciale" and "SPORT" in title_u: trim = "Sport Speciale"
            break
            
    return model, trim, link

def main():
    print("Generowanie finalnej macierzy (nowy schemat TikToka)...")
    
    # 1. Wczytaj dane
    codes_data = load_json(CODES_FILE)
    all_colors = codes_data.get("colors", {})
    mapping = load_json(MAPPING_FILE)

    live_colors_db = {}
    if os.path.exists(LIVE_COLORS_FILE):
        live_colors_db = load_json(LIVE_COLORS_FILE)
        print(f"   Załadowano dane live o kolorach dla {len(live_colors_db)} wersji MVSS.")
    
    img_templates = {}
    with open(IMAGES_FILE, 'r', encoding='utf-8') as f:
        reader = csv.DictReader(f)
        for row in reader:
            if row["image_url"]:
                img_templates[row["mvss"]] = parse_url_params(row["image_url"])

    feed_rows = []
    with open(FEED_FILE, 'r', encoding='utf-8') as f:
        feed_rows = list(csv.DictReader(f))

    # Fallback map
    fallback_templates = {}
    for mvss, params in img_templates.items():
        if len(mvss) > 5:
            mid = mvss[2:5]
            if mid not in fallback_templates:
                fallback_templates[mid] = params
    
    if "638" not in fallback_templates and "622" in fallback_templates:
        fallback_templates["638"] = fallback_templates["622"]
    if "627" not in fallback_templates and "626" in fallback_templates:
        fallback_templates["627"] = fallback_templates["626"]

    final_rows = []
    for row in feed_rows:
        title = row['title']
        model_code = row.get('model_code', '').strip() # Pobranie nowego pola
        
        # Przekazanie model_code do funkcji szukającej
        mvss, target_mid = find_mvss(title, mapping, live_colors_db, forced_mid=model_code)
            
        if not mvss:
            # print(f"⚠️ Brak MVSS dla: {title}")
            continue

        template_params = img_templates.get(mvss)
        if not template_params and target_mid in fallback_templates:
            template_params = fallback_templates[target_mid]
            
        if not template_params:
            # print(f"❌ Brak szablonu obrazka dla: {title}")
            continue

        colors_to_process = []
        if mvss in live_colors_db:
            live_data = live_colors_db[mvss]
            for code in live_data.get("codes", []):
                name = live_data.get("names", {}).get(code) or all_colors.get(code, f"Kolor {code}")
                colors_to_process.append((code, name))
        else:
            for code, name in all_colors.items():
                colors_to_process.append((code, name))
        
        # Dane do nowego feeda
        model, trim, link = get_model_info(title)
        
        # Pobranie i czyszczenie disclaimera
        raw_disclaimer = row.get('disclaimer', '')
        offer_disclaimer = raw_disclaimer.strip(" .,")
        if not offer_disclaimer:
            offer_disclaimer = "Oferta leasingowa. Szczegóły u dealera."
        else:
            # Uppercase first letter
            offer_disclaimer = offer_disclaimer[0].upper() + offer_disclaimer[1:]

        # Obliczenia finansowe
        try:
            price_brutto = float(row['price_brutto'])
            pct = float(row['down_payment_pct'])
            downpayment_val = price_brutto * (pct / 100)
            downpayment_str = f"{int(downpayment_val)} PLN"
            
            installment = row['installment_netto']
            amount_price_str = f"{installment} PLN"
        except:
            downpayment_str = ""
            amount_price_str = ""

        for color_code, color_name in colors_to_process:
            final_url = build_url(template_params, color_code, new_mvss=mvss)
            
            # Generowanie description & title
            description = scraper_utils.format_model_description(title, amount_price_str)
            tiktok_title = scraper_utils.format_model_title(title, amount_price_str)

            # Mapowanie na nowy schemat TikToka
            new_row = {
                "vehicle_id": f"{row['vehicle_id']}-{color_code}",
                "title": tiktok_title,
                "description": description,
                "rodzaj": "modelowy",
                "make": "Alfa Romeo",
                "model": model,
                "year": "2025",
                "link": link,
                "image_link": final_url,
                "exterior_color": color_name,
                "additional_image_link": "",
                "trim": trim,
                "offer_disclaimer": offer_disclaimer,
                "offer_disclaimer_url": link,
                "offer_type": "LEASE",
                "term_length": row['months'],
                "offer_term_qualifier": "months",
                "amount_price": amount_price_str,
                "amount_percentage": "",
                "amount_qualifier": "per month",
                "downpayment": downpayment_str,
                "downpayment_qualifier": "due at signing",
                "emission_disclaimer": "",
                "emission_disclaimer_url": "",
                "emission_overlay_disclaimer": "",
                "emission_image_link": ""
            }
            final_rows.append(new_row)

    # Zapis w nowym formacie
    fieldnames = [
        "vehicle_id", "title", "description", "rodzaj", "make", "model", "year", "link", "image_link", 
        "exterior_color", "additional_image_link", "trim", "offer_disclaimer", 
        "offer_disclaimer_url", "offer_type", "term_length", "offer_term_qualifier", 
        "amount_price", "amount_percentage", "amount_qualifier", "downpayment", 
        "downpayment_qualifier", "emission_disclaimer", "emission_disclaimer_url", 
        "emission_overlay_disclaimer", "emission_image_link"
    ]
    
    with open(OUTPUT_FILE, 'w', newline='', encoding='utf-8') as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(final_rows)
        
    print(f"\nSukces! Wygenerowano {len(final_rows)} wariantów w formacie TikTok Catalog.")

if __name__ == "__main__":
    main()
import requests
from bs4 import BeautifulSoup
import re
import csv
import os
import scraper_utils # Import modułu bezpieczeństwa
import json
import collections
from urllib.parse import urljoin

# Konfiguracja
BASE_URL = "https://www.dsautomobiles.pl"
RANGE_URL = "https://www.dsautomobiles.pl/gama-ds.html"
OUTPUT_FILE = os.path.join(os.path.dirname(os.path.dirname(__file__)), "data", "ds_model_feed.csv")
COLORS_JSON_FILE = os.path.join(os.path.dirname(os.path.dirname(__file__)), "data", "ds_colors.json")
IMAGES_DIR = os.path.join(os.path.dirname(os.path.dirname(__file__)), "data", "images")
HISTORY_FILE = os.path.join(os.path.dirname(os.path.dirname(__file__)), "data", "ds_stock_colors_history.json")
GITHUB_REPO_URL = "https://raw.githubusercontent.com/Andy11001/-alfa-inventory/master/data/images/"

def clean_title(title):
    if not title: return ""
    t = title.strip()
    t = BeautifulSoup(t, 'html.parser').get_text()
    t = re.sub(r'\s+', ' ', t).strip()
    if "DS" not in t.upper() and t:
        t = f"DS {t}"
    return t

def clean_price(price_str):
    if not price_str: return 0
    clean = re.sub(r'[^\d]', '', str(price_str))
    return int(clean) if clean else 0

def load_colors_json():
    if not os.path.exists(COLORS_JSON_FILE):
        return {}
    try:
        with open(COLORS_JSON_FILE, 'r', encoding='utf-8') as f:
            return json.load(f)
    except Exception as e:
        print(f"❌ Błąd ładowania ds_colors.json: {e}")
        return {}

def load_stock_history():
    if not os.path.exists(HISTORY_FILE):
        return {}
    try:
        with open(HISTORY_FILE, 'r', encoding='utf-8') as f:
            return json.load(f)
    except Exception as e:
        print(f"❌ Błąd ładowania historii stocku: {e}")
        return {}

def save_stock_history(history):
    try:
        with open(HISTORY_FILE, 'w', encoding='utf-8') as f:
            json.dump(history, f, indent=4, ensure_ascii=False)
        print("✅ Zapisano historię kolorów stockowych.")
    except Exception as e:
        print(f"❌ Błąd zapisu historii stocku: {e}")

def normalize_model_name_for_filename(model_name):
    """
    DS N°4 HYBRID -> DSN4HYBRID
    DS 3 E-TENSE -> DS3ETENSE
    """
    name = model_name.upper()
    name = name.replace("N°", "N").replace(" ", "").replace("-", "")
    return name

def get_image_from_db(model_name, color_data):
    """
    Pobiera URL obrazka dla danego koloru.
    Priorytet 1: Plik lokalny w data/images (zwraca link GitHub)
    Priorytet 2: URL z ds_colors.json (visuel3d)
    """
    color_code = color_data.get("color_code")
    visuel_url = color_data.get("image_url")
    
    if not color_code:
        return visuel_url

    # Konstrukcja nazwy pliku
    model_part = normalize_model_name_for_filename(model_name)
    filename = f"{model_part}_{color_code}.jpg"
    local_path = os.path.join(IMAGES_DIR, filename)

    if os.path.exists(local_path):
        return f"{GITHUB_REPO_URL}{filename}"
    
    return visuel_url

def get_menu_structure(session):
    """
    Parsuje komponent WlUnifiedHeader ze strony gamy, aby uzyskać 
    oficjalną listę modeli i ich obrazki z menu poprzez JSON w data-props.
    """
    print(f"🔍 Pobieranie struktury menu z: {RANGE_URL}")
    models_list = []
    
    try:
        r = scraper_utils.fetch_with_retry(session, RANGE_URL, timeout=15)
        if r.status_code != 200:
            print(f"❌ Błąd HTTP: {r.status_code}")
            return []

        soup = BeautifulSoup(r.text, 'html.parser')
        
        # Szukamy konfiguracji nagłówka (menu)
        header = soup.find("div", attrs={"data-app-wl": "WlUnifiedHeader"})
        if not header:
            print("❌ Nie znaleziono komponentu WlUnifiedHeader")
            return []

        # W nowej wersji dane są w atrybucie data-props jako JSON
        props_str = header.get("data-props")
        if not props_str:
            print("❌ Komponent WlUnifiedHeader nie zawiera data-props")
            return []
            
        try:
            props = json.loads(props_str)
        except json.JSONDecodeError:
            print("❌ Błąd parsowania JSON z data-props")
            return []
            
        # Szukamy menu z modelami w hamburgermenu->menu
        menu_items = props.get("hamburgermenu", {}).get("menu", [])
        model_menu = None
        for m in menu_items:
            if m.get("name") == "whitelabelmodelmenu":
                model_menu = m
                break
                
        if not model_menu:
            print("❌ Nie znaleziono 'whitelabelmodelmenu' w strukturze JSON")
            return []

        # Interesuje nas lista subModelTagMapping
        sub_models = model_menu.get("subModelTagMapping", [])
        
        # Oraz główne modele jako awaryjne fallbacki, jeśli subModele nie wystarczą
        # Niektóre mogą być w modelTagMapping
        # Często główne modele mogą nie mieć prosto zdefiniowanych linków do konkretnych silników
        
        for sm in sub_models:
            href = sm.get("link", {}).get("href", "")
            if not href or href == "#": continue
            
            full_url = urljoin(BASE_URL, href)
            
            # Tytuł
            title = sm.get("image", {}).get("alt", "")
            if not title:
                title = sm.get("name", "")
            
            title = clean_title(title)
            
            # Obrazek
            img_src = sm.get("image", {}).get("desktopImg", "")
            full_img_url = urljoin(BASE_URL, img_src) if img_src else ""

            models_list.append({
                "title": title,
                "url": full_url,
                "image_url": full_img_url
            })
            
        # Unikalne modele wg URL (JSON czasem ma duplikaty ścieżek z różnymi filterQueries)
        unique_models = {}
        for m in models_list:
            unique_models[m["url"]] = m
        models_list = list(unique_models.values())

    except Exception as e:
        print(f"❌ Błąd parsowania menu: {e}")

    print(f"✅ Znaleziono {len(models_list)} modeli w menu bocznym.")
    return models_list

def get_price_from_page(url, session):
    """Wchodzi na stronę modelu i pobiera cenę/ratę oraz pełny disclaimer z popupu."""
    try:
        r = scraper_utils.fetch_with_retry(session, url, timeout=10)
        if r.status_code != 200: return 0, 0, ""
        
        soup = BeautifulSoup(r.text, 'html.parser')
        
        # 1. Próbujemy pobrać pełny disclaimer z popupu (legal-mentions.html)
        full_legal = ""
        for div in soup.find_all("div", attrs={"data-app-wl": "WlModalWindow"}):
            try:
                props = json.loads(div["data-props"])
                page_url = props.get("pageUrl")
                if page_url and "legal-mentions" in page_url:
                    full_legal_url = urljoin(BASE_URL, page_url)
                    lr = scraper_utils.fetch_with_retry(session, full_legal_url, timeout=5)
                    full_legal = BeautifulSoup(lr.text, 'html.parser').get_text(" ", strip=True)
                    break
            except: pass
            
        if not full_legal:
            match = re.search(r'(/[\w\d\-\/]*/legal-mentions\.html)', r.text)
            if match:
                try:
                    full_legal_url = urljoin(BASE_URL, match.group(1))
                    lr = scraper_utils.fetch_with_retry(session, full_legal_url, timeout=5)
                    full_legal = BeautifulSoup(lr.text, 'html.parser').get_text(" ", strip=True)
                except: pass

        # 2. Pobieramy cenę/ratę
        p, i = 0, 0
        comp = soup.find("div", attrs={"data-app-wl": "WlModelIndex"})
        if comp:
            props = json.loads(comp["data-props"])
            legal_note = props.get("legalNote", "")
            clean_note = BeautifulSoup(legal_note, 'html.parser').get_text(" ", strip=True)
            
            price_match = re.search(r'([\d\s\xa0\u202f.,]+)\s*zł\s*brutto', clean_note, re.I)
            rate_match = re.search(r'Od\s*([\d\s\xa0\u202f.,]+)\s*zł\s*netto', clean_note, re.I)
            
            p = clean_price(price_match.group(1)) if price_match else 0
            i = clean_price(rate_match.group(1)) if rate_match else 0
            
            if not full_legal:
                full_legal = clean_note

        # 3. Fallback
        if p == 0 or i == 0:
            text = soup.get_text(" ", strip=True).replace('\xa0', ' ')
            if p == 0:
                price_match = re.search(r'([\d\s]+)\s*zł\s*brutto', text, re.I)
                p = clean_price(price_match.group(1)) if price_match else 0
            if i == 0:
                rate_match = re.search(r'Od\s*([\d\s]+)\s*zł\s*netto', text, re.I)
                i = clean_price(rate_match.group(1)) if rate_match else 0
            
            if not full_legal and price_match:
                full_legal = price_match.group(0)

        return p, i, full_legal

    except Exception as e:
        print(f"⚠️ Błąd pobierania danych ze strony {url}: {e}")
        return 0, 0, ""

def load_inventory_colors():
    """
    Loads ds_inventory.csv and returns a map:
    {
        "MODEL_KEY": {
            "COLOR_NAME": "IMAGE_URL"
        }
    }
    """
    inv_path = os.path.join(os.path.dirname(os.path.dirname(__file__)), "data", "ds_inventory.csv")
    if not os.path.exists(inv_path):
        print("⚠️ Warning: ds_inventory.csv not found. Skipping color fallback.")
        return {}

    color_map = collections.defaultdict(dict)

    with open(inv_path, 'r', encoding='utf-8') as f:
        reader = csv.DictReader(f)
        for row in reader:
            model = row.get('model', '').strip()
            color = row.get('exterior_color', '').strip()
            img = row.get('image_link', '').strip()

            if not model or not color or not img: continue

            # Normalize model name for key (e.g. "DS 7" -> "DS7", "N°4" -> "N4")
            norm_model = re.sub(r'[^A-Z0-9]', '', model.upper())
            
            if color not in color_map[norm_model]:
                color_map[norm_model][color] = img

    return color_map

def match_inventory_colors(model_title, color_map):
    """
    Finds matching colors for a model title.
    Returns dict {color: img} or empty dict.
    """
    norm_title = re.sub(r'[^A-Z0-9]', '', model_title.upper())
    
    # Check if any key in color_map is a substring of norm_title
    for key, colors in color_map.items():
        if key in norm_title:
            return colors
            
    return {}

# ─────────────────────────────────────────────
# NOWE: Integracja z API configv3 (jak w Oplu)
# ─────────────────────────────────────────────
API_BASE = "https://api-cdn.configv3.awsmpsa.com/api/v4/d-pl-pl-btoc/vehicles"

ENERGY_MAP = {
    "01": "Hybrid",
    "02": "Gasoline",
    "03": "Diesel",
    "04": "Electric",
    "12": "Plug-in Hybrid"
}

def fetch_all_derived_models():
    """Pobiera listę wszystkich modeli (derivedModels) z API DS."""
    url = f"{API_BASE}/derivedModels"
    try:
        r = requests.get(url, timeout=10)
        if r.status_code == 200:
            return r.json()
    except Exception as e:
        print(f"Błąd łączenia z API: {e}")
    return []

def fetch_api_versions(model_id):
    """Pobiera warianty (versions) z API dla danego ID modelu."""
    url = f"{API_BASE}/versions?derivedModel={model_id}"
    try:
        r = requests.get(url, timeout=15)
        if r.status_code == 200:
            return r.json()
    except Exception as e:
        print(f"Błąd przy pobieraniu wariantów dla {model_id}: {e}")
    return []

def extract_model_data_from_api(versions):
    """
    Extract structured trim/color/engine data from API versions list for DS.
    Returns dict: { trim_name: { "engines": [...], "colors": [...] } }
    """
    trims = {}
    for v in versions:
        trim_label = v.get("grCommercialName", {}).get("label", "Standard")
        energy_id = v.get("energy", {}).get("id", "02")
        fuel_type = ENERGY_MAP.get(energy_id, "Gasoline")
        engine_label = v.get("grEngine", {}).get("label", "")

        if "hybrid" in engine_label.lower() and fuel_type == "Gasoline":
            fuel_type = "Hybrid"
        transmission = v.get("grTransmissionType", {}).get("label", "")
        # API price may exist but we prioritize menu scraping over it
        api_price = float(v.get("prices", {}).get("price", {}).get("base", "0"))

        body_style = v.get("bodyStyle", {}).get("label", "")
        lcdv = v.get("lcdv", "")

        colors = []
        looks = v.get("globalFeatures", {}).get("looks", {}).get("categories", [])
        
        has_rims = any(cat.get("id") == "rims" for cat in looks)
        interior_id = ""
        rim_id = ""
        
        # Grab first default interior and rim to build a valid complete CFGAP3D visual URL
        for cat in looks:
            if cat.get("id") == "interiors" and not interior_id:
                feats = cat.get("features", [])
                if feats: interior_id = feats[0].get("id", "")
            elif cat.get("id") == "rims" and not rim_id:
                feats = cat.get("features", [])
                if feats: rim_id = feats[0].get("id", "")

        for cat in looks:
            if cat.get("id") == "exteriors":
                for feat in cat.get("features", []):
                    color_name = feat.get("label", "")
                    color_id = feat.get("id", "")
                    swatch_url = feat.get("visuals", {}).get("default", "")

                    if color_name and lcdv and color_id:
                        if has_rims:
                            # Full car 3D render URL for DS (requires trim and opt for CFGAP3D)
                            trim_param = f"&trim={interior_id}" if interior_id else ""
                            opt_param = f"&opt1={rim_id}" if rim_id else ""
                            
                            img_url = (
                                f"https://visuel3d-secure.citroen.com/V3DImage.ashx"
                                f"?client=CFGAP3D&mkt=PL&env=PROD&version={lcdv}"
                                f"&ratio=1&format=jpg&quality=90&width=1280"
                                f"&view=001&color={color_id}{trim_param}{opt_param}&back=0"
                            )
                        else:
                            img_url = swatch_url if swatch_url else ""
                            
                        if img_url:
                            colors.append({"name": color_name, "image": img_url})

        if trim_label not in trims:
            trims[trim_label] = {"engines": [], "colors": []}

        engine_key = f"{fuel_type}|{engine_label}|{transmission}"
        existing_keys = [f"{e['fuel_type']}|{e['engine']}|{e['transmission']}" for e in trims[trim_label]["engines"]]
        if engine_key not in existing_keys:
            trims[trim_label]["engines"].append({
                "fuel_type": fuel_type,
                "engine": engine_label,
                "transmission": transmission,
                "api_price": api_price,
                "body_style": body_style,
            })

        existing_colors = {c["name"] for c in trims[trim_label]["colors"]}
        for c in colors:
            if c["name"] not in existing_colors:
                trims[trim_label]["colors"].append(c)
                existing_colors.add(c["name"])

    return trims



def run():
    print("🕷️ Rozpoczynam pobieranie (Menu -> Modele)...")
    session = requests.Session()
    session.headers.update({"User-Agent": "Mozilla/5.0"})

    # 1. Pobierz modele z menu
    menu_models = get_menu_structure(session)
    
    print("📦 Pobieranie listy modeli z API dsautomobiles...")
    api_models = fetch_all_derived_models()
    if not api_models:
        print("❌ Nie udało się pobrać modeli z API. Przerwanie.")
        return

    # Słownik do szybkiego szukania modeli w API { "DS4": model_id }
    api_models_map = {}
    for m in api_models:
        label = m.get("label", "").upper().replace(" ", "")
        if label == "N°4": label = "DSN4"
        elif label == "N°8": label = "DSN8"
        api_models_map[label] = m.get("id")

    final_data = []
    seen = set()

    for item in menu_models:
        url = item['url']
        if url in seen: continue
        seen.add(url)
        
        print(f"\n➡️ Przetwarzanie: {item['title']} ({url})")
        price, installment, disclaimer = get_price_from_page(url, session)
        
        # Skip if no price and no installment
        if price == 0 and installment == 0:
            print(f"   ⚠️ Pominięto {item['title']} - brak ceny i raty.")
            continue

        # Dopasowanie do API (menu zwraca np. "DS 4 E-TENSE", API ma bazowe "DS 4")
        # Zmieniamy N° na N by ułatwić szukanie
        menu_title_upper = item['title'].upper().replace(" ", "").replace("N°", "N")
        
        # Determine base model for API lookup
        known_base_models = ["DSN4", "DSN8", "DS3", "DS4", "DS7", "DS9"]
        matched_api_id = None
        base_model_label = item['title']
        
        for kbm in known_base_models:
            # W przypadku modeli zaczynających się od DSN (np. DSN4), 
            # menu_title_upper może mieć tylko 'N4' po usunięciu spacji i zamianie 'N°'.
            alt_match = kbm.replace("DSN", "N") if kbm.startswith("DSN") else kbm
            if kbm in menu_title_upper or alt_match in menu_title_upper:
                matched_api_id = api_models_map.get(kbm)
                # Odtwarzamy przybliżoną nazwę bazy jeśli brak
                if kbm == "DSN4": base_model_label = "DS N°4"
                elif kbm == "DSN8": base_model_label = "DS N°8"
                elif kbm == "DS3": base_model_label = "DS 3"
                elif kbm == "DS4": base_model_label = "DS 4"
                elif kbm == "DS7": base_model_label = "DS 7"
                elif kbm == "DS9": base_model_label = "DS 9"
                break
                
        if not matched_api_id:
            print(f"   ⚠️ Nie dopasowano '{item['title']}' do żadnego modelu API. Pomijam warianty zaawansowane.")
            continue
            
        print(f"   🛠️ Pobieranie wariantów API dla bazowego {base_model_label} ({matched_api_id})...")
        versions = fetch_api_versions(matched_api_id)
        if not versions:
            print("   ⚠️ Brak wersji w API.")
            continue
            
        trims_data = extract_model_data_from_api(versions)
        trim_count = len(trims_data)
        engine_count = sum(len(t["engines"]) for t in trims_data.values())
        color_count = sum(len(t["colors"]) for t in trims_data.values())
        print(f"   ✅ API: {trim_count} trimów, {engine_count} silników, {color_count} kolorów")
        
        # Generowanie permutacji dla Feed'a (Ceny promocyjne "od" są te same dla modelu, warianty zdjęć/nazw się zmieniają)
        for trim_name, data in trims_data.items():
            engines_to_use = data["engines"]
            
            # Jeśli nazwa z menu jasno wskazuje na paliwo, spróbujmy odfiltrować silniki
            menu_hints_electric = ["E-TENSE", "ELECTRIC", "ELEKTRYCZNY", "ELEKTRYCZNA"]
            menu_hints_phev = ["PLUG-IN"]
            menu_hints_hybrid = ["HYBRID", "HYBRYDOWY"]
            menu_hints_diesel = ["DIESEL", "BLUEHDI"]
            
            is_electric = any(h in menu_title_upper for h in menu_hints_electric) and not any(h in menu_title_upper for h in menu_hints_phev)
            is_phev = any(h in menu_title_upper for h in menu_hints_phev)
            is_hybrid = any(h in menu_title_upper for h in menu_hints_hybrid)
            is_diesel = any(h in menu_title_upper for h in menu_hints_diesel)
            
            # Odfiltrujmy silniki w API pasujące do tej podstrony
            filtered_engines = []
            for eng in engines_to_use:
                ft = eng["fuel_type"].upper()
                if is_electric and "ELECTRIC" in ft: filtered_engines.append(eng)
                elif is_phev and "PLUG-IN" in ft: filtered_engines.append(eng)
                elif is_hybrid and "HYBRID" in ft and "PLUG" not in ft: filtered_engines.append(eng)
                elif is_diesel and "DIESEL" in ft: filtered_engines.append(eng)
                elif not (is_electric or is_phev or is_hybrid or is_diesel):
                    # Podstrona ogólna (np. wprowadzająca / spalinowa)
                    if "GASOLINE" in ft or "DIESEL" in ft: filtered_engines.append(eng)
            
            # Fallback - jak przefiltrowało za mocno, bierzemy wszystkie
            if not filtered_engines:
                filtered_engines = engines_to_use
                
            for eng in filtered_engines:
                fuel_hint = eng["fuel_type"]
                engine_name = eng["engine"]
                
                # Ustawiamy ratę z menu (z konfiguracji wskaźnikowej "od")
                amount_price_str = f"{installment} PLN" if installment else ""
                downpayment_val = int(price * 0.10) if price else 0
                downpayment_str = f"{downpayment_val} PLN" if downpayment_val else ""

                # Generowanie description & title dla tej konkretnej wersji (uwzględniając Trim i Silnik)
                # Tytuł: DS 4 E-TENSE Etoile Hybrid 136 · Rata od 1085 PLN netto/mies.
                full_model_title = f"{item['title']} {trim_name} {fuel_hint}"
                if fuel_hint.upper() in item['title'].upper():
                    full_model_title = f"{item['title']} {trim_name}"
                    
                description = scraper_utils.format_model_description(full_model_title, amount_price_str)
                tiktok_title = scraper_utils.format_model_title(full_model_title, amount_price_str)
                
                base_record = {
                    "vehicle_id": scraper_utils.generate_stable_id(f"{item['title']}-{trim_name}-{fuel_hint}", prefix="DS"),
                    "title": tiktok_title,
                    "description": description,
                    "rodzaj": "modelowy",
                    "make": "DS Automobiles",
                    "model": base_model_label,
                    "year": "2025", 
                    "link": url,
                    "trim": trim_name,
                    "offer_disclaimer": disclaimer,
                    "offer_disclaimer_url": url,
                    "offer_type": "LEASE",
                    "term_length": "24",
                    "offer_term_qualifier": "months",
                    "amount_price": amount_price_str,
                    "amount_qualifier": "per month",
                    "downpayment": downpayment_str,
                    "downpayment_qualifier": "due at signing",
                    "emission_disclaimer": "",
                    "emission_disclaimer_url": "",
                    "emission_overlay_disclaimer": "",
                    "emission_image_link": ""
                }
                
                if not data["colors"]:
                    # Fallback obrazka
                    base_record["exterior_color"] = "Standard"
                    base_record["image_link"] = item['image_url']
                    final_data.append(base_record)
                else:
                    for color in data["colors"]:
                        record = base_record.copy()
                        record["exterior_color"] = color["name"]
                        record["image_link"] = color["image"]
                        color_suffix = scraper_utils.generate_stable_id(color["name"], length=6)
                        record["vehicle_id"] = f"{base_record['vehicle_id']}-{color_suffix}"
                        
                        final_data.append(record)

    # Zapis
    if final_data:
        os.makedirs(os.path.dirname(OUTPUT_FILE), exist_ok=True)
        
        # New Fieldnames matching Alfa Final Feed
        fieldnames = [
            "vehicle_id", "title", "description", "rodzaj", "make", "model", "year", "link", "image_link", 
            "exterior_color", "additional_image_link", "trim", "offer_disclaimer", 
            "offer_disclaimer_url", "offer_type", "term_length", "offer_term_qualifier", 
            "amount_price", "amount_percentage", "amount_qualifier", "downpayment", 
            "downpayment_qualifier", "emission_disclaimer", "emission_disclaimer_url", 
            "emission_overlay_disclaimer", "emission_image_link"
        ]
        
        # Bezpieczny zapis z scraper_utils
        from scraper_utils import safe_save_csv
        # Przygotowanie danych w formacie listy słowników
        data_to_save = [{k: row.get(k, "") for k in fieldnames} for row in final_data]
        
        if safe_save_csv(data_to_save, fieldnames, OUTPUT_FILE, min_rows_threshold=1):
            print(f"✅ Zapisano {len(final_data)} ofert do {OUTPUT_FILE} (Schema zgodna z Alfa Final)")
        else:
            print(f"⚠️ Nie udało się zapisać pliku {OUTPUT_FILE}")

if __name__ == "__main__":
    run()
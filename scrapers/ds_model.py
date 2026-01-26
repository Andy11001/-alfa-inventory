import requests
from bs4 import BeautifulSoup
import re
import csv
import os
import json
import collections
from urllib.parse import urljoin

# Konfiguracja
BASE_URL = "https://www.dsautomobiles.pl"
RANGE_URL = "https://www.dsautomobiles.pl/gama-ds.html"
OUTPUT_FILE = os.path.join(os.path.dirname(os.path.dirname(__file__)), "data", "ds_model_feed.csv")

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

def get_menu_structure(session):
    """
    Parsuje komponent WlUnifiedHeader ze strony gamy, aby uzyskać 
    oficjalną listę modeli i ich obrazki z menu.
    """
    print(f"🔍 Pobieranie struktury menu z: {RANGE_URL}")
    models_list = []
    
    try:
        r = session.get(RANGE_URL, timeout=15)
        if r.status_code != 200:
            print(f"❌ Błąd HTTP: {r.status_code}")
            return []

        soup = BeautifulSoup(r.text, 'html.parser')
        
        # Szukamy konfiguracji nagłówka (menu)
        header = soup.find("div", attrs={"data-app-wl": "WlUnifiedHeader"})
        if not header or not header.get("data-props"):
            print("❌ Nie znaleziono komponentu WlUnifiedHeader")
            return []

        props = json.loads(header["data-props"])
        hamburger = props.get("hamburgermenu", {})
        
        # 1. Budujemy mapę obrazków (pathQuery -> Image URL)
        image_map = {}
        
        # Mapowanie główne
        for mapping in hamburger.get("modelTagMapping", []):
            pq = mapping.get("pathQuery")
            img = mapping.get("image", {}).get("desktopImg")
            if pq and img:
                image_map[pq] = urljoin(BASE_URL, img)
        
        # Mapowanie podmodeli (wersje silnikowe, edycje specjalne)
        for mapping in hamburger.get("subModelTagMapping", []):
            pq = mapping.get("pathQuery")
            img = mapping.get("image", {}).get("desktopImg")
            if pq and img:
                image_map[pq] = urljoin(BASE_URL, img)

        # 2. Iterujemy po modelach z cache menu
        for model in hamburger.get("modelsCache", []):
            main_name = clean_title(model.get("name"))
            
            # Główny model (często jako kontener)
            # Jeśli ma submodele, to one są ważniejsze
            sub_models = model.get("subModels", [])
            
            if sub_models:
                for sm in sub_models:
                    name = clean_title(sm.get("name"))
                    if not name: name = main_name # Fallback name
                    
                    pq = sm.get("pathQuery")
                    
                    # Szukamy linku w strukturze menu, która jest nieco głębiej
                    # Ale modelCache ma też pole 'modelPathQuery' lub można próbować zgadnąć URL
                    # W JSONie wyżej widać, że linki są w 'menu' -> 'menuItem' -> ... ale to skomplikowane.
                    # Prościej: w 'modelsCache' brakuje URLi wprost, musimy je zmapować z 'modelTagMapping' lub 'switchLinks' na stronie modelu
                    # ALE w tym JSONie z poprzedniego kroku widziałem linki w sekcji "subModelTagMapping"? Nie, tam są obrazki.
                    # Wróćmy do analizy html. WlUnifiedHeader ma sekcję "menu", tam są linki.
                    
                    # Alternatywa: Użyjmy pathQuery do znalezienia URL w innym miejscu lub po prostu zbudujmy URL
                    # W poprzednim output 'switchLinks' na stronie modelu miały URLe.
                    
                    # Spróbujmy wyciągnąć URL z sekcji 'menu' w propsach, która jest listą
                    pass

        # Podejście 2 do wyciągania URLi i Nazw z sekcji "menu" w propsach, która odzwierciedla pasek boczny
        menu_items = props.get("hamburgermenu", {}).get("menu", [])
        for item in menu_items:
            # Szukamy kafelków modeli w "menuVariation": "model"
            if item.get("menuVariation") == "model":
                # Tu są "modelTagMapping" które iterowaliśmy wyżej, ale to tylko obrazki.
                # W HTML wyrenderowanym (SSR) są linki.
                # Parsowanie wyrenderowanego HTML wewnątrz WlUnifiedHeader może być łatwiejsze niż JSONA dla linków
                pass

        # Parsowanie HTML wewnątrz znacznika, bo jest SSR (Server Side Rendered)
        # To jest klucz do sukcesu - linki są w HTMLu wewnątrz diva data-props
        
        # Szukamy kart modeli w wyrenderowanym HTML
        model_cards = header.find_all(class_="wl-header__model-card")
        
        for card in model_cards:
            href = card.get('href')
            if not href or href == "#": continue
            
            full_url = urljoin(BASE_URL, href)
            
            # Tytuł
            title_div = card.find(class_="wl-header__model-card-title")
            title = title_div.get_text(strip=True) if title_div else "DS Model"
            title = clean_title(title)
            
            # Obrazek
            img_tag = card.find("img")
            img_src = img_tag.get("src") if img_tag else ""
            # Jeśli src jest puste, sprawdźmy srcset lub source
            if not img_src and img_tag and img_tag.get("srcset"):
                img_src = img_tag.get("srcset").split(" ")[0]
            
            if not img_src:
                source = card.find("source")
                if source and source.get("srcset"):
                    img_src = source.get("srcset").split(" ")[0]

            full_img_url = urljoin(BASE_URL, img_src) if img_src else ""

            models_list.append({
                "title": title,
                "url": full_url,
                "image_url": full_img_url
            })

    except Exception as e:
        print(f"❌ Błąd parsowania menu: {e}")

    print(f"✅ Znaleziono {len(models_list)} modeli w menu bocznym.")
    return models_list

def get_price_from_page(url, session):
    """Wchodzi na stronę modelu i pobiera cenę/ratę oraz pełny disclaimer z popupu."""
    try:
        r = session.get(url, timeout=10)
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
                    lr = session.get(full_legal_url, timeout=5)
                    full_legal = BeautifulSoup(lr.text, 'html.parser').get_text(" ", strip=True)
                    break
            except: pass
            
        if not full_legal:
            match = re.search(r'(/[\w\d\-\/]*/legal-mentions\.html)', r.text)
            if match:
                try:
                    full_legal_url = urljoin(BASE_URL, match.group(1))
                    lr = session.get(full_legal_url, timeout=5)
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

def get_colors_from_page(url, session):
    """
    Attempts to find color variants directly on the model page.
    Looks for Wl components with 'slides' or HTML color visualizers.
    Returns dict: { "Color Name": "Image URL" (or None) }
    """
    candidates = {}
    try:
        r = session.get(url, timeout=10)
        if r.status_code != 200: return {}
        
        soup = BeautifulSoup(r.text, 'html.parser')
        
        # 1. Heuristic: Look for components with 'slides' (Wl components)
        for div in soup.find_all("div", attrs={"data-app-wl": True}):
            try:
                props = json.loads(div["data-props"])
                if "slides" in props and isinstance(props["slides"], list):
                    temp_candidates = {}
                    for slide in props["slides"]:
                        title = slide.get("title", "").strip()
                        img_obj = slide.get("image", {})
                        img_src = img_obj.get("desktopImg") or img_obj.get("src")
                        
                        if title and img_src:
                            clean_t = BeautifulSoup(title, 'html.parser').get_text(" ", strip=True)
                            if 3 < len(clean_t) < 40:
                                full_img = urljoin(BASE_URL, img_src)
                                temp_candidates[clean_t] = full_img
                    
                    if len(temp_candidates) >= 2:
                        candidates.update(temp_candidates)
            except:
                pass

        # 2. Heuristic: HTML Color Visualizer (e.g. DS N°8)
        # Structure: div.q-automatic-colour-visualiser_colour_inner > img[title="Color"]
        # This gives us Names, but often only Thumbnail images.
        visualizers = soup.find_all("div", class_="q-automatic-colour-visualiser_colour_inner")
        if visualizers:
            for div in visualizers:
                img = div.find("img")
                if img and img.get("title"):
                    color_name = img.get("title").strip()
                    # We usually don't have the full car image here, just a patch.
                    # We store None to indicate "Found name, but no car image".
                    if color_name not in candidates:
                         candidates[color_name] = None

    except Exception as e:
        print(f"⚠️ Błąd pobierania kolorów ze strony: {e}")
        
    return candidates

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

def run():
    print("🕷️ Rozpoczynam pobieranie (Menu -> Modele)...")
    session = requests.Session()
    session.headers.update({"User-Agent": "Mozilla/5.0"})

    # 1. Pobierz modele z menu
    menu_models = get_menu_structure(session)
    
    # 2. Load colors
    inventory_colors = load_inventory_colors()
    print(f"🎨 Załadowano kolory dla modeli: {list(inventory_colors.keys())}")

    final_data = []
    seen = set()

    for item in menu_models:
        url = item['url']
        if url in seen: continue
        seen.add(url)
        
        print(f"➡️ Przetwarzanie: {item['title']} ({url})")
        price, installment, disclaimer = get_price_from_page(url, session)
        
        # Skip if no price and no installment
        if price == 0 and installment == 0:
            print(f"   ⚠️ Pominięto {item['title']} - brak ceny i raty.")
            continue
            
        # Determine Trim / Model from Title
        title_upper = item['title'].upper()
        model_name = item['title'] # Default
        trim_name = "Standard"
        
        # List of known base models to extract
        known_models = ["DS N°4", "DS N°8", "DS 3", "DS 4", "DS 7", "DS 9", "DS N4"]
        for km in known_models:
            if km in title_upper:
                match_index = title_upper.find(km)
                if match_index != -1:
                    model_name = km
                    remainder = title_upper[match_index + len(km):].strip()
                    if remainder:
                        trim_name = remainder.title()
                    break
        
        # Calculate Amount Price (Rata) string
        amount_price_str = f"{installment} PLN" if installment else ""
        
        # Calculate Downpayment (Wpłata)
        downpayment_val = int(price * 0.10) if price else 0
        downpayment_str = f"{downpayment_val} PLN" if downpayment_val else ""

        # Base record with new schema
        base_record = {
            "vehicle_id": f"DS-MODEL-{abs(hash(item['title']))}",
            "title": item['title'],
            "make": "DS Automobiles",
            "model": model_name,
            "year": "2025", # Default year
            "link": url,
            # "image_link": populated below
            # "exterior_color": populated below
            "additional_image_link": "",
            "trim": trim_name,
            "offer_disclaimer": disclaimer,
            "offer_disclaimer_url": url,
            "offer_type": "LEASE",
            "term_length": "24", # Default months
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

        # 1. Try to get colors from the page directly
        colors = get_colors_from_page(url, session)
        source = "Page"
        
        # 2. If not found, fallback to Inventory
        if not colors:
            colors = match_inventory_colors(item['title'], inventory_colors)
            source = "Inventory"

        if colors:
            print(f"   🎨 Znaleziono {len(colors)} kolorów dla {item['title']} (Źródło: {source})")
            for color_name, color_img in colors.items():
                record = base_record.copy()
                record["exterior_color"] = color_name
                
                # Use specific color image if available, else default model image
                if color_img:
                    record["image_link"] = color_img
                else:
                    record["image_link"] = item['image_url'] # Fallback
                    
                # Create unique ID for color variant
                record["vehicle_id"] = f"{base_record['vehicle_id']}-{abs(hash(color_name))}"
                final_data.append(record)
        else:
            print(f"   ⚠️ Brak kolorów dla {item['title']}, używam domyślnego.")
            record = base_record.copy()
            record["exterior_color"] = "Standard"
            record["image_link"] = item['image_url']
            final_data.append(record)

    # Zapis
    if final_data:
        os.makedirs(os.path.dirname(OUTPUT_FILE), exist_ok=True)
        
        # New Fieldnames matching Alfa Final Feed
        fieldnames = [
            "vehicle_id", "title", "make", "model", "year", "link", "image_link", 
            "exterior_color", "additional_image_link", "trim", "offer_disclaimer", 
            "offer_disclaimer_url", "offer_type", "term_length", "offer_term_qualifier", 
            "amount_price", "amount_percentage", "amount_qualifier", "downpayment", 
            "downpayment_qualifier", "emission_disclaimer", "emission_disclaimer_url", 
            "emission_overlay_disclaimer", "emission_image_link"
        ]
        
        with open(OUTPUT_FILE, 'w', encoding='utf-8', newline='') as f:
            writer = csv.DictWriter(f, fieldnames=fieldnames)
            writer.writeheader()
            for row in final_data:
                # Ensure row has all fields
                row_to_write = {k: row.get(k, "") for k in fieldnames}
                writer.writerow(row_to_write)
        print(f"✅ Zapisano {len(final_data)} ofert do {OUTPUT_FILE} (Schema zgodna z Alfa Final)")

if __name__ == "__main__":
    run()
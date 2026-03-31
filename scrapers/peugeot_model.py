"""
Peugeot Model Feed
- Trims, colors, engines, prices: Stellantis configv3 API
- Images: configv3 API 3D visualizer
- URLs: Redirected to oferty.peugeot.pl
"""
import requests
import re
import os

try:
    from scrapers import scraper_utils
except ModuleNotFoundError:
    import scraper_utils

# --- Config ---
API_BASE_BTOC = "https://api-cdn.configv3.awsmpsa.com/api/v4/p-pl-pl-btoc/vehicles"
API_BASE_BTOB = "https://api-cdn.configv3.awsmpsa.com/api/v4/p-pl-pl-btob/vehicles"

OUTPUT_DIR = os.path.join(os.path.dirname(os.path.dirname(__file__)), "data")
OUTPUT_FILE_OSO = os.path.join(OUTPUT_DIR, "peugeot_osobowe_model.csv")
OUTPUT_FILE_DOS = os.path.join(OUTPUT_DIR, "peugeot_dostawcze_model.csv")

# Models present in API but to skip
SKIP_MODELS = set()

# Map to local offers pages
MODEL_LINKS = {
    "Nowy 308": "https://oferty.peugeot.pl/nowy-308/",
    "Nowy E-308": "https://oferty.peugeot.pl/nowy-e-308/",
    "Nowy 308 SW": "https://oferty.peugeot.pl/nowy-308-sw/",
    "Nowy E-308 SW": "https://oferty.peugeot.pl/nowy-e-308-sw/",
    "Nowy E-3008": "https://oferty.peugeot.pl/nowy-e-3008/",
    "Nowy 3008": "https://oferty.peugeot.pl/nowy-3008-hybrid/",
    "Nowy 5008": "https://oferty.peugeot.pl/nowy-peugeot-5008/",
    "Nowy E-5008": "https://oferty.peugeot.pl/nowy-peugeot-e-5008/",
    "208": "https://oferty.peugeot.pl/peugeot-208/",
    "E-208": "https://oferty.peugeot.pl/peugeot-e-208/",
    "2008": "https://oferty.peugeot.pl/peugeot-2008/",
    "E-2008": "https://oferty.peugeot.pl/peugeot-e-2008/",
    "308": "https://oferty.peugeot.pl/peugeot-308-2/",
    "E-308": "https://oferty.peugeot.pl/peugeot-e-308/",
    "308 SW": "https://oferty.peugeot.pl/peugeot-308-sw/",
    "E-308 SW": "https://oferty.peugeot.pl/peugeot-e-308-sw/",
    "408": "https://oferty.peugeot.pl/peugeot-408/",
    "E-408": "https://oferty.peugeot.pl/peugeot-e-408/",
    "Rifter": "https://oferty.peugeot.pl/e-rifter-2/",
    "E-Rifter": "https://oferty.peugeot.pl/e-rifter-2/",
    "Traveller": "https://oferty.peugeot.pl/e-traveller-2/",
    "E-Traveller": "https://oferty.peugeot.pl/e-traveller-2/"
}

ENERGY_MAP = {
    "01": "Hybrid",
    "02": "Gasoline",
    "04": "Diesel",
    "05": "Electric",
    "07": "Electric", 
    "10": "Plug-in Hybrid",
}

def get_model_url(label, fuel_type):
    original_label = label
    # E- mapping
    if fuel_type == "Electric":
        if label.startswith("Nowy ") and not label.startswith("Nowy E-"):
            label = label.replace("Nowy ", "Nowy E-")
        elif not label.startswith("E-") and not label.startswith("Nowy E-"):
            label = f"E-{label}"

    if label in MODEL_LINKS:
        return MODEL_LINKS[label]
    if original_label in MODEL_LINKS:
        return MODEL_LINKS[original_label]
        
    slug = original_label.lower().replace(" ", "-")
    return f"https://www.peugeot.pl/modele/{slug}.html"


import time

session = requests.Session()
session.headers.update({
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Accept": "application/json, text/plain, */*",
    "Accept-Language": "pl-PL,pl;q=0.9,en-US;q=0.8,en;q=0.7",
    "Origin": "https://www.peugeot.pl",
    "Referer": "https://www.peugeot.pl/"
})

def fetch_api_versions(api_base, derived_model_id):
    url = f'{api_base}/versions?derivedModel={derived_model_id}'
    for i in range(3):
        try:
            r = session.get(url, timeout=30)
            r.raise_for_status()
            time.sleep(1)
            return r.json()
        except Exception as e:
            print(f'  ⚠ API error for {derived_model_id} (próba {i+1}/3): {e}')
            time.sleep(3)
    return []

def fetch_all_derived_models(api_base):
    url = f'{api_base}/derivedModels'
    for i in range(3):
        try:
            r = session.get(url, timeout=30)
            r.raise_for_status()
            time.sleep(1)
            return r.json()
        except Exception as e:
            print(f'  ⚠ API derivedModels error (próba {i+1}/3): {e}')
            time.sleep(3)
    return []

def extract_model_data_from_api(versions):
    trims = {}
    for v in versions:
        trim_label = v.get("grCommercialName", {}).get("label", "Standard")
        energy_id = v.get("energy", {}).get("id", "02")
        fuel_type = ENERGY_MAP.get(energy_id, "Gasoline")
        engine_label = v.get("grEngine", {}).get("label", "")
        
        # Override to detect Hybrids mapped sometimes under Gasoline
        if "hybrid" in engine_label.lower() and fuel_type == "Gasoline":
            fuel_type = "Hybrid"
            
        transmission = v.get("grTransmissionType", {}).get("label", "")
        api_price = float(v.get("prices", {}).get("price", {}).get("base", "0"))
        body_style = v.get("bodyStyle", {}).get("label", "")
        lcdv = v.get("lcdv", "")

        colors = []
        looks = v.get("globalFeatures", {}).get("looks", {}).get("categories", [])
        has_rims = any(cat.get("id") == "rims" for cat in looks)

        for cat in looks:
            if cat.get("id") == "exteriors":
                for feat in cat.get("features", []):
                    color_name = feat.get("label", "")
                    color_id = feat.get("id", "")
                    swatch_url = feat.get("visuals", {}).get("default", "")

                    if color_name and lcdv and color_id:
                        if has_rims:
                            # 3D full render generator url for peugeot
                            img_url = (
                                f"https://visual3d-secure.peugeot.com/V3DImage.ashx"
                                f"?client=CFGAP3D&mkt=PL&env=PROD&version={lcdv}"
                                f"&ratio=1&format=jpg&quality=90&width=1280"
                                f"&view=001&color={color_id}&back=0"
                            )
                        else:
                            img_url = swatch_url if swatch_url else ""

                        if img_url:
                            colors.append({"name": color_name, "image": img_url})

        if trim_label not in trims:
            trims[trim_label] = {"engines": [], "colors": []}

        # Unique engine signatures
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

        # Colors 
        existing_colors = {c["name"] for c in trims[trim_label]["colors"]}
        for c in colors:
            if c["name"] not in existing_colors:
                trims[trim_label]["colors"].append(c)
                existing_colors.add(c["name"])

    return trims

def scrape_model_lease_price(url):
    try:
        r = session.get(url, timeout=15)
        if r.status_code != 200:
            return None
        from bs4 import BeautifulSoup
        soup = BeautifulSoup(r.text, 'html.parser')
        text = soup.get_text(separator=' ', strip=True)
        
        matches = re.findall(r'(\d[\d\s]*\d)\s*z[łl]\s*(?:netto|brutto)?\s*/\s*mies', text, re.IGNORECASE)
        prices_found = []
        for m in matches:
            clean_str = re.sub(r'[^\d]', '', m[0] if isinstance(m, tuple) else m)
            if clean_str.isdigit():
                val = int(clean_str)
                prices_found.append(val)
        if prices_found:
            return min(prices_found)
    except Exception as e:
        print(f"  ⚠ Scrape error na {url}: {e}")
    return None

def generate_feed_rows(model_label, trims_data, is_commercial):
    rows = []
    
    model_name = f'Peugeot {model_label}' if not is_commercial else f'Peugeot {model_label.capitalize()}'
    
    for trim_label, trim_info in trims_data.items():
        colors = trim_info['colors']
        if not colors:
            colors = [{'name': 'Standard', 'image': ''}]

        for engine in trim_info['engines']:
            fuel = engine["fuel_type"]
            engine_desc = engine["engine"]
            transmission = engine["transmission"]
            api_price = int(engine['api_price']) if engine['api_price'] > 0 else None
            
            if not api_price:
                continue
                
            page_url = get_model_url(model_label, fuel)
            
            if not hasattr(generate_feed_rows, "lease_cache"):
                generate_feed_rows.lease_cache = {}
            if page_url not in generate_feed_rows.lease_cache:
                generate_feed_rows.lease_cache[page_url] = scrape_model_lease_price(page_url)
            
            lease_val = generate_feed_rows.lease_cache[page_url]
            
            full_title = f'{model_name} {trim_label}' if trim_label != 'Standard' else model_name
            
            if lease_val:
                offer_type = 'LEASE'
                amount_price_str = f'{lease_val} PLN'
                amount_qualifier_str = 'per month'
                price_str = f'{api_price} PLN'
                tiktok_title = f'{full_title} · od {lease_val} PLN / mies.'
            else:
                offer_type = 'CASH'
                amount_price_str = f'{api_price} PLN'
                amount_qualifier_str = 'Total'
                price_str = f'{api_price} PLN'
                tiktok_title = f'{full_title} · od {api_price} PLN'
            
            tiktok_desc = f'Nowy {full_title} · {engine_desc} · Sprawdź ofertę!'

            for color in colors:
                color_name = color["name"]
                img_url = color["image"]

                vid = (f"PEU-{scraper_utils.generate_stable_id(model_label, length=4)}"
                       f"-{scraper_utils.generate_stable_id(trim_label, length=4)}"
                       f"-{scraper_utils.generate_stable_id(color_name, length=4)}"
                       f"-{scraper_utils.generate_stable_id(fuel + engine_desc, length=3)}")

                row = {
                    "vehicle_id": vid,
                    "title": tiktok_title,
                    "description": tiktok_desc,
                    "rodzaj": "modelowy",
                    "make": "Peugeot",
                    "model": model_name,
                    "year": "2025",
                    "link": page_url,
                    "image_link": img_url,
                    "exterior_color": color_name,
                    "additional_image_link": "",
                    'trim': trim_label,
                    'offer_disclaimer': 'Oferta ma charakter informacyjny. Szczegóły u autoryzowanego dealera Peugeot.',
                    'offer_disclaimer_url': page_url,
                    'price': price_str,
                    'offer_type': offer_type,
                    'term_length': '',
                    'offer_term_qualifier': '',
                    'amount_price': amount_price_str,
                    'amount_percentage': '',
                    'amount_qualifier': amount_qualifier_str,
                    'downpayment': '',
                    "downpayment_qualifier": "",
                    "emission_disclaimer": "",
                    "emission_disclaimer_url": "",
                    "emission_overlay_disclaimer": "",
                    "emission_image_link": "",
                    "fuel_type": fuel,
                }
                rows.append(row)
    return rows

def main():
    print("=" * 60)
    print("Peugeot Model Feed — API Configv3 Base Prices")
    print("=" * 60)

    print("\n[1/3] Pobieranie listy modeli z API...")
    btoc_models = fetch_all_derived_models(API_BASE_BTOC)
    btob_models = fetch_all_derived_models(API_BASE_BTOB)
    print(f"  Znaleziono: {len(btoc_models)} osobowych + {len(btob_models)} dostawczych")

    all_osobowe = []
    all_dostawcze = []
    seen_ids = set()

    print("\n[2/3] Przetwarzanie modeli...\n")
    all_models = []
    for m in btoc_models:
        all_models.append(("btoc", m))
    for m in btob_models:
        all_models.append(("btob", m))

    for api_type, model_info in all_models:
        model_id = model_info["id"]
        model_label = model_info["label"]
        if model_label in SKIP_MODELS:
            continue

        is_commercial = (api_type == "btob")
        api_base = API_BASE_BTOC if api_type == "btoc" else API_BASE_BTOB
        print(f"  📦 {model_label} ({model_id}) [{'dostawczy' if is_commercial else 'osobowy'}]")

        versions = fetch_api_versions(api_base, model_id)
        if not versions:
            print(f"    ⚠ Brak wersji w API — pomijam.")
            continue

        trims_data = extract_model_data_from_api(versions)
        trim_count = len(trims_data)
        engine_count = sum(len(t["engines"]) for t in trims_data.values())
        color_count = sum(len(t["colors"]) for t in trims_data.values())
        print(f"    API: {trim_count} trimów, {engine_count} silników, {color_count} kolorów")

        rows = generate_feed_rows(model_label, trims_data, is_commercial)

        for r in rows:
            if r["vehicle_id"] not in seen_ids:
                seen_ids.add(r["vehicle_id"])
                if is_commercial:
                    all_dostawcze.append(r)
                else:
                    all_osobowe.append(r)
        print(f"    ✅ Wygenerowano {len(rows)} wierszy\n")

    print("\n[3/3] Zapisywanie feedów modelowych...")
    fieldnames = [
        'vehicle_id', 'title', 'description', 'rodzaj', 'make', 'model', 'year', 'link', 'image_link',
        'exterior_color', 'additional_image_link', 'trim', 'offer_disclaimer',
        'offer_disclaimer_url', 'price', 'offer_type', 'term_length', 'offer_term_qualifier',
        'amount_price', 'amount_percentage', 'amount_qualifier', 'downpayment',
        'downpayment_qualifier', 'emission_disclaimer', 'emission_disclaimer_url',
        'emission_overlay_disclaimer', 'emission_image_link', 'fuel_type'
    ]

    print(f"  Osobowe: {len(all_osobowe)}")
    print(f"  Dostawcze: {len(all_dostawcze)}")

    scraper_utils.safe_save_csv(all_osobowe, fieldnames, OUTPUT_FILE_OSO, min_rows_threshold=1)
    scraper_utils.safe_save_csv(all_dostawcze, fieldnames, OUTPUT_FILE_DOS, min_rows_threshold=1)
    print("Zakończono.")

if __name__ == "__main__":
    main()

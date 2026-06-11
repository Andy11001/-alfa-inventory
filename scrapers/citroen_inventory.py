# -*- coding: utf-8 -*-
"""
Citroën Inventory (Stock) Feed
- Lista produktów: WordPress JSON API (sklep.citroen.pl)
- Raty + miasto dealera: bezpośrednie API kalkulatora SFS (sfs_calculator),
  bez Selenium — patrz scrapers/sfs_calculator.py
- Wyjście: citroen_osobowe_inventory.csv + citroen_lcv_inventory.csv
"""
import requests
import json
import re
import os
import sys

if sys.stdout.encoding and sys.stdout.encoding.lower() != "utf-8":
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

try:
    from scrapers import scraper_utils, sfs_calculator
except ModuleNotFoundError:
    import scraper_utils
    import sfs_calculator

API_URL = "https://sklep.citroen.pl/wp-json/wp/v2/product"
BASE_URL = "https://sklep.citroen.pl"
OUTPUT_DIR = os.path.join(os.path.dirname(os.path.dirname(__file__)), "data")
OUTPUT_FILE_OSO = os.path.join(OUTPUT_DIR, "citroen_osobowe_inventory.csv")
OUTPUT_FILE_LCV = os.path.join(OUTPUT_DIR, "citroen_lcv_inventory.csv")
IMAGES_DIR = os.path.join(OUTPUT_DIR, "images")
GITHUB_BASE_IMAGE_URL = "https://raw.githubusercontent.com/Andy11001/-alfa-inventory/master/data/images"

LCV_MODELS = ["Berlingo", "Berlingo Van", "ë-Berlingo", "Jumpy", "ë-Jumpy", "Jumper", "ë-Jumper"]

MODEL_MAP = {
    "c3": "C3", "c3-aircross": "C3 Aircross", "nowy-c3-aircross": "Nowy C3 Aircross",
    "nowy-c3": "Nowy C3", "c4": "C4", "e-c4": "ë-C4", "c4-x": "C4 X",
    "e-c4-x": "ë-C4 X", "c5-aircross": "C5 Aircross",
    "nowy-c5-aircross": "Nowy C5 Aircross",
    "berlingo": "Berlingo", "e-berlingo": "ë-Berlingo",
    "berlingo-van": "Berlingo Van",
    "jumpy": "Jumpy", "e-jumpy": "ë-Jumpy",
    "jumper": "Jumper", "e-jumper": "ë-Jumper",
    "spacetourer": "SpaceTourer", "e-spacetourer": "ë-SpaceTourer",
}

CITY_TO_REGION = {
    "Kraków": "Małopolskie", "Warszawa": "Mazowieckie",
    "Wrocław": "Dolnośląskie", "Poznań": "Wielkopolskie",
    "Gdańsk": "Pomorskie", "Katowice": "Śląskie",
    "Łódź": "Łódzkie", "Szczecin": "Zachodniopomorskie",
    "Opole": "Opolskie", "Bielsko-Biała": "Śląskie",
    "Lublin": "Lubelskie", "Bydgoszcz": "Kujawsko-Pomorskie",
    "Toruń": "Kujawsko-Pomorskie", "Rzeszów": "Podkarpackie",
    "Radom": "Mazowieckie", "Kielce": "Świętokrzyskie",
    "Białystok": "Podlaskie", "Słupsk": "Pomorskie",
    "Gliwice": "Śląskie", "Rybnik": "Śląskie",
}

DEALER_LOCATIONS = {
    "Kraków": {"lat": "50.0931", "lon": "19.9238", "street": "ul. Opolska 9"},
    "Warszawa": {"lat": "52.2084", "lon": "20.9412", "street": "Al. Krakowska 206"},
    "Wrocław": {"lat": "51.1274", "lon": "16.9535", "street": "ul. Szczecińska 7"},
    "Poznań": {"lat": "52.3787", "lon": "17.0270", "street": "ul. Krzywoustego 71"},
    "Gdańsk": {"lat": "54.4022", "lon": "18.5714", "street": "al. Grunwaldzka 256"},
    "Katowice": {"lat": "50.2649", "lon": "19.0238", "street": "Al. Roździeńskiego 170"},
    "Łódź": {"lat": "51.7371", "lon": "19.4316", "street": "ul. Obywatelska 181"},
    "Szczecin": {"lat": "53.3891", "lon": "14.6543", "street": "ul. Struga 1b"},
}

FIELDNAMES = [
    "vehicle_id", "title", "description", "link", "image_link",
    "make", "model", "year", "mileage.value", "mileage.unit",
    "body_style", "exterior_color", "state_of_vehicle",
    "price", "currency", "address", "latitude", "longitude",
    "offer_type", "amount_price", "amount_qualifier",
    "fuel_type", "transmission", "drivetrain",
]


def format_address_json(street, city):
    region = CITY_TO_REGION.get(city, "Mazowieckie")
    return json.dumps({
        "addr1": street.upper(), "city": city.upper(),
        "region": region.upper(), "country": "PL"
    }, ensure_ascii=False)


def match_dealer_city(raw_city, raw_name):
    """Miasto z dataLayer -> znana lokalizacja; nieznane miasto zostaje
    (Citroën akceptował surowe miasta spoza listy)."""
    if raw_city:
        cand = raw_city.strip()
        for known in DEALER_LOCATIONS:
            if known.upper() == cand.upper():
                return known
        if len(cand) > 1:
            return cand
    if raw_name:
        up = raw_name.upper()
        for known in DEALER_LOCATIONS:
            if known.upper() in up:
                return known
    return "Warszawa"


def download_image(url, filepath):
    if os.path.exists(filepath):
        return True
    try:
        r = requests.get(url, stream=True, timeout=10, headers={"User-Agent": "Mozilla/5.0"})
        if r.status_code == 200:
            with open(filepath, "wb") as f:
                for chunk in r.iter_content(1024):
                    f.write(chunk)
            return True
    except Exception:
        pass
    return False


def get_model_slug(product):
    classes = product.get("class_list", {})
    class_values = classes.values() if isinstance(classes, dict) else classes
    for cls in class_values:
        if cls.startswith("product_cat-"):
            slug = cls.replace("product_cat-", "")
            if slug not in ["bez-kategorii"]:
                return slug
    # Fallback ze ścieżki URL: /produkt/<model>/<vin>/
    link_match = re.search(r"/produkt/([^/]+)/", product.get("link") or "")
    if link_match and link_match.group(1) != "bez-kategorii":
        return link_match.group(1)
    return None


def fetch_wp_products():
    all_products = []
    page = 1
    session = requests.Session()
    session.headers.update({"User-Agent": "Mozilla/5.0"})
    while True:
        try:
            r = session.get(f"{API_URL}?per_page=100&page={page}", timeout=15)
            if r.status_code == 400:
                break
            r.raise_for_status()
            data = r.json()
            if not data:
                break
            all_products.extend(data)
            print(f"  Strona {page} ({len(data)} aut, łącznie: {len(all_products)})")
            page += 1
        except Exception as e:
            print(f"  Koniec przy stronie {page}: {e}")
            break
    return all_products


def build_row(product, rate_info):
    pid = str(product.get("id"))
    link = product.get("link")
    title_raw = product.get("title", {}).get("rendered", "")
    vin = title_raw if len(title_raw) == 17 else f"CIT-{pid}"

    model_slug = get_model_slug(product)
    if not model_slug:
        return None
    model = MODEL_MAP.get(model_slug, model_slug.replace("-", " ").title())
    if model in ["Bez Kategorii"]:
        return None

    classes = product.get("class_list", {})
    class_values = classes.values() if isinstance(classes, dict) else classes

    color = "Standard"
    fuel = "Gasoline"
    trans = "Manual"
    trim = ""
    year = "2025"
    body_style = "SUV"

    for cls in class_values:
        if cls.startswith("pa_kolor-"):
            color = cls.replace("pa_kolor-", "").replace("-", " ").title()
        elif cls.startswith("pa_typ-paliwa-"):
            f_val = cls.replace("pa_typ-paliwa-", "")
            if "hybryda" in f_val or "mhev" in f_val:
                fuel = "Hybrid"
            elif "elektryczn" in f_val:
                fuel = "Electric"
            elif "diesel" in f_val:
                fuel = "Diesel"
        elif cls.startswith("pa_typ-skrzyni-"):
            if "automat" in cls:
                trans = "Automatic"
        elif cls.startswith("pa_poziom-wyposazenia-"):
            trim = cls.replace("pa_poziom-wyposazenia-", "").replace("-", " ").title()
        elif cls.startswith("pa_rok-produkcji-"):
            yr = cls.replace("pa_rok-produkcji-", "")
            if len(yr) == 4 and yr.isdigit():
                year = yr
        elif cls.startswith("pa_typ-nadwozia-"):
            b = cls.replace("pa_typ-nadwozia-", "")
            if b in ["suv", "crossover"]:
                body_style = "SUV"
            elif b in ["van", "furgon"]:
                body_style = "Van"
            elif b in ["hatchback", "hatchback-5-drzwi"]:
                body_style = "Hatchback"
            elif b in ["kombi", "sw"]:
                body_style = "Wagon"

    if rate_info and rate_info.get("year"):
        year = rate_info["year"]

    if not rate_info or not rate_info.get("installment"):
        return None
    clean_installment = str(rate_info["installment"])

    full_price = ""
    gross = rate_info.get("gross_price")
    if isinstance(gross, (int, float)) and gross > 10000:
        full_price = f"{int(round(gross))} PLN"
    if not full_price:
        yoast_desc = product.get("yoast_head_json", {}).get("description", "")
        price_match = re.search(r"([\d\s]+)\s*zł", yoast_desc)
        if price_match:
            full_price = f"{re.sub(r'[^0-9]', '', price_match.group(1))} PLN"
    if not full_price:
        full_price = "100000 PLN"

    image = ""
    imgs = product.get("yoast_head_json", {}).get("og_image", [])
    if imgs:
        image = imgs[0].get("url", "")
    if image:
        ext = ".webp" if image.endswith(".webp") else ".jpg"
        image_filename = f"{vin}_clean{ext}"
        local_path = os.path.join(IMAGES_DIR, image_filename)
        if download_image(image, local_path):
            image = f"{GITHUB_BASE_IMAGE_URL}/{image_filename}"

    detected_city = match_dealer_city(rate_info.get("dealer_city"),
                                      rate_info.get("dealer_name"))
    dealer_data = DEALER_LOCATIONS.get(detected_city, DEALER_LOCATIONS["Warszawa"])
    address_text = format_address_json(dealer_data["street"], detected_city)

    is_commercial = any(lcv.lower() in model.lower() for lcv in LCV_MODELS)

    tiktok_title = scraper_utils.format_inventory_title(model, trim, clean_installment)
    tiktok_desc = scraper_utils.format_inventory_description(
        "Citroën", model, trim, clean_installment, detected_city)

    row = {
        "vehicle_id": vin,
        "title": tiktok_title,
        "description": tiktok_desc,
        "link": link,
        "image_link": image,
        "make": "Citroën",
        "model": model,
        "year": year,
        "mileage.value": 0,
        "mileage.unit": "KM",
        "body_style": body_style,
        "exterior_color": color,
        "state_of_vehicle": "New",
        "price": full_price,
        "currency": "PLN",
        "address": address_text,
        "latitude": dealer_data.get("lat", "52.2297"),
        "longitude": dealer_data.get("lon", "21.0122"),
        "offer_type": "LEASE",
        "amount_price": f"{clean_installment} PLN",
        "amount_qualifier": "per month",
        "fuel_type": fuel,
        "transmission": trans,
        "drivetrain": "FWD",
    }
    return {"row": row, "is_commercial": is_commercial}


def main():
    print("=" * 60)
    print("Citroën Inventory Feed — sklep.citroen.pl (API SFS, bez Selenium)")
    print("=" * 60)

    os.makedirs(IMAGES_DIR, exist_ok=True)

    print("\n[1/3] Pobieranie listy produktów z API...")
    all_products = fetch_wp_products()
    all_products = [p for p in all_products if get_model_slug(p) and p.get("link")]
    limit = int(os.environ.get("SFS_LIMIT", "0"))
    if limit:
        all_products = all_products[:limit]
    print(f"  Po odfiltrowaniu duchów: {len(all_products)} produktów")

    print("\n[2/3] Raty + lokalizacje przez API SFS...")
    links = [p["link"] for p in all_products]
    rates, stats = sfs_calculator.get_inventory_rates("citroen", links)

    osobowe_rows, lcv_rows = [], []
    for product in all_products:
        res = build_row(product, rates.get(product["link"]))
        if res:
            (lcv_rows if res["is_commercial"] else osobowe_rows).append(res["row"])

    print(f"\n[3/3] Zapisywanie: Osobowe ({len(osobowe_rows)}), Dostawcze ({len(lcv_rows)})")
    scraper_utils.safe_save_csv(osobowe_rows, FIELDNAMES, OUTPUT_FILE_OSO, min_rows_threshold=0)
    scraper_utils.safe_save_csv(lcv_rows, FIELDNAMES, OUTPUT_FILE_LCV, min_rows_threshold=0)
    print("Zakończono.")


if __name__ == "__main__":
    main()

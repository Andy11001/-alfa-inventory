"""
Citroën Inventory (Stock) Feed
- Data source: WordPress JSON API at sklep.citroen.pl
- Installment prices: Selenium B2B scraping
- Output: two CSVs — citroen_osobowe_inventory.csv + citroen_lcv_inventory.csv
"""
import requests
import csv
import json
import re
import time
import os
import sys
from concurrent.futures import ThreadPoolExecutor, as_completed

sys.stdout.reconfigure(encoding="utf-8")

try:
    from scrapers import scraper_utils
except ModuleNotFoundError:
    import scraper_utils

API_URL = "https://sklep.citroen.pl/wp-json/wp/v2/product"
BASE_URL = "https://sklep.citroen.pl"
OUTPUT_DIR = os.path.join(os.path.dirname(os.path.dirname(__file__)), "data")
OUTPUT_FILE_OSO = os.path.join(OUTPUT_DIR, "citroen_osobowe_inventory.csv")
OUTPUT_FILE_LCV = os.path.join(OUTPUT_DIR, "citroen_lcv_inventory.csv")
IMAGES_DIR = os.path.join(OUTPUT_DIR, "images")
GITHUB_BASE_IMAGE_URL = "https://raw.githubusercontent.com/Andy11001/-alfa-inventory/master/data/images"

LCV_MODELS = ["Berlingo", "Jumpy", "Jumper", "Berlingo Van", "e-Berlingo", "e-Jumpy", "e-Jumper"]

MODEL_MAP = {
    # Readable slugs
    "c3": "C3", "c3-aircross": "C3 Aircross", "nowy-c3-aircross": "Nowy C3 Aircross",
    "nowy-c3": "Nowy C3", "c4": "C4", "e-c4": "ë-C4", "c4-x": "C4 X",
    "e-c4-x": "ë-C4 X", "c5-aircross": "C5 Aircross",
    "nowy-c5-aircross": "Nowy C5 Aircross",
    "berlingo": "Berlingo", "e-berlingo": "ë-Berlingo",
    "jumpy": "Jumpy", "e-jumpy": "ë-Jumpy",
    "jumper": "Jumper", "e-jumper": "ë-Jumper",
    "spacetourer": "SpaceTourer", "e-spacetourer": "ë-SpaceTourer",
    "berlingo-van": "Berlingo Van",
}

CITY_TO_REGION = {
    "Kraków": "Małopolskie", "Warszawa": "Mazowieckie",
    "Wrocław": "Dolnośląskie", "Poznań": "Wielkopolskie",
    "Gdańsk": "Pomorskie", "Katowice": "Śląskie",
    "Łódź": "Łódzkie", "Szczecin": "Zachodniopomorskie",
    "Opole": "Opolskie", "Bielsko-Biała": "Śląskie",
    "Lublin": "Lubelskie", "Bydgoszcz": "Kujawsko-Pomorskie",
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


def format_address_json(street, city):
    region = CITY_TO_REGION.get(city, "Mazowieckie")
    return json.dumps({
        "addr1": street.upper(), "city": city.upper(),
        "region": region.upper(), "country": "PL"
    }, ensure_ascii=False)


def process_product(product, index, total_count, driver=None):
    try:
        from scrapers.selenium_helper import get_b2b_price_selenium
    except:
        try:
            from selenium_helper import get_b2b_price_selenium
        except:
            get_b2b_price_selenium = None

    pid = str(product.get("id"))
    link = product.get("link")
    title_raw = product.get("title", {}).get("rendered", "")
    vin = title_raw if len(title_raw) == 17 else f"CIT-{pid}"

    classes = product.get("class_list", {})
    model_slug = ""
    for cls in classes.values():
        if cls.startswith("product_cat-"):
            model_slug = cls.replace("product_cat-", "")
            if model_slug not in ["bez-kategorii"]:
                break

    if not model_slug or model_slug == "bez-kategorii":
        return None

    model = MODEL_MAP.get(model_slug, model_slug.replace("-", " ").title())
    is_commercial = any(lcv.lower() in model.lower() for lcv in LCV_MODELS)

    color = "Standard"
    fuel = "Gasoline"
    trans = "Manual"
    trim = ""
    year = "2025"

    for cls in classes.values():
        if cls.startswith("pa_kolor-"):
            color = cls.replace("pa_kolor-", "").replace("-", " ").title()
        elif cls.startswith("pa_typ-paliwa-"):
            f_val = cls.replace("pa_typ-paliwa-", "")
            if "hybryd" in f_val or "mhev" in f_val:
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
            y = cls.replace("pa_rok-produkcji-", "")
            if len(y) == 4:
                year = y

    # Price from Yoast
    full_price = ""
    yoast_desc = product.get("yoast_head_json", {}).get("description", "")
    price_match = re.search(r"od\s+([\d\s]+)\s*zł", yoast_desc)
    if price_match:
        installment_raw = re.sub(r"[^0-9]", "", price_match.group(1))
    else:
        installment_raw = ""

    # Try to get full price from meta
    price_match2 = re.search(r"([\d\s]+)\s*zł", yoast_desc)
    if price_match2:
        full_price = f"{re.sub(r'[^0-9]', '', price_match2.group(1))} PLN"

    # Selenium B2B price (optional)
    detected_city = "Warszawa"
    if driver and get_b2b_price_selenium:
        try:
            b2b_price = get_b2b_price_selenium(link, driver=driver)
            if b2b_price:
                installment_raw = b2b_price
                print(f"  [{index}/{total_count}] {vin}: Rata = {b2b_price} PLN")
            else:
                print(f"  [{index}/{total_count}] {vin}: Brak raty B2B")

            page_source = driver.page_source
            city_match = re.search(r'"edealerCity"\s*:\s*"([^"]+)"', page_source)
            if city_match and city_match.group(1):
                candidate = city_match.group(1)
                for known_city in DEALER_LOCATIONS:
                    if known_city.upper() == candidate.upper():
                        detected_city = known_city
                        break
        except Exception as e:
            print(f"  [{index}/{total_count}] {vin}: Err {e}")
    else:
        if index % 50 == 0:
            print(f"  [{index}/{total_count}] {vin}: (no Selenium)")

    clean_installment = re.sub(r"[^0-9]", "", str(installment_raw))
    if not clean_installment or not clean_installment.isdigit() or int(clean_installment) <= 0:
        # Still include but as CASH with full price
        if not full_price:
            return None
        amount_price_final = full_price
        offer_type = "CASH"
        qualifier = "Total"
    else:
        amount_price_final = f"{clean_installment} PLN"
        offer_type = "LEASE"
        qualifier = "per month"

    if not full_price:
        full_price = "100000 PLN"

    image = ""
    imgs = product.get("yoast_head_json", {}).get("og_image", [])
    if imgs:
        image = imgs[0].get("url", "")

    dealer_data = DEALER_LOCATIONS.get(detected_city, DEALER_LOCATIONS["Warszawa"])
    address_text = format_address_json(dealer_data["street"], detected_city)

    tiktok_title = scraper_utils.format_inventory_title(model, trim, clean_installment if offer_type == "LEASE" else "")
    tiktok_desc = scraper_utils.format_inventory_description("Citroën", model, trim, clean_installment if offer_type == "LEASE" else "", detected_city)

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
        "body_style": "Van" if is_commercial else "SUV",
        "exterior_color": color,
        "state_of_vehicle": "New",
        "price": full_price,
        "currency": "PLN",
        "address": address_text,
        "latitude": dealer_data["lat"],
        "longitude": dealer_data["lon"],
        "offer_type": offer_type,
        "amount_price": amount_price_final,
        "amount_qualifier": qualifier,
        "fuel_type": fuel,
        "transmission": trans,
        "drivetrain": "FWD",
    }
    return {"row": row, "is_commercial": is_commercial}


def main():
    print("=" * 60)
    print("Citroën Inventory Feed — sklep.citroen.pl WP API")
    print("=" * 60)
    os.makedirs(IMAGES_DIR, exist_ok=True)

    print("\n[1/3] Pobieranie listy produktów z API...")
    all_products = []
    page = 1
    session = requests.Session()
    session.headers.update({"User-Agent": "Mozilla/5.0"})

    while True:
        try:
            url = f"{API_URL}?per_page=100&page={page}"
            r = session.get(url, timeout=15)
            if r.status_code == 400:
                break
            r.raise_for_status()
            data = r.json()
            if not data:
                break
            all_products.extend(data)
            print(f"  Strona {page} ({len(data)} aut)")
            page += 1
        except Exception as e:
            print(f"  Koniec przy stronie {page}: {e}")
            break

    total = len(all_products)
    print(f"  Łącznie: {total} produktów")

    print("\n[2/3] Przetwarzanie ofert (bez Selenium)...")
    osobowe_rows = []
    dostawcze_rows = []

    for i, p in enumerate(all_products, 1):
        result = process_product(p, i, total)
        if result:
            if result["is_commercial"]:
                dostawcze_rows.append(result["row"])
            else:
                osobowe_rows.append(result["row"])

    fieldnames = [
        "vehicle_id", "title", "description", "link", "image_link",
        "make", "model", "year", "mileage.value", "mileage.unit",
        "body_style", "exterior_color", "state_of_vehicle",
        "price", "currency", "address", "latitude", "longitude",
        "offer_type", "amount_price", "amount_qualifier",
        "fuel_type", "transmission", "drivetrain",
    ]

    print(f"\n[3/3] Zapisywanie: Osobowe ({len(osobowe_rows)}), Dostawcze ({len(dostawcze_rows)})")
    scraper_utils.safe_save_csv(osobowe_rows, fieldnames, OUTPUT_FILE_OSO, min_rows_threshold=1)
    scraper_utils.safe_save_csv(dostawcze_rows, fieldnames, OUTPUT_FILE_LCV, min_rows_threshold=1)
    print("Zakończono.")


if __name__ == "__main__":
    main()

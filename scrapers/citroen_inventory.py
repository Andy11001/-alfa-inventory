"""
Citroën Inventory (Stock) Feed
- Data source: WordPress JSON API at sklep.citroen.pl
- Installment prices + dealer city: Selenium B2B scraping
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


def format_address_json(street, city):
    region = CITY_TO_REGION.get(city, "Mazowieckie")
    return json.dumps({
        "addr1": street.upper(), "city": city.upper(),
        "region": region.upper(), "country": "PL"
    }, ensure_ascii=False)


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


def process_product(product, index, total_count, driver):
    try:
        from scrapers.selenium_helper import get_b2b_price_selenium
    except ImportError:
        from selenium_helper import get_b2b_price_selenium

    pid = str(product.get("id"))
    link = product.get("link")
    title_raw = product.get("title", {}).get("rendered", "")
    vin = title_raw if len(title_raw) == 17 else f"CIT-{pid}"

    classes = product.get("class_list", {})

    # Model from product_cat
    model_slug = ""
    for cls in classes.values():
        if cls.startswith("product_cat-"):
            slug = cls.replace("product_cat-", "")
            if slug not in ["bez-kategorii"]:
                model_slug = slug
                break

    if not model_slug:
        link_match = re.search(r"/produkt/([^/]+)/", link or "")
        if link_match:
            model_slug = link_match.group(1)

    if model_slug:
        model = MODEL_MAP.get(model_slug, model_slug.replace("-", " ").title())
    else:
        return None

    if model_slug in ["bez-kategorii", ""] or model in ["Bez Kategorii"]:
        return None

    # Attributes from CSS classes
    color = "Standard"
    fuel = "Gasoline"
    trans = "Manual"
    trim = ""
    year = "2025"
    body_style = "SUV"

    for cls in classes.values():
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

    # Price from yoast
    full_price = ""
    yoast_desc = product.get("yoast_head_json", {}).get("description", "")
    price_match = re.search(r"([\d\s]+)\s*zł", yoast_desc)
    if price_match:
        full_price = f"{re.sub(r'[^0-9]', '', price_match.group(1))} PLN"

    # Selenium: B2B price + dealer city
    installment = ""
    detected_city = "Warszawa"
    try:
        b2b_price = get_b2b_price_selenium(link, driver=driver)
        if b2b_price:
            installment = b2b_price
            print(f"  [{index}/{total_count}] {vin}: Rata = {b2b_price} PLN")
        else:
            print(f"  [{index}/{total_count}] {vin}: Brak raty B2B")

        # Extract dealer city from dataLayer
        try:
            page_source = driver.page_source
            city_match = re.search(r'"edealerCity"\s*:\s*"([^"]+)"', page_source)
            if city_match and city_match.group(1):
                candidate = city_match.group(1).strip()
                if candidate:
                    for known_city in DEALER_LOCATIONS:
                        if known_city.upper() == candidate.upper():
                            detected_city = known_city
                            break
                    else:
                        if len(candidate) > 1:
                            detected_city = candidate
            else:
                name_match = re.search(r'"edealerName"\s*:\s*"([^"]+)"', page_source)
                if name_match:
                    dealer_name = name_match.group(1).upper()
                    for city in DEALER_LOCATIONS:
                        if city.upper() in dealer_name:
                            detected_city = city
                            break
        except Exception:
            pass

    except Exception as e:
        print(f"  [{index}/{total_count}] {vin}: Err Selenium {e}")

    clean_installment = installment.replace("PLN", "").replace(" ", "").strip()
    if not clean_installment or not clean_installment.isdigit() or int(clean_installment) <= 0:
        return None

    if not full_price:
        full_price = "100000 PLN"

    amount_price_final = f"{clean_installment} PLN"

    # Image
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

    # Address
    dealer_data = DEALER_LOCATIONS.get(detected_city, DEALER_LOCATIONS["Warszawa"])
    address_text = format_address_json(dealer_data["street"], detected_city)
    lat = dealer_data.get("lat", "52.2297")
    lon = dealer_data.get("lon", "21.0122")

    is_commercial = any(lcv.lower() in model.lower() for lcv in LCV_MODELS)

    tiktok_title = scraper_utils.format_inventory_title(model, trim, clean_installment)
    tiktok_desc = scraper_utils.format_inventory_description("Citroën", model, trim, clean_installment, detected_city)

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
        "latitude": lat,
        "longitude": lon,
        "offer_type": "LEASE",
        "amount_price": amount_price_final,
        "amount_qualifier": "per month",
        "fuel_type": fuel,
        "transmission": trans,
        "drivetrain": "FWD",
    }
    return {"row": row, "is_commercial": is_commercial}


def process_chunk(chunk, chunk_id, total_count, base_index):
    try:
        from scrapers.selenium_helper import init_driver
    except ImportError:
        from selenium_helper import init_driver

    driver = None
    results = []
    try:
        driver = init_driver()
        for i, p in enumerate(chunk):
            if i > 0 and i % 50 == 0:
                print(f"  [Chunk {chunk_id}] Restarting driver to free RAM...")
                try: driver.quit()
                except: pass
                driver = init_driver()

            real_index = base_index + i + 1
            res = process_product(p, real_index, total_count, driver)
            if res:
                results.append(res)
            try: driver.delete_all_cookies()
            except: pass
    except Exception as e:
        print(f"Chunk {chunk_id} error: {e}")
    finally:
        if driver:
            try: driver.quit()
            except: pass

    return results


def main():
    print("=" * 60)
    print("Citroën Inventory Feed — sklep.citroen.pl (Selenium)")
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
            print(f"  Strona {page} ({len(data)} aut, łącznie: {len(all_products)})")
            page += 1
        except Exception as e:
            print(f"  Koniec przy stronie {page}: {e}")
            break

    total = len(all_products)
    print(f"  Łącznie: {total} produktów")

    print("\n[2/3] Przetwarzanie ofert (Selenium B2B + lokalizacja)...\n")

    MAX_WORKERS = 2
    chunk_size = (total + MAX_WORKERS - 1) // MAX_WORKERS
    chunks = [all_products[i * chunk_size:(i + 1) * chunk_size] for i in range(MAX_WORKERS)]

    all_results = []
    with ThreadPoolExecutor(max_workers=MAX_WORKERS) as executor:
        futures = []
        base_idx = 0
        for i, chunk in enumerate(chunks):
            futures.append(executor.submit(process_chunk, chunk, i + 1, total, base_idx))
            base_idx += len(chunk)

        for future in as_completed(futures):
            try:
                res_list = future.result()
                if res_list:
                    all_results.extend(res_list)
            except Exception as e:
                print(f"  Błąd wątku: {e}")

    osobowe_rows = [r["row"] for r in all_results if not r["is_commercial"]]
    lcv_rows = [r["row"] for r in all_results if r["is_commercial"]]

    fieldnames = [
        "vehicle_id", "title", "description", "link", "image_link",
        "make", "model", "year", "mileage.value", "mileage.unit",
        "body_style", "exterior_color", "state_of_vehicle",
        "price", "currency", "address", "latitude", "longitude",
        "offer_type", "amount_price", "amount_qualifier",
        "fuel_type", "transmission", "drivetrain",
    ]

    print(f"\n[3/3] Zapisywanie: Osobowe ({len(osobowe_rows)}), Dostawcze ({len(lcv_rows)})")
    scraper_utils.safe_save_csv(osobowe_rows, fieldnames, OUTPUT_FILE_OSO, min_rows_threshold=0)
    scraper_utils.safe_save_csv(lcv_rows, fieldnames, OUTPUT_FILE_LCV, min_rows_threshold=0)
    print("Zakończono.")


if __name__ == "__main__":
    main()

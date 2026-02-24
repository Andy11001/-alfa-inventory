import requests
import csv
import json
import re
import time
import os
from concurrent.futures import ThreadPoolExecutor, as_completed

try:
    from scrapers import scraper_utils
except ModuleNotFoundError:
    import scraper_utils

API_URL = "https://sklep.opel.pl/wp-json/wp/v2/product"
BASE_URL = "https://sklep.opel.pl"
OUTPUT_DIR = os.path.join(os.path.dirname(os.path.dirname(__file__)), "data")
OUTPUT_FILE_OSO = os.path.join(OUTPUT_DIR, "opel_osobowe_inventory.csv")
OUTPUT_FILE_DOS = os.path.join(OUTPUT_DIR, "opel_dostawcze_inventory.csv")
IMAGES_DIR = os.path.join(OUTPUT_DIR, "images")
GITHUB_BASE_IMAGE_URL = "https://raw.githubusercontent.com/Andy11001/-alfa-inventory/master/data/images"

DOS_CATEGORIES = ["combo-cargo", "movano", "vivaro", "vivaro-zafira"]

CITY_TO_REGION = {
    "Kraków": "Małopolskie",    "Warszawa": "Mazowieckie",
    "Wrocław": "Dolnośląskie",  "Poznań": "Wielkopolskie",
    "Gdańsk": "Pomorskie",      "Katowice": "Śląskie",
    "Łódź": "Łódzkie",          "Szczecin": "Zachodniopomorskie",
    "Opole": "Opolskie",        "Bielsko-Biała": "Śląskie"
}

DEALER_LOCATIONS = {
    "Kraków": {"lat": "50.0931", "lon": "19.9238", "street": "ul. Opolska 9"},
    "Warszawa": {"lat": "52.2084", "lon": "20.9412", "street": "Al. Krakowska 206"},
    "Wrocław": {"lat": "51.1274", "lon": "16.9535", "street": "ul. Szczecińska 7"},
    "Poznań": {"lat": "52.3787", "lon": "17.0270", "street": "ul. Bolesława Krzywoustego 71"},
    "Gdańsk": {"lat": "54.4022", "lon": "18.5714", "street": "al. Grunwaldzka 256"},
    "Katowice": {"lat": "50.2649", "lon": "19.0238", "street": "Al. Roździeńskiego 170"},
    "Łódź": {"lat": "51.7371", "lon": "19.4316", "street": "ul. Obywatelska 181"},
    "Szczecin": {"lat": "53.3891", "lon": "14.6543", "street": "ul. Struga 1b"},
    "Opole": {"lat": "50.6751", "lon": "17.9213", "street": "ul. Wrocławska 137"},
    "Bielsko-Biała": {"lat": "49.8225", "lon": "19.0444", "street": "ul. Warszawska 15"}
}

def format_address_json(street, city):
    region = CITY_TO_REGION.get(city, "Mazowieckie")
    addr = {
        "addr1": street.upper(),
        "city": city.upper(),
        "region": region.upper(),
        "country": "PL"
    }
    return json.dumps(addr, ensure_ascii=False)

def download_image_clean(url, filepath):
    if os.path.exists(filepath):
        return True
    try:
        r = scraper_utils.fetch_with_retry(requests, url, stream=True, timeout=10)
        if r.status_code == 200:
            with open(filepath, 'wb') as f:
                for chunk in r.iter_content(1024):
                    f.write(chunk)
            return True
    except Exception as e:
        pass
    return False

def process_product(product, index, total_count):
    try:
        from scrapers.selenium_helper import init_driver, get_b2b_price_selenium
    except:
        from selenium_helper import init_driver, get_b2b_price_selenium
    
    pid = str(product.get("id"))
    link = product.get("link")
    title_raw = product.get("title", {}).get("rendered", "")
    vin = title_raw if len(title_raw) == 17 else f"OPEL-{pid}"
    
    classes = product.get("class_list", {})
    model_slug = ""
    for cls in classes.values():
        if cls.startswith("product_cat-"):
            model_slug = cls.replace("product_cat-", "")
            if model_slug not in ["bez-kategorii"]:
                break
            
    if not model_slug or model_slug == "bez-kategorii":
        return None
        
    model = model_slug.replace("-", " ").title()
    is_commercial = any(d in model_slug for d in DOS_CATEGORIES)
    
    color = "Standard"
    fuel = "Gasoline"
    trans = "Manual"
    drive = "FWD"
    trim = ""
    year = "2024"

    for cls in classes.values():
        if cls.startswith("pa_kolor-"):
            color = cls.replace("pa_kolor-", "").replace("-", " ").title()
        elif cls.startswith("pa_typ-paliwa-"):
            f_val = cls.replace("pa_typ-paliwa-", "")
            if "hybryd" in f_val: fuel = "Hybrid"
            elif "elektryczn" in f_val: fuel = "Electric"
            elif "diesel" in f_val: fuel = "Diesel"
        elif cls.startswith("pa_typ-skrzyni-"):
            if "automat" in cls: trans = "Automatic"
        elif cls.startswith("pa_poziom-wyposazenia-"):
            trim = cls.replace("pa_poziom-wyposazenia-", "").replace("-", " ").title()
        elif cls.startswith("pa_rok-produkcji-"):
             year = cls.replace("pa_rok-produkcji-", "")
             if len(year) != 4: year = "2024"
    
    full_price = ""
    yoast_desc = product.get("yoast_head_json", {}).get("description", "")
    price_match = re.search(r'([\d\s]+)\s*z\ł', yoast_desc)
    if price_match:
        full_price = f"{re.sub(r'[^0-9]', '', price_match.group(1))} PLN"

    installment = ""
    driver = None
    try:
        driver = init_driver()
        b2b_price = get_b2b_price_selenium(link, driver=driver)
        if b2b_price:
            installment = b2b_price
            print(f"  [{index}/{total_count}] {vin}: Rata = {b2b_price} PLN")
        else:
             print(f"  [{index}/{total_count}] {vin}: Brak raty B2B")
    except Exception as e:
         print(f"  [{index}/{total_count}] {vin}: Err Selenium {e}")
    finally:
        if driver:
            try: driver.quit()
            except: pass
            
    clean_installment = installment.replace("PLN", "").replace(" ", "").strip()
    if not clean_installment or not clean_installment.isdigit() or int(clean_installment) <= 0:
        return None
        
    if not full_price: full_price = "150000 PLN"
    
    amount_price_final = f"{clean_installment} PLN"

    image = ""
    imgs = product.get("yoast_head_json", {}).get("og_image", [])
    if imgs:
        image = imgs[0].get("url")

    if image:
        image_filename = f"{vin}_clean.jpg"
        local_image_path = os.path.join(IMAGES_DIR, image_filename)
        if download_image_clean(image, local_image_path):
            image = f"{GITHUB_BASE_IMAGE_URL}/{image_filename}"

    detected_city = "Warszawa"
    dealer_data = DEALER_LOCATIONS["Warszawa"]
    address_text = format_address_json(dealer_data["street"], detected_city)

    tiktok_title = scraper_utils.format_inventory_title(model, trim, clean_installment)
    tiktok_desc = scraper_utils.format_inventory_description("Opel", model, trim, clean_installment, detected_city)

    row = {
        "vehicle_id": vin,
        "title": tiktok_title,
        "description": tiktok_desc,
        "link": link,
        "image_link": image,
        "make": "Opel",
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
        "offer_type": "LEASE",
        "amount_price": amount_price_final,
        "amount_qualifier": "per month",
        "fuel_type": fuel,
        "transmission": trans,
        "drivetrain": drive
    }
    
    return {"row": row, "is_commercial": is_commercial}

def main():
    print("Pobieranie listy pojazdów z API sklepu Opel...")
    os.makedirs(IMAGES_DIR, exist_ok=True)
    
    all_products = []
    page = 1
    session = requests.Session()
    session.headers.update({"User-Agent": "Mozilla/5.0"})

    while True:
        try:
            r = scraper_utils.fetch_with_retry(session, f"{API_URL}?per_page=100&page={page}", timeout=10)
            if r.status_code != 200: break
            data = r.json()
            if not data: break
            all_products.extend(data)
            print(f"Pobrano stronę {page} ({len(data)} aut)...")
            page += 1
        except Exception as e:
            print(f"Błąd API: {e}")
            break

    total = len(all_products[:100])
    print(f"Łącznie znaleziono {len(all_products)} ofert, procesuję {total} ofert Opla. Pobieranie szczegółów (wielowątkowo)...")

    osobowe_rows = []
    dostawcze_rows = []

    MAX_WORKERS = 6
    
    with ThreadPoolExecutor(max_workers=MAX_WORKERS) as executor:
        futures = {executor.submit(process_product, p, i+1, total): p for i, p in enumerate(all_products[:100])}
        
        for future in as_completed(futures):
            try:
                result = future.result()
                if result:
                    if result["is_commercial"]:
                        dostawcze_rows.append(result["row"])
                    else:
                        osobowe_rows.append(result["row"])
            except Exception as e:
                print(f"Błąd wątku: {e}")

    fieldnames = [
        "vehicle_id", "title", "description", "link", "image_link",
        "make", "model", "year", "mileage.value", "mileage.unit",
        "body_style", "exterior_color", "state_of_vehicle",
        "price", "currency", "address", "latitude", "longitude",
        "offer_type", "amount_price", "amount_qualifier", "fuel_type", "transmission", "drivetrain"
    ]

    print(f"\nZapisywanie: Osobowe ({len(osobowe_rows)}), Dostawcze ({len(dostawcze_rows)})")
    
    scraper_utils.safe_save_csv(osobowe_rows, fieldnames, OUTPUT_FILE_OSO)
    scraper_utils.safe_save_csv(dostawcze_rows, fieldnames, OUTPUT_FILE_DOS)
    
    print("Zakończono sukcesem.")

if __name__ == "__main__":
    main()

"""
Peugeot Inventory (Stock) Feed
- Data source: WordPress JSON API at sklep.peugeot.pl
- Installment prices: Selenium B2B scraping
- Output: single CSV with all stock vehicles (osobowe + dostawcze)
"""
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

API_URL = "https://sklep.peugeot.pl/wp-json/wp/v2/product"
BASE_URL = "https://sklep.peugeot.pl"
OUTPUT_DIR = os.path.join(os.path.dirname(os.path.dirname(__file__)), "data")
OUTPUT_FILE_OSO = os.path.join(OUTPUT_DIR, "peugeot_osobowe_inventory.csv")
OUTPUT_FILE_LCV = os.path.join(OUTPUT_DIR, "peugeot_lcv_inventory.csv")
IMAGES_DIR = os.path.join(OUTPUT_DIR, "images")
GITHUB_BASE_IMAGE_URL = "https://raw.githubusercontent.com/Andy11001/-alfa-inventory/master/data/images"

LCV_MODELS = ["Boxer", "Boxer Podwozie", "Expert", "Partner"]

# --- Model category slug -> display name ---
# Includes both readable slugs AND numeric WP term IDs found in class_list
MODEL_MAP = {
    # Readable slugs
    "208": "208",
    "2008": "2008",
    "308": "308",
    "308-sw": "308 SW",
    "408": "408",
    "3008": "3008",
    "5008": "5008",
    "nowe-308": "Nowe 308",
    "nowe-308-sw": "Nowe 308 SW",
    "nowy-3008": "Nowy 3008",
    "nowy-408": "Nowy 408",
    "nowy-5008": "Nowy 5008",
    "rifter": "Rifter",
    "rifter-mpv": "Rifter MPV",
    "traveller": "Traveller",
    "partner": "Partner",
    "expert": "Expert",
    "boxer": "Boxer",
    "boxer-podwozie-do-zabudowy": "Boxer Podwozie",
    "boxer-podwozie-do-zabudowy-2": "Boxer Podwozie",
    # Numeric WP term IDs (from product_cat taxonomy)
    "190": "208",
    "166": "2008",
    "172": "308",
    "175": "308 SW",
    "317": "408",
    "160": "3008",
    "197": "5008",
    "673": "Nowe 308",
    "674": "Nowe 308 SW",
    "480": "Nowy 3008",
    "704": "Nowy 408",
    "518": "Nowy 5008",
    "241": "Rifter",
    "697": "Rifter MPV",
    "255": "Traveller",
    "332": "Partner",
    "320": "Expert",
    "329": "Boxer",
    "706": "Boxer Podwozie",
    "456": "_MTO",  # Skip this
}

# --- Dealer locations ---
CITY_TO_REGION = {
    "Kraków": "Małopolskie",    "Warszawa": "Mazowieckie",
    "Wrocław": "Dolnośląskie",  "Poznań": "Wielkopolskie",
    "Gdańsk": "Pomorskie",      "Katowice": "Śląskie",
    "Łódź": "Łódzkie",          "Szczecin": "Zachodniopomorskie",
    "Opole": "Opolskie",        "Bielsko-Biała": "Śląskie",
    "Lublin": "Lubelskie",      "Bydgoszcz": "Kujawsko-Pomorskie",
    "Toruń": "Kujawsko-Pomorskie", "Rzeszów": "Podkarpackie",
    "Radom": "Mazowieckie",     "Kielce": "Świętokrzyskie",
    "Elbląg": "Warmińsko-Mazurskie", "Białystok": "Podlaskie",
    "Piła": "Wielkopolskie",    "Rybnik": "Śląskie",
    "Gliwice": "Śląskie",       "Sosnowiec": "Śląskie",
    "Legnica": "Dolnośląskie",  "Kalisz": "Wielkopolskie",
    "Leszno": "Wielkopolskie",  "Płock": "Mazowieckie",
    "Nowy Targ": "Małopolskie", "Ełk": "Warmińsko-Mazurskie",
}

DEALER_LOCATIONS = {
    "Kraków":       {"lat": "50.0931", "lon": "19.9238", "street": "ul. Opolska 9"},
    "Warszawa":     {"lat": "52.2084", "lon": "20.9412", "street": "Al. Krakowska 206"},
    "Wrocław":      {"lat": "51.1274", "lon": "16.9535", "street": "ul. Szczecińska 7"},
    "Poznań":       {"lat": "52.3787", "lon": "17.0270", "street": "ul. Bolesława Krzywoustego 71"},
    "Gdańsk":       {"lat": "54.4022", "lon": "18.5714", "street": "al. Grunwaldzka 256"},
    "Katowice":     {"lat": "50.2649", "lon": "19.0238", "street": "Al. Roździeńskiego 170"},
    "Łódź":         {"lat": "51.7371", "lon": "19.4316", "street": "ul. Obywatelska 181"},
    "Szczecin":     {"lat": "53.3891", "lon": "14.6543", "street": "ul. Struga 1b"},
    "Opole":        {"lat": "50.6751", "lon": "17.9213", "street": "ul. Wrocławska 137"},
    "Bielsko-Biała":{"lat": "49.8225", "lon": "19.0444", "street": "ul. Warszawska 15"},
    "Lublin":       {"lat": "51.2465", "lon": "22.5684", "street": "ul. Mełgiewska 10"},
    "Bydgoszcz":    {"lat": "53.1235", "lon": "18.0084", "street": "ul. Fordońska 353"},
    "Toruń":        {"lat": "53.0138", "lon": "18.5984", "street": "ul. Szosa Bydgoska 52"},
    "Rzeszów":      {"lat": "50.0412", "lon": "21.9991", "street": "ul. Krakowska 150"},
    "Radom":        {"lat": "51.4027", "lon": "21.1471", "street": "ul. Żółkiewskiego 4"},
    "Elbląg":       {"lat": "54.1522", "lon": "19.4040", "street": "ul. Kazimierzowo 4"},
    "Białystok":    {"lat": "53.1325", "lon": "23.1688", "street": "ul. Elewatorska 60"},
    "Piła":         {"lat": "53.1510", "lon": "16.7384", "street": "ul. Warsztatowa 6"},
    "Rybnik":       {"lat": "50.1022", "lon": "18.5463", "street": "ul. Żorska 14"},
    "Gliwice":      {"lat": "50.2945", "lon": "18.6714", "street": "ul. Toszecka 101"},
    "Sosnowiec":    {"lat": "50.2863", "lon": "19.1042", "street": "ul. Wojska Polskiego 45"},
    "Legnica":      {"lat": "51.2070", "lon": "16.1619", "street": "ul. Jaworzyńska 235"},
    "Kalisz":       {"lat": "51.7612", "lon": "18.0929", "street": "ul. Częstochowska 144"},
    "Leszno":       {"lat": "51.8432", "lon": "16.5751", "street": "ul. Okrzei 12"},
    "Płock":        {"lat": "52.5468", "lon": "19.7064", "street": "ul. Otolińska 25"},
    "Nowy Targ":    {"lat": "49.4793", "lon": "20.0327", "street": "ul. Ludźmierska 51"},
    "Ełk":          {"lat": "53.8281", "lon": "22.3647", "street": "ul. Suwalska 2"},
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


def download_image(url, filepath):
    """Download image if not already cached."""
    if os.path.exists(filepath):
        return True
    try:
        r = requests.get(url, stream=True, timeout=10,
                         headers={"User-Agent": "Mozilla/5.0"})
        if r.status_code == 200:
            with open(filepath, 'wb') as f:
                for chunk in r.iter_content(1024):
                    f.write(chunk)
            return True
    except Exception:
        pass
    return False





def process_product(product, index, total_count, driver):
    """Process a single product from WP API using a persistent driver and return a feed row."""
    try:
        from scrapers.selenium_helper import get_b2b_price_selenium
    except ImportError:
        from selenium_helper import get_b2b_price_selenium

    pid = str(product.get("id"))
    link = product.get("link")
    title_raw = product.get("title", {}).get("rendered", "")
    vin = title_raw if len(title_raw) == 17 else f"PEU-{pid}"

    classes = product.get("class_list", {})

    # --- Extract model from product_cat slug ---
    model_slug = ""
    model = "Peugeot"
    for cls in classes.values():
        if cls.startswith("product_cat-"):
            slug = cls.replace("product_cat-", "")
            if slug not in ["bez-kategorii", "_mto"]:
                model_slug = slug
                break

    if not model_slug:
        # Try from link: /produkt/308/VIN/ -> 308
        link_match = re.search(r'/produkt/([^/]+)/', link or "")
        if link_match:
            model_slug = link_match.group(1)

    if model_slug:
        model = MODEL_MAP.get(model_slug, model_slug.replace("-", " ").title())

    if model_slug in ["bez-kategorii", "_mto", ""] or model in ["Peugeot", "_MTO"]:
        return None  # Skip uncategorized

    # --- Extract attributes from CSS classes ---
    color = "Standard"
    fuel = "Gasoline"
    trans = "Manual"
    drive = "FWD"
    trim = ""
    year = "2025"
    body_style = "Hatchback"
    engine = ""

    for cls in classes.values():
        if cls.startswith("pa_kolor-"):
            color = cls.replace("pa_kolor-", "").replace("-", " ").title()
        elif cls.startswith("pa_typ-paliwa-"):
            f_val = cls.replace("pa_typ-paliwa-", "")
            if "hybryda-plug-in" in f_val:
                fuel = "Plug-in Hybrid"
            elif "hybryda" in f_val:
                fuel = "Hybrid"
            elif "elektryczn" in f_val:
                fuel = "Electric"
            elif "diesel" in f_val or "turbo-diesel" in f_val:
                fuel = "Diesel"
        elif cls.startswith("pa_typ-skrzyni-"):
            if "automat" in cls:
                trans = "Automatic"
        elif cls.startswith("pa_poziom-wyposazenia-"):
            trim = cls.replace("pa_poziom-wyposazenia-", "").replace("-", " ").title()
        elif cls.startswith("pa_rok-produkcji-"):
            yr = cls.replace("pa_rok-produkcji-", "")
            # Value can be 4-digit year OR a WP term ID
            if len(yr) == 4 and yr.isdigit():
                year = yr
            # Known WP term ID -> year mappings
            elif yr == "693":
                year = "2025"
            elif yr == "626":
                year = "2025"
            elif yr == "784":
                year = "2026"
        elif cls.startswith("pa_silnik-"):
            engine = cls.replace("pa_silnik-", "").replace("-", " ").title()
        elif cls.startswith("pa_typ-nadwozia-"):
            b = cls.replace("pa_typ-nadwozia-", "")
            if b in ["suv", "crossover"]:
                body_style = "SUV"
            elif b in ["sw", "kombi"]:
                body_style = "Wagon"
            elif b in ["van", "furgon", "xl", "l1", "l2", "l3", "l4"]:
                body_style = "Van"
            elif b in ["mpv"]:
                body_style = "Minivan"
            elif b in ["sedan"]:
                body_style = "Sedan"

    # --- Extract price from yoast description ---
    full_price = ""
    yoast_desc = product.get("yoast_head_json", {}).get("description", "")
    price_match = re.search(r'([\d\s]+)\s*zł', yoast_desc)
    if price_match:
        full_price = f"{re.sub(r'[^0-9]', '', price_match.group(1))} PLN"

    # --- Get B2B installment via Selenium ---
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
                    # Try exact match or case-insensitive match
                    for known_city in DEALER_LOCATIONS.keys():
                        if known_city.upper() == candidate.upper():
                            detected_city = known_city
                            break
                    else:
                        # Store raw if no exact match but valid text
                        if len(candidate) > 1:
                            detected_city = candidate
            else:
                # Fallback: try edealerName
                name_match = re.search(r'"edealerName"\s*:\s*"([^"]+)"', page_source)
                if name_match:
                    dealer_name = name_match.group(1).upper()
                    for city in DEALER_LOCATIONS.keys():
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
        full_price = "150000 PLN"

    amount_price_final = f"{clean_installment} PLN"

    # --- Image ---
    image = ""
    imgs = product.get("yoast_head_json", {}).get("og_image", [])
    if imgs:
        image = imgs[0].get("url", "")

    if image:
        ext = ".webp" if image.endswith(".webp") else ".jpg"
        image_filename = f"{vin}_clean{ext}"
        local_image_path = os.path.join(IMAGES_DIR, image_filename)
        if download_image(image, local_image_path):
            image = f"{GITHUB_BASE_IMAGE_URL}/{image_filename}"

    # --- Address ---
    dealer_data = DEALER_LOCATIONS.get(detected_city, DEALER_LOCATIONS["Warszawa"])
    address_text = format_address_json(dealer_data["street"], detected_city)
    lat = dealer_data.get("lat", "52.2297")
    lon = dealer_data.get("lon", "21.0122")

    # --- Build row ---
    tiktok_title = scraper_utils.format_inventory_title(model, trim, clean_installment)
    tiktok_desc = scraper_utils.format_inventory_description("Peugeot", model, trim, clean_installment, detected_city)

    row = {
        "vehicle_id": vin,
        "title": tiktok_title,
        "description": tiktok_desc,
        "link": link,
        "image_link": image,
        "make": "Peugeot",
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
        "drivetrain": drive
    }
    return row


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
            real_index = base_index + i + 1
            res = process_product(p, real_index, total_count, driver)
            if res:
                results.append(res)
            # Clear local storage/cookies to free RAM between iterations
            try:
                driver.delete_all_cookies()
            except:
                pass
    except Exception as e:
        print(f"Chunk {chunk_id} error: {e}")
    finally:
        if driver:
            try: driver.quit()
            except: pass
            
    return results

def main():
    print("=" * 60)
    print("Peugeot Inventory Feed — sklep.peugeot.pl")
    print("=" * 60)

    os.makedirs(IMAGES_DIR, exist_ok=True)

    # Step 1: Fetch all products from WP API
    print("\n[1/3] Pobieranie listy pojazdów z API sklepu Peugeot...")
    all_products = []
    page = 1
    session = requests.Session()
    session.headers.update({"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"})

    while True:
        try:
            url = f"{API_URL}?per_page=100&page={page}"
            r = session.get(url, timeout=15)

            if r.status_code == 400:
                print(f"  Koniec wyników (HTTP 400 na stronie {page}).")
                break

            r.raise_for_status()
            data = r.json()
            if not data:
                break
            all_products.extend(data)
            print(f"  Pobrano stronę {page} ({len(data)} aut, łącznie: {len(all_products)})...")
            page += 1
        except Exception as e:
            print(f"  Koniec wyników / Błąd przy stronie {page}: {e}")
            break

    total = len(all_products)
    print(f"\n  Łącznie znaleziono {total} produktów w API.")

    # Step 2: Process products (multithreaded chunks)
    print("\n[2/3] Przetwarzanie ofert (Selenium B2B)...\n")

    processed_rows = []
    MAX_WORKERS = 4
    
    # Split all_products into MAX_WORKERS chunks
    chunk_size = (total + MAX_WORKERS - 1) // MAX_WORKERS
    chunks = [all_products[i * chunk_size:(i + 1) * chunk_size] for i in range(MAX_WORKERS)]

    with ThreadPoolExecutor(max_workers=MAX_WORKERS) as executor:
        futures = []
        base_idx = 0
        for i, chunk in enumerate(chunks):
            futures.append(executor.submit(process_chunk, chunk, i+1, total, base_idx))
            base_idx += len(chunk)
            
        for future in as_completed(futures):
            try:
                res_list = future.result()
                if res_list:
                    processed_rows.extend(res_list)
            except Exception as e:
                print(f"  Błąd wątku: {e}")

    # Step 3: Save CSVs
    print(f"\n[3/3] Zapisywanie {len(processed_rows)} ofert...")

    fieldnames = [
        "vehicle_id", "title", "description", "link", "image_link",
        "make", "model", "year", "mileage.value", "mileage.unit",
        "body_style", "exterior_color", "state_of_vehicle",
        "price", "currency", "address", "latitude", "longitude",
        "offer_type", "amount_price", "amount_qualifier",
        "fuel_type", "transmission", "drivetrain"
    ]

    osobowe_rows = [r for r in processed_rows if r["model"] not in LCV_MODELS]
    lcv_rows = [r for r in processed_rows if r["model"] in LCV_MODELS]

    print(f"  Osobowe: {len(osobowe_rows)} pojazdów")
    print(f"  Dostawcze: {len(lcv_rows)} pojazdów")

    success_oso = scraper_utils.safe_save_csv(osobowe_rows, fieldnames, OUTPUT_FILE_OSO, min_rows_threshold=0)
    success_lcv = scraper_utils.safe_save_csv(lcv_rows, fieldnames, OUTPUT_FILE_LCV, min_rows_threshold=0)

    if success_oso:
        print(f"✅ Sukces! Zapisano {len(osobowe_rows)} osobówek -> {OUTPUT_FILE_OSO}")
    else:
        print(f"❌ BŁĄD przy zapisie osobówek -> {OUTPUT_FILE_OSO}")

    if success_lcv:
        print(f"✅ Sukces! Zapisano {len(lcv_rows)} dostawczych -> {OUTPUT_FILE_LCV}")
    else:
        print(f"❌ BŁĄD przy zapisie dostawczych -> {OUTPUT_FILE_LCV}")

    print("\nZakończono.")


if __name__ == "__main__":
    main()

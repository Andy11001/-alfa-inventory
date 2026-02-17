import requests
import csv
import json
import re
import time
import os
import scraper_utils # Import modułu bezpieczeństwa
from bs4 import BeautifulSoup
try:
    from scrapers.image_processor import process_image
except ModuleNotFoundError:
    from image_processor import process_image

API_URL = "https://sklep.dsautomobiles.pl/wp-json/wp/v2/product"
OUTPUT_FILE = os.path.join(os.path.dirname(os.path.dirname(__file__)), "data", "ds_inventory.csv")
IMAGES_DIR = os.path.join(os.path.dirname(os.path.dirname(__file__)), "data", "images")
GITHUB_BASE_IMAGE_URL = "https://raw.githubusercontent.com/Andy11001/-alfa-inventory/master/data/images"

# Mapa modeli (class_list -> ładna nazwa)
MODEL_MAP = {
    "ds-3": "DS 3",
    "ds-4": "DS 4",
    "n4": "N°4", 
    "ds-7": "DS 7",
    "ds-9": "DS 9",
    "n8": "N°8"
}

CITY_TO_REGION = {
    "Kraków": "Małopolskie",
    "Warszawa": "Mazowieckie",
    "Wrocław": "Dolnośląskie",
    "Poznań": "Wielkopolskie",
    "Gdańsk": "Pomorskie",
    "Katowice": "Śląskie",
    "Łódź": "Łódzkie",
    "Szczecin": "Zachodniopomorskie",
    "Opole": "Opolskie",
    "Bielsko-Biała": "Śląskie"
}

COLOR_CONFIG = {
    "White Pearl": (242, 242, 242),
    "Blanc Banquise": (242, 242, 242),
    "Perla Nera Black": (26, 26, 26),
    "Cristal Pearl": (209, 205, 197),
    "Crystal Pearl": (209, 205, 197),
    "Cashmere": (118, 121, 130),
    "Night Flight": (62, 65, 73),
    "Lazurite Blue": (0, 107, 125)
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

# Hardcoded Dealer Locations (Lat/Lon + Street Address)
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

def clean_html_text(text):
    if not text: return ""
    return re.sub(r'\s+', ' ', text).strip()

def parse_detail_page(url, session):
    """Pobiera stronę produktu i wyciąga cenę, dealera oraz rok produkcji."""
    price = ""
    address_text = ""
    dynamic_year = "2024" # Default updated
    lat, lon = "", ""
    
    try:
        # Użycie bezpiecznego pobeirania
        r = scraper_utils.fetch_with_retry(session, url, timeout=10)
        html_content = r.text
        soup = BeautifulSoup(r.content, 'html.parser')
        
        # --- 1. Cena (Full Price) ---
        price_tag = soup.find("p", class_="price")
        if price_tag:
            ins_tag = price_tag.find("ins")
            if ins_tag:
                raw_price = ins_tag.get_text(strip=True)
            else:
                raw_price = price_tag.get_text(strip=True)
            
            clean_digits = re.sub(r'[^\d]', '', raw_price)
            if clean_digits:
                price = f"{clean_digits} PLN"

        if not price:
            matches = re.findall(r'([\d\s\.]+)\s*z\ł', html_content)
            for m in matches:
                clean = re.sub(r'[^\d]', '', m)
                if len(clean) >= 5: 
                    price = f"{clean} PLN"
                    break
        
        # --- 2. Dealer / Lokalizacja / Rok ---
        text_content = soup.get_text(" ", strip=True)
        detected_city = "Warszawa" # Default fallback

        # Try to extract city from dataLayer (more reliable)
        city_match = re.search(r'"edealerCity"\s*:\s*"([^"]+)"', html_content)
        if city_match and city_match.group(1):
            detected_city = city_match.group(1)
        else:
            # Fallback to edealerName if city is empty
            name_match = re.search(r'"edealerName"\s*:\s*"([^"]+)"', html_content)
            if name_match:
                dealer_name = name_match.group(1).upper()
                for city in DEALER_LOCATIONS.keys():
                    if city.upper() in dealer_name:
                        detected_city = city
                        break
        
        # Set Address Data
        dealer_data = DEALER_LOCATIONS.get(detected_city, DEALER_LOCATIONS["Warszawa"])
        lat = dealer_data["lat"]
        lon = dealer_data["lon"]
        street = dealer_data.get("street", "Al. Krakowska 206")

        # Format adresu jako JSON (wymagane przez system)
        address_text = format_address_json(street, detected_city)

        year_match = re.search(r'Rok produkcji\s*[:\-]?\s*(\d{4})', text_content, re.IGNORECASE)
        if year_match:
            dynamic_year = year_match.group(1)

        return price, address_text, dynamic_year, lat, lon
        
    except Exception as e:
        print(f"Błąd parsowania {url}: {e}")
        fallback_addr = format_address_json("Al. Krakowska 206", "Warszawa")
        return "", fallback_addr, "2024", "", ""

def cleanup_images(current_vins):
    """Usuwa zdjęcia, których nie ma już w aktualnej liście ofert."""
    if not os.path.exists(IMAGES_DIR):
        return
        
    print("Czyszczenie folderu ze zdjęciami...")
    all_files = os.listdir(IMAGES_DIR)
    removed_count = 0
    
    for filename in all_files:
        if filename.endswith(".jpg"):
            vin = filename.replace(".jpg", "")
            if vin not in current_vins:
                try:
                    os.remove(os.path.join(IMAGES_DIR, filename))
                    removed_count += 1
                except Exception as e:
                    print(f"Błąd podczas usuwania {filename}: {e}")
    
    if removed_count > 0:
        print(f"Usunięto {removed_count} nieaktualnych zdjęć.")

def main():
    print("Pobieranie listy pojazdów z API sklepu DS...")
    all_products = []
    page = 1
    session = requests.Session()
    session.headers.update({"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36"})

    while True:
        try:
            # Użycie fetch_with_retry do bezpiecznego pobierania stron
            r = scraper_utils.fetch_with_retry(session, f"{API_URL}?per_page=100&page={page}", timeout=10)
            if r.status_code != 200:
                break
            data = r.json()
            if not data:
                break
            all_products.extend(data)
            print(f"Pobrano stronę {page} ({len(data)} aut)...")
            page += 1
        except Exception as e:
            print(f"Błąd API przy stronie {page}: {e}")
            break

    print(f"Łącznie znaleziono {len(all_products)} ofert. Pobieranie szczegółów...")
    
    # Init Selenium Driver for B2B prices
    try:
        try:
            from scrapers.selenium_helper import init_driver, get_b2b_price_selenium
        except ImportError:
            from selenium_helper import init_driver, get_b2b_price_selenium
        driver = init_driver()
        print("Selenium driver initialized.")
    except Exception as e:
        print(f"Failed to init Selenium: {e}")
        driver = None

    fieldnames = [
        "vehicle_id", "title", "description", "link", "image_link",
        "make", "model", "year", "mileage.value", "mileage.unit",
        "body_style", "exterior_color", "state_of_vehicle",
        "price", "currency", "address", "latitude", "longitude",
        "offer_type", "amount_price", "amount_qualifier", "fuel_type", "transmission", "drivetrain"
    ]

    processed_rows = []

    for i, product in enumerate(all_products, 1):
        if i % 5 == 0:
            print(f"Przetwarzanie {i}/{len(all_products)}...", end='\r')

        pid = str(product.get("id"))

        link = product.get("link")
        title_raw = product.get("title", {}).get("rendered", "")
        vin = title_raw if len(title_raw) == 17 else f"DS-{pid}"
        
        # --- Basic Data from API ---
        classes = product.get("class_list", {})
        
        model = "DS Unknown"
        for cls in classes.values():
            if cls.startswith("product_cat-") and cls.replace("product_cat-", "") in MODEL_MAP:
                model = MODEL_MAP[cls.replace("product_cat-", "")]
        
        # Fallback model from link
        if model == "DS Unknown":
            if "ds-7" in link: model = "DS 7"
            elif "ds-3" in link: model = "DS 3"
            elif "ds-4" in link: model = "DS 4"
            elif "/n4/" in link: model = "N°4"
            elif "ds-9" in link: model = "DS 9"
            elif "/n8/" in link: model = "N°8"

        color = "Standard"
        fuel = "Gasoline"
        trans = "Automatic"
        drive = "FWD"
        trim = ""
        
        for cls in classes.values():
            if cls.startswith("pa_kolor-"):
                color = cls.replace("pa_kolor-", "").replace("-", " ").title()
            elif cls.startswith("pa_typ-paliwa-"):
                f_val = cls.replace("pa_typ-paliwa-", "")
                if "hybryda" in f_val: fuel = "Hybrid"
                elif "elektryczny" in f_val: fuel = "Electric"
                elif "diesel" in f_val: fuel = "Diesel"
            elif cls.startswith("pa_typ-skrzyni-"):
                if "manual" in cls: trans = "Manual"
            elif cls.startswith("pa_poziom-wyposazenia-"):
                trim = cls.replace("pa_poziom-wyposazenia-", "").replace("-", " ").title()

        # --- Detailed Parsing ---
        full_price, address_text, year, lat, lon = parse_detail_page(link, session)

        # --- Leasing / Monthly Price (B2B ONLY) ---
        desc_api = product.get("yoast_head_json", {}).get("description", "")
        installment = ""

        # B2B price via Selenium — NEVER use B2C
        if driver:
            try:
                b2b_price = get_b2b_price_selenium(link, driver=driver)
                if b2b_price:
                    installment = b2b_price
                    print(f"  [{i}] {vin}: B2B rata = {b2b_price} PLN")
                else:
                    print(f"  [{i}] {vin}: Brak raty B2B — pomijam")
            except Exception as e:
                print(f"  [{i}] {vin}: Błąd Selenium: {e}")
        else:
            print(f"  [{i}] {vin}: Brak drivera Selenium — pomijam")

        # Check for valid installment
        clean_installment = installment.replace("PLN", "").replace(" ", "").strip()
        
        # FILTR: Pomiń jeśli brak raty B2B
        if not clean_installment:
            continue
        try:
            if int(clean_installment) <= 0:
                continue
        except ValueError:
            continue

        # TikTok wymaga pola 'price'. Jeśli go nie znaleziono na stronie,
        # ale mamy ratę (co sprawdziliśmy wyżej), ustawiamy placeholder.
        if not full_price:
            full_price = "200000 PLN"

        amount_price_final = f"{clean_installment} PLN"

        image = ""
        if "og_image" in product.get("yoast_head_json", {}):
            imgs = product.get("yoast_head_json")["og_image"]
            if imgs:
                image = imgs[0].get("url")

        # --- Image Processing (Resize + Dynamic Color Border) ---
        if image:
            image_filename = f"{vin}.jpg"
            local_image_path = os.path.join(IMAGES_DIR, image_filename)
            
            # Pobierz kolor z konfiguracji lub użyj domyślnego beżu
            border_rgb = COLOR_CONFIG.get(color, (181, 162, 152))
            
            if process_image(image, local_image_path, border_color_rgb=border_rgb):
                # Zmieniamy link na bezpośredni link do GitHuba
                image = f"{GITHUB_BASE_IMAGE_URL}/{image_filename}"

        desc = f"{desc_api[:450]}"

        row = {
            "vehicle_id": vin,
            "title": f"{model} {trim}"[:40],
            "description": desc.strip(),
            "link": link,
            "image_link": image,
            "make": "DS Automobiles",
            "model": model,
            "year": year,
            "mileage.value": 0,
            "mileage.unit": "KM",
            "body_style": "SUV" if "7" in model or "3" in model else "Hatchback",
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
        processed_rows.append(row)

    print(f"\nGenerowanie feedu z {len(processed_rows)} ofertami...")
    
    if driver:
        driver.quit()
        print("Selenium driver closed.")

    # Czyszczenie starych zdjęć
    current_vins = [r['vehicle_id'] for r in processed_rows]
    cleanup_images(current_vins)
    
    # Bezpieczny zapis z scraper_utils
    from scraper_utils import safe_save_csv
    success = safe_save_csv(processed_rows, fieldnames, OUTPUT_FILE)
    
    if success:
        print(f"Sukces! Dane zapisane w: {OUTPUT_FILE}")
    else:
        print(f"BŁĄD KRYTYCZNY: Nie udało się zapisać {OUTPUT_FILE}")

if __name__ == "__main__": main()

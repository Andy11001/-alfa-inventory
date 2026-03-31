import sys
import os
import re
import time
from bs4 import BeautifulSoup
from concurrent.futures import ThreadPoolExecutor

try:
    from scrapers import scraper_utils
except ModuleNotFoundError:
    import scraper_utils

# Import drivera
try:
    from scrapers.selenium_helper import init_driver
except ModuleNotFoundError:
    from selenium_helper import init_driver

BASE_URL = "https://www.leapmotor.net/pl"
OUTPUT_DIR = os.path.join(os.path.dirname(os.path.dirname(__file__)), "data")
OUTPUT_FILE = os.path.join(OUTPUT_DIR, "leapmotor_model_feed.csv")

def extract_prices(html_content):
    soup = BeautifulSoup(html_content, 'html.parser')
    text = soup.get_text(" ", strip=True)
    
    offers = []
    
    # Przykładowe dopasowanie: "Leapmotor T03 EV JUŻ OD 69 900 ZŁ"
    # Szukamy modelu B10, T03, C10
    pattern = r'(?:Leapmotor\s+)?(B10|T03|C10)[^\d]*JUŻ OD\s*([\d\s]+)\s*ZŁ'
    matches = re.finditer(pattern, text, re.IGNORECASE)
    
    found_models = set()
    for m in matches:
        model_name = m.group(1).upper()
        if model_name in found_models:
            continue
            
        found_models.add(model_name)
        price_str = m.group(2)
        price_clean = int(re.sub(r'[^\d]', '', price_str))
        
        # Obrazek (szukamy na podstawie typowej domeny Leapmotor ze ścieżką dostarczoną przez Usera)
        # B10, T03, C10 zazwyczaj maja jakies zdjecie, sprobujmy znalezc wzorzec
        image_url = ""
        img_pattern = rf'https://lpwebsite-prod-s3cdn\.leapmotor-international\.com[A-Za-z0-9/.\-_]*?{model_name}[A-Za-z0-9/.\-_]*?\.png'
        img_match = re.search(img_pattern, html_content, re.IGNORECASE)
        
        if img_match:
             image_url = img_match.group(0)
        else:
             # Fallback do generycznego obrazka jesli nazwa modelu wprost nie pasuje do URL (np Photo21)
             fallback_pattern = r'https://lpwebsite-prod-s3cdn\.leapmotor-international\.com/public/[A-Za-z0-9/.\-_]*?Photo[0-9]*_.*?.png'
             fallback_match = re.search(fallback_pattern, html_content, re.IGNORECASE)
             if fallback_match:
                  image_url = fallback_match.group(0)

        # Tworzenie oferty (dla feedu modelowego)
        title = f"Leapmotor {model_name}"
        offer = {
            "vehicle_id": scraper_utils.generate_stable_id(title, prefix="LEAP"),
            "title": title,
            "price_brutto": price_clean,
            "installment_netto": "", # Brak rat
            "months": "",
            "down_payment_pct": "",
            "disclaimer": "Cena bazowa pojazdu wyciągnięta ze strony głównej (od).",
            "model_code": model_name
        }
        
        offers.append(offer)
        
    return offers

def main():
    print(f"🚀 Rozpoczynam pobieranie ofert modelowych Leapmotor z: {BASE_URL}")
    os.makedirs(OUTPUT_DIR, exist_ok=True)
    
    driver = None
    try:
        driver = init_driver()
        driver.get(BASE_URL)
        time.sleep(5)  # Czekamy na Vue/Nuxt
        
        html = driver.page_source
        offers = extract_prices(html)
        
        if not offers:
            print("❌ Nie znaleziono ofert na stronie głównej.")
            return
            
        print(f"✅ Znaleziono {len(offers)} ofert bazowych.")
        for off in offers:
            print(f"   - {off['title']} od {off['price_brutto']} PLN")
            
        fieldnames = ["vehicle_id", "title", "price_brutto", "installment_netto", "months", "down_payment_pct", "disclaimer", "model_code"]
        
        from scraper_utils import safe_save_csv
        if safe_save_csv(offers, fieldnames, OUTPUT_FILE, min_rows_threshold=1):
             print(f"\n💾 Zapisano {len(offers)} ofert do {OUTPUT_FILE}")
        else:
             print(f"\n⚠️ Nie udało się zapisać pliku {OUTPUT_FILE}")

    except Exception as e:
        print(f"❌ Wystąpił błąd: {e}")
    finally:
        if driver:
            try:
                driver.quit()
            except:
                pass

if __name__ == "__main__":
    main()

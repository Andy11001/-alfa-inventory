# -*- coding: utf-8 -*-
"""
Opel Inventory (Stock) Feed
- Lista produktów: WordPress JSON API (sklep.opel.pl)
- Raty B2B + miasto dealera: bezpośrednie API kalkulatora SFS (sfs_calculator),
  bez Selenium — patrz scrapers/sfs_calculator.py
- Wyjście: opel_osobowe_inventory.csv + opel_dostawcze_inventory.csv
"""
import re
import os
import sys
import signal
import threading

if sys.stdout.encoding and sys.stdout.encoding.lower() != "utf-8":
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

try:
    from scrapers import scraper_utils, sfs_calculator, wp_shop
except ModuleNotFoundError:
    import scraper_utils
    import sfs_calculator
    import wp_shop

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

FIELDNAMES = [
    "vehicle_id", "title", "description", "link", "image_link",
    "make", "model", "year", "mileage.value", "mileage.unit",
    "body_style", "exterior_color", "state_of_vehicle",
    "price", "currency", "address", "latitude", "longitude",
    "offer_type", "amount_price", "amount_qualifier", "fuel_type", "transmission", "drivetrain"
]


def get_model_slug(product):
    return wp_shop.get_model_slug(product)


def build_row(product, rate_info):
    """Buduje wiersz feedu z danych WP + wyniku kalkulatora SFS."""
    pid = str(product.get("id"))
    link = product.get("link")
    title_raw = product.get("title", {}).get("rendered", "")
    vin = title_raw if len(title_raw) == 17 else f"OPEL-{pid}"

    classes = product.get("class_list", {})
    class_values = classes.values() if isinstance(classes, dict) else classes

    model_slug = get_model_slug(product)
    if not model_slug:
        return None

    model = model_slug.replace("-", " ").title()
    is_commercial = any(d in model_slug for d in DOS_CATEGORIES)

    color = "Standard"
    fuel = "Gasoline"
    trans = "Manual"
    drive = "FWD"
    trim = ""
    year = "2024"

    for cls in class_values:
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
            yr = cls.replace("pa_rok-produkcji-", "")
            if len(yr) == 4 and yr.isdigit():
                year = yr

    if rate_info and rate_info.get("year"):
        year = rate_info["year"]

    # Rata z kalkulatora SFS — bez niej oferta nie wchodzi do feedu (jak dotychczas)
    if not rate_info or not rate_info.get("installment"):
        return None
    clean_installment = str(rate_info["installment"])

    # Cena: attachOffer (dokładna) -> opis yoast -> default
    full_price = ""
    gross = rate_info.get("gross_price")
    if isinstance(gross, (int, float)) and gross > 10000:
        full_price = f"{int(round(gross))} PLN"
    if not full_price:
        yoast_desc = product.get("yoast_head_json", {}).get("description", "")
        price_match = re.search(r'([\d\s]+)\s*zł', yoast_desc)
        if price_match:
            full_price = f"{re.sub(r'[^0-9]', '', price_match.group(1))} PLN"
    if not full_price:
        full_price = "150000 PLN"

    image = ""
    imgs = product.get("yoast_head_json", {}).get("og_image", [])
    if imgs:
        image = imgs[0].get("url")
    if image:
        image_filename = f"{vin}_clean.jpg"
        local_image_path = os.path.join(IMAGES_DIR, image_filename)
        if wp_shop.download_image(image, local_image_path):
            image = f"{GITHUB_BASE_IMAGE_URL}/{image_filename}"

    # allow_unknown=False: Opel publikuje tylko znane salony (jak dotychczas)
    detected_city, street, lat, lon = wp_shop.resolve_dealer(
        rate_info.get("dealer_city"), rate_info.get("dealer_name"),
        DEALER_LOCATIONS, allow_unknown=False)
    address_text = wp_shop.format_address_json(street, detected_city, CITY_TO_REGION)

    tiktok_title = scraper_utils.format_inventory_title(model, trim, clean_installment)
    tiktok_desc = scraper_utils.format_inventory_description(
        "Opel", model, trim, clean_installment, detected_city)

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
        "latitude": lat,
        "longitude": lon,
        "offer_type": "LEASE",
        "amount_price": f"{clean_installment} PLN",
        "amount_qualifier": "per month",
        "fuel_type": fuel,
        "transmission": trans,
        "drivetrain": drive
    }
    return {"row": row, "is_commercial": is_commercial}


def main():
    print("Pobieranie listy pojazdów z API sklepu Opel...")
    os.makedirs(IMAGES_DIR, exist_ok=True)

    all_products = wp_shop.fetch_wp_products(API_URL)
    # Filtr przed pobieraniem stron: produkty bez kategorii to skasowane auta
    # (ich strony zwracają 500) — nie ma sensu ich odpytywać.
    all_products = [p for p in all_products if get_model_slug(p) and p.get("link")]
    limit = int(os.environ.get("SFS_LIMIT", "0"))
    if limit:
        all_products = all_products[:limit]
    total = len(all_products)
    print(f"Po odfiltrowaniu duchów: {total} ofert. Pobieranie rat przez API SFS...")

    # Współdzielone akumulatory: handler SIGTERM zrzuca częściowy wynik,
    # żeby timeout/cancel na CI nie wyrzucał całej pracy.
    osobowe_rows = []
    dostawcze_rows = []
    rows_lock = threading.RLock()

    def save_all(reason, no_shrink, min_rows):
        with rows_lock:
            oso = list(osobowe_rows)
            dos = list(dostawcze_rows)
        print(f"\nZapisywanie ({reason}): Osobowe ({len(oso)}), Dostawcze ({len(dos)})")
        scraper_utils.safe_save_csv(oso, FIELDNAMES, OUTPUT_FILE_OSO, min_rows_threshold=min_rows, no_shrink=no_shrink)
        scraper_utils.safe_save_csv(dos, FIELDNAMES, OUTPUT_FILE_DOS, min_rows_threshold=min_rows, no_shrink=no_shrink)

    def handle_term(signum, frame):
        print(f"\n⚠️  Sygnał {signum} — zapis częściowych wyników i wyjście.")
        save_all(reason=f"partial/sig{signum}", no_shrink=True, min_rows=0)
        os._exit(0)

    signal.signal(signal.SIGTERM, handle_term)
    signal.signal(signal.SIGINT, handle_term)

    # Raty + miasta dealera jednym przebiegiem (HTTP, batchowane) — bez Selenium.
    links = [p.get("link") for p in all_products if p.get("link")]
    rates, stats = sfs_calculator.get_inventory_rates("opel", links)

    print(f"\nBudowanie feedu ({len(rates)} aut z ratą)...")
    for i, product in enumerate(all_products, 1):
        res = build_row(product, rates.get(product.get("link")))
        if res:
            with rows_lock:
                if res["is_commercial"]:
                    dostawcze_rows.append(res["row"])
                else:
                    osobowe_rows.append(res["row"])
        if i % 100 == 0:
            print(f"  Przetworzono {i}/{total}...")

    save_all(reason="complete", no_shrink=False, min_rows=5)
    print("Zakończono sukcesem.")


if __name__ == "__main__":
    main()

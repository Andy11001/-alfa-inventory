# -*- coding: utf-8 -*-
"""
DS Automobiles Inventory (Stock) Feed
- Lista produktów: WordPress JSON API (sklep.dsautomobiles.pl)
- Raty + miasto dealera + cena + rok: bezpośrednie API kalkulatora SFS
  (sfs_calculator), bez Selenium — patrz scrapers/sfs_calculator.py
- Wyjście: ds_inventory.csv (+ zdjęcia z ramką w kolorze nadwozia)

Uwaga: DS domyślnie wyświetla produkt "b2b" (Abonament SimplyDrive B2B),
nie l101 — skonfigurowane w sfs_calculator.BRAND_CONFIG (zweryfikowane
empirycznie Selenium vs API).
"""
import re
import os
import sys

if sys.stdout.encoding and sys.stdout.encoding.lower() != "utf-8":
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

try:
    from scrapers import scraper_utils, sfs_calculator, wp_shop
except ModuleNotFoundError:
    import scraper_utils
    import sfs_calculator
    import wp_shop

try:
    from scrapers.image_processor import process_image
except ModuleNotFoundError:
    from image_processor import process_image

API_URL = "https://sklep.dsautomobiles.pl/wp-json/wp/v2/product"
OUTPUT_FILE = os.path.join(os.path.dirname(os.path.dirname(__file__)), "data", "ds_inventory.csv")
IMAGES_DIR = os.path.join(os.path.dirname(os.path.dirname(__file__)), "data", "images")
GITHUB_BASE_IMAGE_URL = "https://raw.githubusercontent.com/Andy11001/-alfa-inventory/master/data/images"

MODEL_MAP = {
    "ds-3": "DS 3",
    "ds-4": "DS 4",
    "n4": "N°4",
    "ds-7": "DS 7",
    "ds-9": "DS 9",
    "n7": "N°7",
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


def cleanup_images(current_vins):
    """Usuwa zdjęcia aut, których nie ma już w aktualnej liście ofert."""
    if not os.path.exists(IMAGES_DIR):
        return
    print("Czyszczenie folderu ze zdjęciami...")
    removed_count = 0
    for filename in os.listdir(IMAGES_DIR):
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


def get_model_slug(product):
    classes = product.get("class_list", {})
    class_values = classes.values() if isinstance(classes, dict) else classes
    for cls in class_values:
        if cls.startswith("product_cat-"):
            slug = cls.replace("product_cat-", "")
            if slug in MODEL_MAP:
                return slug
    # Fallback ze ścieżki URL
    link = product.get("link") or ""
    for slug in MODEL_MAP:
        if f"/{slug}/" in link:
            return slug
    return None


def build_row(product, rate_info):
    pid = str(product.get("id"))
    link = product.get("link")
    title_raw = product.get("title", {}).get("rendered", "")
    vin = title_raw if len(title_raw) == 17 else f"DS-{pid}"

    model_slug = get_model_slug(product)
    model = MODEL_MAP.get(model_slug, "DS Unknown")
    if model == "DS Unknown":
        return None

    classes = product.get("class_list", {})
    class_values = classes.values() if isinstance(classes, dict) else classes

    color = "Standard"
    fuel = "Gasoline"
    trans = "Automatic"
    drive = "FWD"
    trim = ""

    for cls in class_values:
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

    if not rate_info or not rate_info.get("installment"):
        return None
    clean_installment = str(rate_info["installment"])

    year = rate_info.get("year") or "2024"

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
        full_price = "200000 PLN"

    image = ""
    imgs = product.get("yoast_head_json", {}).get("og_image", [])
    if imgs:
        image = imgs[0].get("url")

    if image:
        image_filename = f"{vin}.jpg"
        local_image_path = os.path.join(IMAGES_DIR, image_filename)
        original_image_url = image
        border_rgb = COLOR_CONFIG.get(color, (181, 162, 152))
        try:
            if process_image(original_image_url, local_image_path, border_color_rgb=border_rgb):
                image = f"{GITHUB_BASE_IMAGE_URL}/{image_filename}"
            clean_filename = f"{vin}_clean.jpg"
            clean_path = os.path.join(IMAGES_DIR, clean_filename)
            process_image(original_image_url, clean_path, add_border=False)
        except Exception as e:
            print(f"Błąd renderingu zdjęcia {vin}: {e}")

    detected_city, street, lat, lon = wp_shop.resolve_dealer(
        rate_info.get("dealer_city"), rate_info.get("dealer_name"),
        DEALER_LOCATIONS, allow_unknown=True)
    address_text = wp_shop.format_address_json(street, detected_city, CITY_TO_REGION)

    tiktok_title = scraper_utils.format_inventory_title(model, trim, clean_installment)
    tiktok_desc = scraper_utils.format_inventory_description("DS Automobiles", model, trim, clean_installment)

    return {
        "vehicle_id": vin,
        "title": tiktok_title,
        "description": tiktok_desc,
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
        "amount_price": f"{clean_installment} PLN",
        "amount_qualifier": "per month",
        "fuel_type": fuel,
        "transmission": trans,
        "drivetrain": drive
    }


def main():
    print("Pobieranie listy pojazdów z API sklepu DS...")
    os.makedirs(IMAGES_DIR, exist_ok=True)

    all_products = wp_shop.fetch_wp_products(API_URL)
    all_products = [p for p in all_products if get_model_slug(p) and p.get("link")]
    limit = int(os.environ.get("SFS_LIMIT", "0"))
    if limit:
        all_products = all_products[:limit]
    total = len(all_products)
    print(f"Po odfiltrowaniu duchów: {total} ofert. Pobieranie rat przez API SFS...")

    links = [p["link"] for p in all_products]
    rates, stats = sfs_calculator.get_inventory_rates("ds", links)

    processed_rows = []
    for product in all_products:
        row = build_row(product, rates.get(product["link"]))
        if row:
            processed_rows.append(row)

    print(f"\nGenerowanie feedu z {len(processed_rows)} ofertami...")

    current_vins = [r['vehicle_id'] for r in processed_rows]
    cleanup_images(current_vins)

    success = scraper_utils.safe_save_csv(processed_rows, FIELDNAMES, OUTPUT_FILE)
    if success:
        print(f"Sukces! Dane zapisane w: {OUTPUT_FILE}")
    else:
        print(f"BŁĄD KRYTYCZNY: Nie udało się zapisać {OUTPUT_FILE}")


if __name__ == "__main__":
    main()

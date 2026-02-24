"""
Opel Model Feed — Hybrid Approach
- Trims, colors, engines, images: Stellantis configv3 API
- Promotional "od" prices: Selenium scraping from opel.pl
"""
import requests
from bs4 import BeautifulSoup
import re
import csv
import os
import time
import json

try:
    from scrapers import scraper_utils
    from scrapers.selenium_helper import init_driver
except ModuleNotFoundError:
    import scraper_utils
    from selenium_helper import init_driver

# --- Config ---
API_BASE_BTOC = "https://api-cdn.configv3.awsmpsa.com/api/v4/o-pl-pl-btoc/vehicles"
API_BASE_BTOB = "https://api-cdn.configv3.awsmpsa.com/api/v4/o-pl-pl-btob/vehicles"
BASE_URL = "https://www.opel.pl"

OUTPUT_DIR = os.path.join(os.path.dirname(os.path.dirname(__file__)), "data")
OUTPUT_FILE_OSO = os.path.join(OUTPUT_DIR, "opel_osobowe_model.csv")
OUTPUT_FILE_DOS = os.path.join(OUTPUT_DIR, "opel_dostawcze_model.csv")

# Only exceptions where URL slug differs from label.lower().replace(' ', '-')
URL_SLUG_OVERRIDES = {
    "Combo": "combo-life",
    "Zafira": "zafira-electric",
}

# Models present in API but NOT on opel.pl as standalone products — skip them
SKIP_MODELS = {"Vivaro Kombi Electric"}



def get_model_url(label):
    """Auto-generate opel.pl URL from model label, with override for exceptions."""
    slug = URL_SLUG_OVERRIDES.get(label, label.lower().replace(' ', '-'))
    return f"{BASE_URL}/samochody/{slug}.html"

# Energy ID -> readable fuel type
ENERGY_MAP = {
    "01": "Hybrid",
    "02": "Gasoline",
    "04": "Diesel",
    "05": "Electric",
    "10": "Plug-in Hybrid",
}


# ─────────────────────────────────────────────
# 1. API: Get structured model data
# ─────────────────────────────────────────────
def fetch_api_versions(api_base, derived_model_id):
    """Fetch all versions for a derivedModel from the configv3 API."""
    url = f"{api_base}/versions?derivedModel={derived_model_id}"
    try:
        r = requests.get(url, timeout=30)
        r.raise_for_status()
        return r.json()
    except Exception as e:
        print(f"  ⚠ API error for {derived_model_id}: {e}")
        return []


def fetch_all_derived_models(api_base):
    """Fetch list of all derivedModels from configv3 API."""
    url = f"{api_base}/derivedModels"
    try:
        r = requests.get(url, timeout=30)
        r.raise_for_status()
        return r.json()
    except Exception as e:
        print(f"  ⚠ API derivedModels error: {e}")
        return []


def extract_model_data_from_api(versions):
    """
    Extract structured trim/color/engine data from API versions list.
    Returns dict: { trim_name: { "engines": [...], "colors": [...] } }
    """
    trims = {}
    for v in versions:
        trim_label = v.get("grCommercialName", {}).get("label", "Standard")
        energy_id = v.get("energy", {}).get("id", "02")
        fuel_type = ENERGY_MAP.get(energy_id, "Gasoline")
        engine_label = v.get("grEngine", {}).get("label", "")

        # Override: API often labels Hybrid engines under energy "Benzyna" (02)
        # but the engine label clearly says "Hybrid"
        if "hybrid" in engine_label.lower() and fuel_type == "Gasoline":
            fuel_type = "Hybrid"
        transmission = v.get("grTransmissionType", {}).get("label", "")
        api_price = float(v.get("prices", {}).get("price", {}).get("base", "0"))

        # Body style (for Astra hatchback vs Sports Tourer distinction)
        body_style = v.get("bodyStyle", {}).get("label", "")

        # LCDV code for building full car render URLs
        lcdv = v.get("lcdv", "")

        # Extract colors for this version
        colors = []
        looks = v.get("globalFeatures", {}).get("looks", {}).get("categories", [])

        # Check if this model has rims data (needed for correct 3D renders with wheels)
        has_rims = any(cat.get("id") == "rims" for cat in looks)

        for cat in looks:
            if cat.get("id") == "exteriors":
                for feat in cat.get("features", []):
                    color_name = feat.get("label", "")
                    color_id = feat.get("id", "")
                    swatch_url = feat.get("visuals", {}).get("default", "")

                    if color_name and lcdv and color_id:
                        if has_rims:
                            # Full car 3D render (wheels render correctly)
                            img_url = (
                                f"https://visual3d-secure.opel-vauxhall.com/V3DImage.ashx"
                                f"?client=CFGAP3D&mkt=PL&env=PROD&version={lcdv}"
                                f"&ratio=1&format=jpg&quality=90&width=1280"
                                f"&view=001&color={color_id}&back=0"
                            )
                        else:
                            # Fallback: swatch image (model has no rims → 3D render has no wheels)
                            img_url = swatch_url if swatch_url else ""

                        if img_url:
                            colors.append({"name": color_name, "image": img_url})

        if trim_label not in trims:
            trims[trim_label] = {"engines": [], "colors": []}

        # Add engine variant if not already present
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

        # Merge colors (avoid duplicates by name)
        existing_colors = {c["name"] for c in trims[trim_label]["colors"]}
        for c in colors:
            if c["name"] not in existing_colors:
                trims[trim_label]["colors"].append(c)
                existing_colors.add(c["name"])

    return trims


# ─────────────────────────────────────────────
# 2. Selenium: Scrape promotional prices
# ─────────────────────────────────────────────
def scrape_promo_prices(driver, url):
    """
    Scrape promotional 'od' prices from an opel.pl model page.
    Returns dict: { (trim_lower, fuel_hint): price_int }
    Returns None if page does not exist (404, error page).
    """
    prices = {}
    try:
        driver.get(url)
        time.sleep(3)

        for i in range(1, 6):
            driver.execute_script(f"window.scrollTo(0, document.body.scrollHeight * {i/5});")
            time.sleep(0.8)

        soup = BeautifulSoup(driver.page_source, 'html.parser')
        texts = soup.find_all(string=True)

        current_trim = "standard"
        model_name_raw = ""

        # Try to get model name from h1
        h1 = soup.find('h1')
        if h1:
            model_name_raw = h1.text.strip().replace("Nowy", "").replace("Nowa", "").replace("nowy", "").strip()
            model_name_raw = re.sub(r'[\r\n]+', ' ', model_name_raw).strip()

        model_clean = model_name_raw.replace("Opel ", "").upper().strip() if model_name_raw else ""

        for text_node in texts:
            t = text_node.strip().replace('\xa0', ' ')
            if not t:
                continue

            # Detect trim mentions
            if model_clean and model_clean.lower() in t.lower() and len(t) < 45 and t.lower() != model_clean.lower():
                t_clean = re.split(r'\s+już\s+od|\s+od', t, flags=re.IGNORECASE)[0].strip()
                potential_trim = t_clean
                if model_name_raw:
                    potential_trim = potential_trim.replace(model_name_raw, "").strip()
                if model_clean:
                    potential_trim = potential_trim.replace(model_clean.title(), "").replace("Opel", "").strip()

                # Skip junk
                junk_words = ["poznaj", "sprawdź", "oferty", "wszystkie", "modele", "dostosuj",
                              "wybierz", "swojego", "konfigur", "porównaj", "zobacz", "dowiedz",
                              "więcej", "zamów", "umów", "kontakt", "finansow", "leasing",
                              "rocznik", "samochod", "elektryczn", "hybryd", "benzynow", "doskonały"]
                if potential_trim and len(potential_trim) > 1:
                    is_junk = any(j in potential_trim.lower() for j in junk_words)
                    if not is_junk and "opel" not in potential_trim.lower():
                        current_trim = potential_trim.lower().strip()

            # Detect prices
            if 'od' in t.lower() and ('zł' in t.lower() or 'pln' in t.lower()):
                fuel_hint = "gasoline"
                t_lower = t.lower()
                if "hybryd" in t_lower or "hybrid" in t_lower:
                    fuel_hint = "hybrid"
                elif "elektrycz" in t_lower or "electric" in t_lower:
                    fuel_hint = "electric"
                elif "diesel" in t_lower:
                    fuel_hint = "diesel"
                elif "plug-in" in t_lower or "phev" in t_lower:
                    fuel_hint = "plugin_hybrid"

                price_match = re.search(r'([\d\s]+)\s*(zł|pln)', t, re.I)
                if price_match:
                    clean_price = re.sub(r'[^\d]', '', price_match.group(1))
                    if clean_price and len(clean_price) > 3:
                        key = (current_trim, fuel_hint)
                        price_val = int(clean_price)
                        # Keep the lowest price per trim+fuel combo
                        if key not in prices or price_val < prices[key]:
                            prices[key] = price_val

    except Exception as e:
        print(f"  ⚠ Selenium error on {url}: {e}")

    return prices


def match_promo_price(promo_prices, trim_label, fuel_type):
    """
    Try to match a promotional price for a given trim+fuel combo.
    Falls back gracefully to best available match.
    """
    trim_lower = trim_label.lower().strip()
    fuel_lower = fuel_type.lower().strip()

    # Direct match
    for (t, f), price in promo_prices.items():
        if trim_lower in t or t in trim_lower:
            if fuel_lower.startswith(f) or f.startswith(fuel_lower) or f == "gasoline":
                # Fuel match
                if fuel_lower == f or (fuel_lower == "gasoline" and f == "gasoline"):
                    return price

    # Fuzzy: match just trim
    trim_prices = {(t, f): p for (t, f), p in promo_prices.items() if trim_lower in t or t in trim_lower}
    if trim_prices:
        # Try to match fuel
        for (t, f), p in trim_prices.items():
            if f == fuel_lower:
                return p
        # Just return any price for this trim
        return min(trim_prices.values())

    # Fuzzy: match just fuel type across all trims
    fuel_prices = {(t, f): p for (t, f), p in promo_prices.items() if f == fuel_lower}
    if fuel_prices:
        return min(fuel_prices.values())

    # Ultimate fallback: cheapest price available for this model
    if promo_prices:
        return min(promo_prices.values())

    return None


# ─────────────────────────────────────────────
# 3. Generate feed rows
# ─────────────────────────────────────────────
def generate_feed_rows(model_label, trims_data, promo_prices, page_url, is_commercial):
    """Generate feed CSV rows from API data + promotional prices."""
    rows = []
    model_name = f"Opel {model_label}"

    for trim_label, trim_info in trims_data.items():
        colors = trim_info["colors"]
        if not colors:
            colors = [{"name": "Standard", "image": ""}]

        for engine in trim_info["engines"]:
            fuel = engine["fuel_type"]
            engine_desc = engine["engine"]
            transmission = engine["transmission"]

            # Get promotional price, fallback to API price
            promo_price = match_promo_price(promo_prices, trim_label, fuel)
            if promo_price:
                price_val = promo_price
            else:
                price_val = int(engine["api_price"]) if engine["api_price"] > 0 else None

            if not price_val:
                continue

            amount_price_str = f"{price_val} PLN"
            full_title = f"{model_name} {trim_label}" if trim_label != "Standard" else model_name

            tiktok_title = f"{full_title} · od {price_val} PLN"
            tiktok_desc = f"Nowy {full_title} · {engine_desc} · Dowiedz się więcej!"

            for color in colors:
                color_name = color["name"]
                img_url = color["image"]

                vid = (f"OPEL-{scraper_utils.generate_stable_id(model_label, length=4)}"
                       f"-{scraper_utils.generate_stable_id(trim_label, length=4)}"
                       f"-{scraper_utils.generate_stable_id(color_name, length=4)}"
                       f"-{scraper_utils.generate_stable_id(fuel + engine_desc, length=3)}")

                row = {
                    "vehicle_id": vid,
                    "title": tiktok_title,
                    "description": tiktok_desc,
                    "rodzaj": "modelowy",
                    "make": "Opel",
                    "model": model_name,
                    "year": "2025",
                    "link": page_url,
                    "image_link": img_url,
                    "exterior_color": color_name,
                    "additional_image_link": "",
                    "trim": trim_label,
                    "offer_disclaimer": "Oferta ma charakter informacyjny. Szczegóły u autoryzowanego dealera Opel.",
                    "offer_disclaimer_url": page_url,
                    "offer_type": "CASH",
                    "term_length": "",
                    "offer_term_qualifier": "",
                    "amount_price": amount_price_str,
                    "amount_percentage": "",
                    "amount_qualifier": "Total",
                    "downpayment": "",
                    "downpayment_qualifier": "",
                    "emission_disclaimer": "",
                    "emission_disclaimer_url": "",
                    "emission_overlay_disclaimer": "",
                    "emission_image_link": "",
                    "fuel_type": fuel,
                }
                rows.append(row)

    return rows


# ─────────────────────────────────────────────
# 4. Main
# ─────────────────────────────────────────────
def main():
    print("=" * 60)
    print("Opel Model Feed — Hybrid: API trims + Selenium prices")
    print("=" * 60)

    # Step 1: Fetch all derivedModels from API
    print("\n[1/4] Pobieranie listy modeli z API configv3...")
    btoc_models = fetch_all_derived_models(API_BASE_BTOC)
    btob_models = fetch_all_derived_models(API_BASE_BTOB)
    print(f"  Znaleziono: {len(btoc_models)} osobowych + {len(btob_models)} dostawczych")

    # Step 2: Initialize Selenium for price scraping
    print("\n[2/4] Inicjalizacja Selenium do scrapowania cen...")
    driver = init_driver()
    if not driver:
        print("❌ Błąd Selenium init_driver.")
        return

    all_osobowe = []
    all_dostawcze = []
    seen_ids = set()

    try:
        # Step 3: Process each model
        print("\n[3/4] Przetwarzanie modeli...\n")

        all_models = []
        for m in btoc_models:
            all_models.append(("btoc", m))
        for m in btob_models:
            all_models.append(("btob", m))

        for api_type, model_info in all_models:
            model_id = model_info["id"]
            model_label = model_info["label"]
            if model_label in SKIP_MODELS:
                print(f"  ⏭ Pomijam {model_label} — nie istnieje jako samodzielny model na opel.pl")
                continue

            is_commercial = (api_type == "btob")

            api_base = API_BASE_BTOC if api_type == "btoc" else API_BASE_BTOB

            print(f"  📦 {model_label} ({model_id}) [{'dostawczy' if is_commercial else 'osobowy'}]")

            # 3a. Get structured data from API
            versions = fetch_api_versions(api_base, model_id)
            if not versions:
                print(f"    ⚠ Brak wersji w API — pomijam.")
                continue

            trims_data = extract_model_data_from_api(versions)
            trim_count = len(trims_data)
            engine_count = sum(len(t["engines"]) for t in trims_data.values())
            color_count = sum(len(t["colors"]) for t in trims_data.values())
            print(f"    API: {trim_count} trimów, {engine_count} silników, {color_count} kolorów")

            # 3b. Get promotional prices from opel.pl
            page_url = get_model_url(model_label)
            promo_prices = {}
            print(f"    🌐 Scrapuję ceny z: {page_url}")
            promo_prices = scrape_promo_prices(driver, page_url)
            print(f"    Znaleziono {len(promo_prices)} cen promocyjnych")
            for (t, f), p in sorted(promo_prices.items()):
                print(f"      {t:20s} | {f:15s} | {p:>10,} zł")
            if not promo_prices:
                print(f"    ⚠ Brak cen promocyjnych — użyję cen z API")

            # 3c. Generate rows
            rows = generate_feed_rows(model_label, trims_data, promo_prices, page_url, is_commercial)

            # Deduplicate
            for r in rows:
                if r["vehicle_id"] not in seen_ids:
                    seen_ids.add(r["vehicle_id"])
                    if is_commercial:
                        all_dostawcze.append(r)
                    else:
                        all_osobowe.append(r)

            print(f"    ✅ Wygenerowano {len(rows)} wierszy\n")

    finally:
        driver.quit()

    # Step 4: Save feeds
    print("\n[4/4] Zapisywanie feedów modelowych...")
    fieldnames = [
        "vehicle_id", "title", "description", "rodzaj", "make", "model", "year", "link", "image_link",
        "exterior_color", "additional_image_link", "trim", "offer_disclaimer",
        "offer_disclaimer_url", "offer_type", "term_length", "offer_term_qualifier",
        "amount_price", "amount_percentage", "amount_qualifier", "downpayment",
        "downpayment_qualifier", "emission_disclaimer", "emission_disclaimer_url",
        "emission_overlay_disclaimer", "emission_image_link", "fuel_type"
    ]

    print(f"  Osobowe: {len(all_osobowe)}")
    print(f"  Dostawcze: {len(all_dostawcze)}")

    scraper_utils.safe_save_csv(all_osobowe, fieldnames, OUTPUT_FILE_OSO, min_rows_threshold=1)
    scraper_utils.safe_save_csv(all_dostawcze, fieldnames, OUTPUT_FILE_DOS, min_rows_threshold=1)
    print("Zakończono.")


if __name__ == "__main__":
    main()

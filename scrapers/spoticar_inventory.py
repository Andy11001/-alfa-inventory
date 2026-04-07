#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Spoticar Inventory Feed
- Data source: Internal API at spoticar.pl/api/vehicleoffers/list/search
- Access: curl_cffi (TLS fingerprint impersonation to bypass Akamai WAF)
- Output: single CSV with all used vehicles
"""
import re
import os
import sys
import time
import json

sys.stdout.reconfigure(encoding="utf-8")

from curl_cffi import requests as cffi_requests
from bs4 import BeautifulSoup

try:
    from scrapers import scraper_utils
except ModuleNotFoundError:
    import scraper_utils

# --- Config ---
API_URL = "https://www.spoticar.pl/api/vehicleoffers/list/search"
BASE_URL = "https://www.spoticar.pl"
OUTPUT_DIR = os.path.join(os.path.dirname(os.path.dirname(__file__)), "data")
OUTPUT_FILE = os.path.join(OUTPUT_DIR, "spoticar_inventory.csv")

CARS_PER_PAGE = 12  # API returns ~12 cards per page

# Fuel type normalization
FUEL_MAP = {
    "benzyna": "Gasoline",
    "diesel": "Diesel",
    "elektryczny": "Electric",
    "elektryczna": "Electric",
    "hybryda": "Hybrid",
    "hybryda plug-in": "Plug-in Hybrid",
    "hybrydowy plug-in": "Plug-in Hybrid",
    "hybrydowy": "Hybrid",
    "lpg": "LPG",
}

# Transmission normalization
TRANS_MAP = {
    "manualna": "Manual",
    "automatyczna": "Automatic",
    "automatyka": "Automatic",
}


def init_session():
    """Create a curl_cffi session impersonating Chrome to bypass Akamai WAF."""
    session = cffi_requests.Session(impersonate="chrome")
    # Seed cookies by visiting homepage
    try:
        session.get(f"{BASE_URL}/", timeout=15)
        time.sleep(0.5)
    except Exception as e:
        print(f"  ⚠ Could not seed session: {e}")
    return session


def fetch_page(session, page_num, retries=3):
    """Fetch a single page of vehicle offers from the API."""
    url = f"{API_URL}?page={page_num}"
    headers = {
        "X-Requested-With": "XMLHttpRequest",
        "Referer": f"{BASE_URL}/samochody-uzywane",
        "Accept": "application/json, text/javascript, */*; q=0.01",
    }
    for attempt in range(retries):
        try:
            r = session.get(url, headers=headers, timeout=20)
            if r.status_code == 200:
                return r.json()
            else:
                print(f"  ⚠ Page {page_num}: HTTP {r.status_code} (attempt {attempt+1}/{retries})")
        except Exception as e:
            print(f"  ⚠ Page {page_num}: error {e} (attempt {attempt+1}/{retries})")
        time.sleep(2 * (attempt + 1))
    return None


def parse_card(card):
    """Parse a single vehicle card HTML element into a data dict."""
    try:
        vo_id = card.get("data-vo-id", "")

        # --- Link ---
        link_tag = card.find("a", class_="vehicle-images-link") or card.find("a", href=True)
        href = link_tag.get("href", "") if link_tag else ""
        full_link = f"{BASE_URL}{href}" if href and not href.startswith("http") else href

        # --- Title / Brand / Model ---
        title_div = card.find("div", class_="vehicle-card-title")
        h3 = title_div.find("h3") if title_div else card.find("h3")
        brand_text = ""
        model_text = ""
        if h3:
            # H3 contains brand name, version in <span class="car-version">
            version_span = h3.find("span", class_="car-version")
            version_text = version_span.get_text(strip=True) if version_span else ""
            # Brand is the text before version span
            full_h3 = h3.get_text(strip=True)
            if version_text:
                brand_model = full_h3.replace(version_text, "").strip()
            else:
                brand_model = full_h3
            # Split brand and model (first word = brand usually)
            parts = brand_model.split(None, 1)
            if len(parts) >= 2:
                brand_text = parts[0]
                model_text = parts[1]
            elif parts:
                brand_text = parts[0]
                model_text = ""

        # --- Price ---
        price_text = ""
        cash_div = card.find("div", class_="cash")
        if cash_div:
            price_span = cash_div.find("span", class_="price-value")
            if price_span:
                raw = price_span.get_text(strip=True)
                # Extract digits: "49 900 PLN" -> "49900"
                digits = re.sub(r"[^\d]", "", raw)
                if digits:
                    price_text = f"{digits} PLN"

        # --- Monthly payment ---
        monthly_text = ""
        monthly_span = card.find("span", class_="monthly-payement-price")
        if monthly_span:
            raw = monthly_span.get_text(strip=True)
            digits = re.sub(r"[^\d]", "", raw)
            if digits:
                monthly_text = f"{digits} PLN"

        # --- Tags (km, fuel, date, transmission) ---
        tags_div = card.find("div", class_="vehicle-card-tags characteristics-tags")
        if not tags_div:
            tags_div = card.find("div", class_="vehicle-card-subtitle")
        tags = []
        if tags_div:
            tags = [span.get_text(strip=True) for span in tags_div.find_all("span", class_="tag")]

        mileage = ""
        fuel_type = "Gasoline"
        registration_date = ""
        transmission = "Manual"
        year = ""

        for tag in tags:
            tag_lower = tag.lower().strip()
            if "km" in tag_lower:
                digits = re.sub(r"[^\d]", "", tag)
                if digits:
                    mileage = digits
            elif tag_lower in FUEL_MAP:
                fuel_type = FUEL_MAP[tag_lower]
            elif tag_lower in TRANS_MAP:
                transmission = TRANS_MAP[tag_lower]
            elif re.match(r"\d{2}-\d{4}", tag):
                # e.g. "09-2024"
                registration_date = tag
                year = tag.split("-")[1] if "-" in tag else ""

        # --- Images ---
        imgs = card.find_all("img", class_="car-image")
        image_urls = []
        for img in imgs:
            src = img.get("data-src") or img.get("src") or ""
            if src and "amazonaws" in src:
                image_urls.append(src)

        image_link = image_urls[0] if image_urls else ""
        additional_images = "|".join(image_urls[1:4]) if len(image_urls) > 1 else ""

        # --- Dealer ---
        dealer_name = ""
        dealer_address = ""
        dealer_div = card.find("div", class_="vehicle-card-dealer")
        if dealer_div:
            name_span = dealer_div.find("span", class_="pdv-tooltip") or dealer_div.find("div", class_="dealer-name")
            if name_span:
                dealer_name = name_span.get_text(strip=True)
            addr_span = dealer_div.find("span", class_="address-name")
            if addr_span:
                dealer_address = addr_span.get_text(strip=True)

        # --- Warranty ---
        warranty = ""
        warranty_div = card.find("div", class_="vehicle-card-warranty")
        if warranty_div:
            warranty = warranty_div.get_text(strip=True)

        # --- Build title & description ---
        display_name = f"{brand_text} {model_text}".strip()
        if monthly_text:
            monthly_digits = re.sub(r"[^\d]", "", monthly_text)
            title_str = f"{display_name} · od {monthly_digits} PLN/mies."
            desc_str = f"{display_name} · Rata od {monthly_digits} PLN/mies. · {warranty} · {dealer_name} · Sprawdź ofertę!"
        elif price_text:
            price_digits = re.sub(r"[^\d]", "", price_text)
            title_str = f"{display_name} · {price_digits} PLN"
            desc_str = f"{display_name} · Cena: {price_digits} PLN · {warranty} · {dealer_name} · Sprawdź ofertę!"
        else:
            title_str = display_name
            desc_str = f"{display_name} · {warranty} · {dealer_name}"

        # Determine offer type
        if monthly_text:
            offer_type = "LEASE"
            amount_price = monthly_text
            amount_qualifier = "per month"
        else:
            offer_type = "CASH"
            amount_price = price_text
            amount_qualifier = "Total"

        return {
            "vehicle_id": f"SPOT-{vo_id}",
            "title": title_str,
            "description": desc_str,
            "link": full_link,
            "image_link": image_link,
            "additional_image_link": additional_images,
            "make": brand_text,
            "model": model_text,
            "year": year,
            "mileage.value": mileage,
            "mileage.unit": "KM",
            "exterior_color": "",
            "state_of_vehicle": "Used",
            "price": price_text,
            "currency": "PLN",
            "offer_type": offer_type,
            "amount_price": amount_price,
            "amount_qualifier": amount_qualifier,
            "fuel_type": fuel_type,
            "transmission": transmission,
            "dealer_name": dealer_name,
            "dealer_address": dealer_address,
            "warranty": warranty,
        }

    except Exception as e:
        print(f"  ⚠ Card parse error: {e}")
        return None


def get_total_count(data):
    """Extract total vehicle count from API response."""
    count_html = data.get("count", "")
    if count_html:
        match = re.search(r"\((\d+)", count_html)
        if match:
            return int(match.group(1))
    # Fallback: count brands doc_count
    brands = data.get("brands", [[]])
    if brands and isinstance(brands[0], list):
        return sum(b.get("doc_count", 0) for b in brands[0])
    return 0


def main():
    print("=" * 60)
    print("SpotiCar Inventory Feed — curl_cffi API Scraper")
    print("=" * 60)

    os.makedirs(OUTPUT_DIR, exist_ok=True)

    print("\n[1/3] Inicjalizacja sesji (TLS impersonation)...")
    session = init_session()

    print("[2/3] Pobieranie ofert z API...")
    # Fetch first page to get total count
    first_page = fetch_page(session, 1)
    if not first_page:
        print("  ❌ Nie udało się pobrać pierwszej strony API. Kończę.")
        return

    total = get_total_count(first_page)
    total_pages = (total // CARS_PER_PAGE) + (1 if total % CARS_PER_PAGE else 0)
    print(f"  Znaleziono: {total} ofert ({total_pages} stron)")

    all_rows = []

    # Parse page 1
    html1 = first_page.get("renderEntities", "")
    soup1 = BeautifulSoup(html1, "html.parser")
    cards1 = soup1.find_all("div", class_="vehicle-card")
    for card in cards1:
        row = parse_card(card)
        if row:
            all_rows.append(row)
    print(f"  Strona 1: {len(cards1)} kart -> {len(all_rows)} wierszy")

    # Fetch remaining pages
    for page_num in range(2, total_pages + 1):
        data = fetch_page(session, page_num)
        if not data:
            print(f"  ⚠ Strona {page_num}: brak danych — pomijam.")
            continue

        html = data.get("renderEntities", "")
        soup = BeautifulSoup(html, "html.parser")
        cards = soup.find_all("div", class_="vehicle-card")

        if not cards:
            print(f"  Strona {page_num}: 0 kart — koniec paginacji.")
            break

        page_count = 0
        for card in cards:
            row = parse_card(card)
            if row:
                all_rows.append(row)
                page_count += 1

        print(f"  Strona {page_num}/{total_pages}: {page_count} wierszy")
        time.sleep(0.5)  # Be polite

    print(f"\n[3/3] Zapisywanie feedu ({len(all_rows)} ofert)...")

    fieldnames = [
        "vehicle_id", "title", "description", "link", "image_link",
        "additional_image_link", "make", "model", "year",
        "mileage.value", "mileage.unit", "exterior_color",
        "state_of_vehicle", "price", "currency",
        "offer_type", "amount_price", "amount_qualifier",
        "fuel_type", "transmission", "dealer_name",
        "dealer_address", "warranty",
    ]

    scraper_utils.safe_save_csv(all_rows, fieldnames, OUTPUT_FILE, min_rows_threshold=10)
    print("Zakończono.")


if __name__ == "__main__":
    main()

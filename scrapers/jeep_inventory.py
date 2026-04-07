"""
Jeep Inventory (Stock) Feed
- Data source: salon.jeep.pl JSON API (identical to Alfa Romeo pattern)
- Output: single CSV with all stock vehicles
"""
import requests
import csv
import json
import re
import time
import os
import sys
from datetime import datetime

sys.stdout.reconfigure(encoding="utf-8")

try:
    from scrapers import scraper_utils
except ModuleNotFoundError:
    import scraper_utils

# --- Config ---
API_URL = "https://salon.jeep.pl/api/offers/list-jeep.json"
DETAIL_URL = "https://salon.jeep.pl/api/offers/offer-jeep.json?id={uid}"
BASE_URL = "https://salon.jeep.pl/oferta"
OUTPUT_DIR = os.path.join(os.path.dirname(os.path.dirname(__file__)), "data")
OUTPUT_FILE = os.path.join(OUTPUT_DIR, "jeep_inventory.csv")

BODY_STYLE_MAP = {
    "AVENGER": "SUV",
    "COMPASS": "SUV",
    "RENEGADE": "SUV",
    "WRANGLER": "SUV",
    "GLADIATOR": "Pickup",
    "GRAND CHEROKEE": "SUV",
    "CHEROKEE": "SUV",
}


def get_body_style(model_name):
    m = model_name.upper()
    for k, v in BODY_STYLE_MAP.items():
        if k in m:
            return v
    return "SUV"


def format_address_json(street, city, region, country, post_code=None):
    country_code = "PL" if country.lower() in ["polska", "pl"] else country
    addr = {
        "addr1": street.upper(),
        "city": city.upper(),
        "region": region.upper(),
        "country": country_code.upper(),
    }
    if post_code:
        addr["postal_code"] = post_code
    return json.dumps(addr, ensure_ascii=False)


def main():
    print("=" * 60)
    print("Jeep Inventory Feed — salon.jeep.pl API")
    print("=" * 60)

    os.makedirs(OUTPUT_DIR, exist_ok=True)

    print("\n[1/3] Pobieranie listy ofert z API...")
    all_offers = []
    try:
        r = scraper_utils.fetch_with_retry(
            requests, API_URL, headers={"User-Agent": "Mozilla/5.0"}
        )
        data = r.json()
        count = data["result"]["info"]["countOfResults"]
        per_page = data["result"]["info"]["offersPerPage"]
        total_pages = (count + per_page - 1) // per_page
        print(f"  Znaleziono: {count} ofert ({total_pages} stron)")

        for page in range(1, total_pages + 1):
            d = scraper_utils.fetch_with_retry(
                requests,
                f"{API_URL}?page={page}",
                headers={"User-Agent": "Mozilla/5.0"},
            ).json()
            all_offers.extend(d["result"]["list"])
            print(f"  Strona {page}/{total_pages}: +{len(d['result']['list'])} ofert")
    except Exception as e:
        print(f"  ❌ Błąd pobierania listy: {e}")
        return

    print(f"\n[2/3] Przetwarzanie {len(all_offers)} ofert...")

    fieldnames = [
        "vehicle_id", "title", "description", "link", "image_link",
        "make", "model", "year", "mileage.value", "mileage.unit",
        "body_style", "exterior_color", "state_of_vehicle",
        "price", "currency", "address", "latitude", "longitude",
        "offer_type", "amount_price", "amount_qualifier",
        "fuel_type", "transmission", "drivetrain",
    ]

    processed_rows = []
    session = requests.Session()
    session.headers.update({"User-Agent": "Mozilla/5.0"})

    for i, offer in enumerate(all_offers, 1):
        uid = str(offer.get("uid") or offer.get("id"))

        if i % 20 == 0:
            print(f"  Przetwarzanie {i}/{len(all_offers)}...")

        model = offer.get("model", "")
        version = offer.get("version", "")

        # --- Detail API (color + dealer location) ---
        street, city, region, post_code = "", "", "", ""
        lat, lon = "", ""
        color = "Standard"

        try:
            detail_url = DETAIL_URL.format(uid=uid)
            r_detail = session.get(detail_url, timeout=10)
            if r_detail.status_code == 200:
                d_json = r_detail.json()

                # Color
                if "color" in d_json and isinstance(d_json["color"], dict):
                    color = d_json["color"].get("name") or color

                # Dealer location
                dealer = d_json.get("dealer", {})
                if dealer:
                    street = dealer.get("street", "")
                    city = dealer.get("city", "")
                    region = dealer.get("region", "")
                    post_code = dealer.get("postCode", "")
                    coords = dealer.get("coordinates", {})
                    if coords:
                        lat = coords.get("latitude", "")
                        lon = coords.get("longitude", "")
        except Exception:
            pass

        # Fallback location from list
        if not city:
            loc_str = offer.get("localization", "")
            parts = loc_str.split(",")
            city = parts[1].strip() if len(parts) > 1 else parts[0].strip()
            street = city

        # Model + Version
        m_up, v_up = model.upper(), version.upper()
        full_model_name = model if v_up in m_up else f"{model} {version}"

        # Price
        price_data = offer.get("price", {})
        price_brutto = price_data.get("final", {}).get("brutto") or price_data.get(
            "base", {}
        ).get("brutto")
        if not price_brutto:
            continue

        # Financing
        fin_info = price_data.get("financing_info", {})
        installment = None
        for fin_key in ["b2b", "l101", "b2c"]:
            if fin_info.get(fin_key):
                installment = fin_info[fin_key].get("installment")
                if installment:
                    break

        # Engine / fuel / transmission
        eng = offer.get("engineType", "")
        if "Hybrid" in eng or "Hybryda" in eng:
            fuel = "Hybrid"
        elif "Elektryczn" in eng:
            fuel = "Electric"
        elif "Diesel" in eng:
            fuel = "Diesel"
        else:
            fuel = "Gasoline"

        trans = "Manual" if "Manual" in eng else "Automatic"
        drive = (
            "AWD"
            if any(
                x in version or x in model or x in eng
                for x in ["4xe", "4x4", "Trail", "Rubicon", "Trailhawk", "Sahara"]
            )
            else "FWD"
        )

        # Title & Description
        tiktok_title = scraper_utils.format_inventory_title(
            model, version, installment
        )
        tiktok_desc = scraper_utils.format_inventory_description(
            "Jeep", model, version, installment, city
        )

        row = {
            "vehicle_id": uid,
            "title": tiktok_title,
            "description": tiktok_desc,
            "link": f"{BASE_URL}/{uid}",
            "image_link": offer.get("image"),
            "make": "Jeep",
            "model": model,
            "year": offer.get("productionYear"),
            "mileage.value": offer.get("mileage") or 0,
            "mileage.unit": "KM",
            "body_style": get_body_style(model),
            "exterior_color": color,
            "state_of_vehicle": "New" if (offer.get("mileage") or 0) < 100 else "Used",
            "price": f"{price_brutto} PLN",
            "currency": "PLN",
            "address": format_address_json(street, city, region, "PL", post_code),
            "latitude": lat,
            "longitude": lon,
            "offer_type": "LEASE",
            "amount_price": f"{installment} PLN" if installment else "",
            "amount_qualifier": "per month" if installment else "",
            "fuel_type": fuel,
            "transmission": trans,
            "drivetrain": drive,
        }
        processed_rows.append(row)

    print(f"\n[3/3] Zapisywanie {len(processed_rows)} ofert...")
    unique_rows = list({r["vehicle_id"]: r for r in processed_rows}.values())

    scraper_utils.safe_save_csv(unique_rows, fieldnames, OUTPUT_FILE)
    print("Zakończono.")


if __name__ == "__main__":
    main()

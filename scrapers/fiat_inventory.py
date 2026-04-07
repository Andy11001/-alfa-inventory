"""
Fiat Inventory (Stock) Feed
- Data source: salon.fiat.pl + salon.fiatprofessional.pl JSON API
- Output: two CSVs — fiat_osobowe_inventory.csv + fiat_lcv_inventory.csv
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
API_PC = "https://salon.fiat.pl/api/offers/list-fiat.json"
API_LCV = "https://salon.fiatprofessional.pl/api/offers/list-fiat-professional.json"
DETAIL_PC = "https://salon.fiat.pl/api/offers/offer-fiat.json?id={uid}"
DETAIL_LCV = "https://salon.fiatprofessional.pl/api/offers/offer-fiat-professional.json?id={uid}"
BASE_URL_PC = "https://salon.fiat.pl/oferta"
BASE_URL_LCV = "https://salon.fiatprofessional.pl/oferta"

OUTPUT_DIR = os.path.join(os.path.dirname(os.path.dirname(__file__)), "data")
OUTPUT_FILE_PC = os.path.join(OUTPUT_DIR, "fiat_osobowe_inventory.csv")
OUTPUT_FILE_LCV = os.path.join(OUTPUT_DIR, "fiat_lcv_inventory.csv")

BODY_STYLE_MAP = {
    "500": "Hatchback", "500E": "Hatchback", "PANDA": "Hatchback",
    "GRANDE PANDA": "Hatchback", "TIPO": "Sedan", "TIPO SW": "Wagon",
    "TIPO CROSS": "SUV", "FASTBACK": "SUV",
    "DUCATO": "Van", "DOBLO": "Van", "SCUDO": "Van", "FIORINO": "Van",
    "ULYSSE": "Van", "E-DUCATO": "Van", "E-DOBLO": "Van", "E-SCUDO": "Van",
}


def get_body_style(model_name):
    m = model_name.upper()
    for k, v in BODY_STYLE_MAP.items():
        if k in m:
            return v
    return "Hatchback"


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


def fetch_all_offers(api_url):
    """Fetch all offers from paginated API."""
    all_offers = []
    r = scraper_utils.fetch_with_retry(
        requests, api_url, headers={"User-Agent": "Mozilla/5.0"}
    )
    data = r.json()
    count = data["result"]["info"]["countOfResults"]
    per_page = data["result"]["info"]["offersPerPage"]
    total_pages = (count + per_page - 1) // per_page
    print(f"  {count} ofert ({total_pages} stron)")

    for page in range(1, total_pages + 1):
        d = scraper_utils.fetch_with_retry(
            requests, f"{api_url}?page={page}", headers={"User-Agent": "Mozilla/5.0"}
        ).json()
        all_offers.extend(d["result"]["list"])
        print(f"  Strona {page}/{total_pages}: +{len(d['result']['list'])}")
    return all_offers


def process_offers(offers, detail_url_tpl, base_url, make_label="Fiat"):
    """Process list of offers into feed rows."""
    session = requests.Session()
    session.headers.update({"User-Agent": "Mozilla/5.0"})
    rows = []

    for i, offer in enumerate(offers, 1):
        uid = str(offer.get("uid") or offer.get("id"))
        if i % 20 == 0:
            print(f"  Przetwarzanie {i}/{len(offers)}...")

        model = offer.get("model", "")
        version = offer.get("version", "")

        # Detail API
        street, city, region, post_code = "", "", "", ""
        lat, lon = "", ""
        color = "Standard"

        try:
            r_detail = session.get(detail_url_tpl.format(uid=uid), timeout=10)
            if r_detail.status_code == 200:
                d_json = r_detail.json()
                if "color" in d_json and isinstance(d_json["color"], dict):
                    color = d_json["color"].get("name") or color
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

        if not city:
            loc_str = offer.get("localization", "")
            parts = loc_str.split(",")
            city = parts[1].strip() if len(parts) > 1 else parts[0].strip()
            street = city

        # Model + Version
        m_up, v_up = model.upper(), version.upper()
        full_model = model if v_up in m_up else f"{model} {version}"

        # Price
        price_data = offer.get("price", {})
        price_brutto = price_data.get("final", {}).get("brutto") or price_data.get("base", {}).get("brutto")
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

        # Fuel / transmission
        eng = offer.get("engineType", "")
        if "Hybrid" in eng or "Hybryda" in eng:
            fuel = "Hybrid"
        elif "Elektryczn" in eng:
            fuel = "Electric"
        elif "Diesel" in eng:
            fuel = "Diesel"
        elif "CNG" in eng:
            fuel = "CNG"
        else:
            fuel = "Gasoline"

        trans = "Manual" if "Manual" in eng else "Automatic"
        drive = "FWD"

        tiktok_title = scraper_utils.format_inventory_title(model, version, installment)
        tiktok_desc = scraper_utils.format_inventory_description(make_label, model, version, installment, city)

        row = {
            "vehicle_id": uid,
            "title": tiktok_title,
            "description": tiktok_desc,
            "link": f"{base_url}/{uid}",
            "image_link": offer.get("image"),
            "make": make_label,
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
        rows.append(row)

    return list({r["vehicle_id"]: r for r in rows}.values())


def main():
    print("=" * 60)
    print("Fiat Inventory Feed — salon.fiat.pl + fiatprofessional.pl")
    print("=" * 60)
    os.makedirs(OUTPUT_DIR, exist_ok=True)

    fieldnames = [
        "vehicle_id", "title", "description", "link", "image_link",
        "make", "model", "year", "mileage.value", "mileage.unit",
        "body_style", "exterior_color", "state_of_vehicle",
        "price", "currency", "address", "latitude", "longitude",
        "offer_type", "amount_price", "amount_qualifier",
        "fuel_type", "transmission", "drivetrain",
    ]

    # --- PC ---
    print("\n[1/4] Fiat Osobowe (PC)...")
    pc_offers = fetch_all_offers(API_PC)
    print(f"[2/4] Przetwarzanie {len(pc_offers)} osobowych...")
    pc_rows = process_offers(pc_offers, DETAIL_PC, BASE_URL_PC, "Fiat")

    # --- LCV ---
    print(f"\n[3/4] Fiat Professional (LCV)...")
    lcv_offers = fetch_all_offers(API_LCV)
    print(f"[4/4] Przetwarzanie {len(lcv_offers)} dostawczych...")
    lcv_rows = process_offers(lcv_offers, DETAIL_LCV, BASE_URL_LCV, "Fiat Professional")

    print(f"\nZapisywanie: PC={len(pc_rows)}, LCV={len(lcv_rows)}")
    scraper_utils.safe_save_csv(pc_rows, fieldnames, OUTPUT_FILE_PC)
    scraper_utils.safe_save_csv(lcv_rows, fieldnames, OUTPUT_FILE_LCV)
    print("Zakończono.")


if __name__ == "__main__":
    main()

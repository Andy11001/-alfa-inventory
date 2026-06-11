# -*- coding: utf-8 -*-
"""
Jeep Inventory (Stock) Feed
- Źródło: salon.jeep.pl JSON API (rata wprost w financing_info)
- Wspólna logika rodziny salon.*: scrapers/salon_api.py (null-safe)
"""
import os
import sys

if sys.stdout.encoding and sys.stdout.encoding.lower() != "utf-8":
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

try:
    from scrapers import scraper_utils, salon_api
except ModuleNotFoundError:
    import scraper_utils
    import salon_api

API_URL = "https://salon.jeep.pl/api/offers/list-jeep.json"
DETAIL_URL = "https://salon.jeep.pl/api/offers/offer-jeep.json?id={uid}"
BASE_URL = "https://salon.jeep.pl/oferta"
OUTPUT_FILE = os.path.join(os.path.dirname(os.path.dirname(__file__)), "data", "jeep_inventory.csv")

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


def get_drivetrain(model, version, eng):
    return "AWD" if any(
        x in version or x in model or x in eng
        for x in ["4xe", "4x4", "Trail", "Rubicon", "Trailhawk", "Sahara"]
    ) else "FWD"


def main():
    print("=" * 60)
    print("Jeep Inventory Feed — salon.jeep.pl API")
    print("=" * 60)

    print("\n[1/3] Pobieranie listy ofert z API...")
    try:
        all_offers = salon_api.fetch_all_offers(API_URL)
    except Exception as e:
        print(f"  ❌ Błąd pobierania listy: {e}")
        return

    limit = int(os.environ.get("SALON_LIMIT", "0"))
    if limit:
        all_offers = all_offers[:limit]

    print(f"\n[2/3] Przetwarzanie {len(all_offers)} ofert...")
    rows = salon_api.process_offers(
        all_offers, DETAIL_URL, BASE_URL, "Jeep",
        get_body_style, get_drivetrain)

    print(f"\n[3/3] Zapisywanie {len(rows)} ofert...")
    scraper_utils.safe_save_csv(rows, salon_api.FIELDNAMES, OUTPUT_FILE)
    print("Zakończono.")


if __name__ == "__main__":
    main()

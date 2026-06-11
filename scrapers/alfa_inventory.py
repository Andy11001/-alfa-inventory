# -*- coding: utf-8 -*-
"""
Alfa Romeo Inventory (Stock) Feed
- Źródło: salon.alfaromeo.pl JSON API (rata wprost w financing_info)
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

API_URL = "https://salon.alfaromeo.pl/api/offers/list-alfa-romeo.json"
DETAIL_URL = "https://salon.alfaromeo.pl/api/offers/offer-alfa-romeo.json?id={uid}"
BASE_URL = "https://salon.alfaromeo.pl/oferta"
OUTPUT_FILE = os.path.join(os.path.dirname(os.path.dirname(__file__)), "data", "alfa_romeo_inventory.csv")

BODY_STYLE_MAP = {
    "TONALE": "SUV", "STELVIO": "SUV", "GIULIA": "SEDAN",
    "JUNIOR": "SUV", "JUNIOR ELETTRICA": "SUV", "JUNIOR IBRIDA": "SUV"
}


def get_body_style(model_name):
    m = model_name.upper()
    for k, v in BODY_STYLE_MAP.items():
        if k in m:
            return v
    return "SUV"


def get_drivetrain(model, version, eng):
    return "AWD" if any(x in version or x in model or x in eng
                        for x in ["Q4", "Na cztery"]) else "FWD"


def main():
    print("=" * 60)
    print("Alfa Romeo Inventory Feed — salon.alfaromeo.pl API")
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
        all_offers, DETAIL_URL, BASE_URL, "Alfa Romeo",
        get_body_style, get_drivetrain)

    print(f"\n[3/3] Zapisywanie {len(rows)} unikalnych ofert...")
    success = scraper_utils.safe_save_csv(rows, salon_api.FIELDNAMES, OUTPUT_FILE)
    if success:
        print(f"Zakończono sukcesem. Plik: {OUTPUT_FILE}")
    else:
        print(f"BŁĄD: Nie udało się zapisać pliku {OUTPUT_FILE}")


if __name__ == "__main__":
    main()

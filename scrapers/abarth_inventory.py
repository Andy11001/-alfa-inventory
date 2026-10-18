# -*- coding: utf-8 -*-
"""
Abarth Inventory (Stock) Feed
- Źródło: salon.abarth.pl JSON API (rata wprost w financing_info)
- Wspólna logika rodziny salon.*: scrapers/salon_api.py (null-safe)

Abarth to marka niszowa — stock potrafi spaść do zera (tak było przy
uruchamianiu tego feedu). Pusta lista z API to poprawny stan, nie awaria:
zamiast alertu zostawiamy poprzedni CSV nietknięty, a gdy pliku jeszcze nie
ma — zapisujemy sam nagłówek, żeby feed w Giście był prawidłowy, tylko pusty.
Z tego samego powodu próg zapisu to 1 wiersz, a nie domyślne 5.
"""
import csv
import os
import sys

if sys.stdout.encoding and sys.stdout.encoding.lower() != "utf-8":
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

try:
    from scrapers import scraper_utils, salon_api
except ModuleNotFoundError:
    import scraper_utils
    import salon_api

API_URL = "https://salon.abarth.pl/api/offers/list-abarth.json"
DETAIL_URL = "https://salon.abarth.pl/api/offers/offer-abarth.json?id={uid}"
BASE_URL = "https://salon.abarth.pl/oferta"
OUTPUT_FILE = os.path.join(os.path.dirname(os.path.dirname(__file__)), "data", "abarth_inventory.csv")

# Kolejność ma znaczenie — "500E"/"600E" muszą trafić przed "500"/"600"
BODY_STYLE_MAP = {
    "600E": "SUV",
    "500E": "Hatchback",
    "595": "Hatchback",
    "695": "Hatchback",
    "124": "Convertible",
    "500": "Hatchback",
    "600": "SUV",
}


def get_body_style(model_name):
    m = model_name.upper()
    for k, v in BODY_STYLE_MAP.items():
        if k in m:
            return v
    return "Hatchback"


def get_drivetrain(model, version, eng):
    return "FWD"


def write_header_only(path):
    """Pusty, ale poprawny feed — tylko gdy pliku jeszcze nie ma."""
    if os.path.exists(path):
        return
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", newline="", encoding="utf-8-sig") as f:
        csv.DictWriter(f, fieldnames=salon_api.FIELDNAMES).writeheader()
    print(f"  Utworzono pusty feed z samym nagłówkiem: {path}")


def main():
    print("=" * 60)
    print("Abarth Inventory Feed — salon.abarth.pl API")
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

    if not all_offers:
        print("\n  ℹ️ API nie zwróciło żadnych ofert — Abarth ma pusty stock.")
        print("  Zostawiam poprzedni feed bez zmian (to nie jest awaria).")
        write_header_only(OUTPUT_FILE)
        return

    print(f"\n[2/3] Przetwarzanie {len(all_offers)} ofert...")
    rows = salon_api.process_offers(
        all_offers, DETAIL_URL, BASE_URL, "Abarth",
        get_body_style, get_drivetrain)

    if not rows:
        print("\n  ⚠️ API zwróciło oferty, ale żadnej nie dało się przetworzyć.")
        scraper_utils.send_email_alert(
            "Abarth: 0 wierszy z niepustego API",
            f"API zwróciło {len(all_offers)} ofert, feed wyszedł pusty — "
            "prawdopodobnie zmiana struktury salon.abarth.pl.")
        write_header_only(OUTPUT_FILE)
        return

    print(f"\n[3/3] Zapisywanie {len(rows)} unikalnych ofert...")
    success = scraper_utils.safe_save_csv(
        rows, salon_api.FIELDNAMES, OUTPUT_FILE, min_rows_threshold=1)
    if success:
        print(f"Zakończono sukcesem. Plik: {OUTPUT_FILE}")
    else:
        print(f"BŁĄD: Nie udało się zapisać pliku {OUTPUT_FILE}")


if __name__ == "__main__":
    main()

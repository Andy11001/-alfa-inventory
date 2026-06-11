# -*- coding: utf-8 -*-
"""
Fiat Inventory (Stock) Feed
- Źródła: salon.fiat.pl + salon.fiatprofessional.pl JSON API
- Wspólna logika rodziny salon.*: scrapers/salon_api.py (null-safe —
  patrz incydent z null w polach dealera, 2026-06-08/11)
- Wyjście: fiat_osobowe_inventory.csv + fiat_lcv_inventory.csv
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


def get_drivetrain(model, version, eng):
    return "FWD"


def main():
    print("=" * 60)
    print("Fiat Inventory Feed — salon.fiat.pl + fiatprofessional.pl")
    print("=" * 60)
    os.makedirs(OUTPUT_DIR, exist_ok=True)
    limit = int(os.environ.get("SALON_LIMIT", "0"))

    # --- PC ---
    print("\n[1/4] Fiat Osobowe (PC)...")
    pc_offers = salon_api.fetch_all_offers(API_PC)
    if limit:
        pc_offers = pc_offers[:limit]
    print(f"[2/4] Przetwarzanie {len(pc_offers)} osobowych...")
    pc_rows = salon_api.process_offers(
        pc_offers, DETAIL_PC, BASE_URL_PC, "Fiat",
        get_body_style, get_drivetrain)

    # --- LCV ---
    print("\n[3/4] Fiat Professional (LCV)...")
    lcv_offers = salon_api.fetch_all_offers(API_LCV)
    if limit:
        lcv_offers = lcv_offers[:limit]
    print(f"[4/4] Przetwarzanie {len(lcv_offers)} dostawczych...")
    lcv_rows = salon_api.process_offers(
        lcv_offers, DETAIL_LCV, BASE_URL_LCV, "Fiat Professional",
        get_body_style, get_drivetrain)

    print(f"\nZapisywanie: PC={len(pc_rows)}, LCV={len(lcv_rows)}")
    scraper_utils.safe_save_csv(pc_rows, salon_api.FIELDNAMES, OUTPUT_FILE_PC)
    scraper_utils.safe_save_csv(lcv_rows, salon_api.FIELDNAMES, OUTPUT_FILE_LCV)
    print("Zakończono.")


if __name__ == "__main__":
    main()

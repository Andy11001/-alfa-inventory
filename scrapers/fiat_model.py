# -*- coding: utf-8 -*-
"""
Fiat Model Feed
- Źródło: cennik SCCF konfiguratora fiat.pl (marka 00)
- Wspólna logika rodziny ex-FCA: scrapers/fca_sccf.py
"""
import os
import sys

if sys.stdout.encoding and sys.stdout.encoding.lower() != "utf-8":
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

try:
    from scrapers import scraper_utils, fca_sccf
except ModuleNotFoundError:
    import scraper_utils
    import fca_sccf

OUTPUT_FILE = os.path.join(os.path.dirname(os.path.dirname(__file__)),
                           "data", "fiat_osobowe_model.csv")

BRAND = {
    "host": "www.fiat.pl",
    "slug": "fiat",
    "brand_code": "00",
    "make_label": "Fiat",
    "id_prefix": "FIA",
    # tylko strony główne modeli — bez /dane-techniczne, /funkcje, /galeria
    "page_pattern": r"/modele/[a-z0-9-]+/?$",
    "fallback_link": "https://www.fiat.pl/modele",
    "disclaimer": "Oferta ma charakter informacyjny. Szczegóły u autoryzowanego dealera Fiat.",
}


def main():
    print("=" * 60)
    print("Fiat Model Feed — cennik SCCF (fiat.pl)")
    print("=" * 60)

    rows = fca_sccf.scrape_brand(BRAND)

    print(f"\nZapisywanie {len(rows)} wierszy...")
    scraper_utils.safe_save_csv(rows, fca_sccf.FIELDNAMES, OUTPUT_FILE,
                                min_rows_threshold=5)
    print("Zakończono.")


if __name__ == "__main__":
    main()

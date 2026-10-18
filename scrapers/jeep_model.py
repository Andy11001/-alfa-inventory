# -*- coding: utf-8 -*-
"""
Jeep Model Feed
- Źródło: cennik SCCF konfiguratora jeep.pl (marka 57)
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
                           "data", "jeep_model.csv")

BRAND = {
    "host": "www.jeep.pl",
    "slug": "jeep",
    "brand_code": "57",
    "make_label": "Jeep",
    "id_prefix": "JEEP",
    # Jeep zagnieżdża warianty: /modele/avenger/elektryczny — stąd dwa poziomy
    "page_pattern": r"/modele/[a-z0-9-]+(?:/[a-z0-9-]+)?/?$",
    "fallback_link": "https://www.jeep.pl/modele",
    "disclaimer": "Oferta ma charakter informacyjny. Szczegóły u autoryzowanego dealera Jeep.",
}


def main():
    print("=" * 60)
    print("Jeep Model Feed — cennik SCCF (jeep.pl)")
    print("=" * 60)

    rows = fca_sccf.scrape_brand(BRAND)

    print(f"\nZapisywanie {len(rows)} wierszy...")
    scraper_utils.safe_save_csv(rows, fca_sccf.FIELDNAMES, OUTPUT_FILE,
                                min_rows_threshold=5)
    print("Zakończono.")


if __name__ == "__main__":
    main()

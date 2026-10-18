# -*- coding: utf-8 -*-
"""
Abarth Model Feed
- Źródło: cennik SCCF konfiguratora abarth.pl (marka 66)
- Wspólna logika rodziny ex-FCA: scrapers/fca_sccf.py

Abarth to najmniejsza marka w zestawie (kilka wersji w cenniku) i jedyna bez
sekcji /modele/ — strony modeli leżą w korzeniu (/abarth-500e, /abarth-695).
Dlatego próg zapisu to 1 wiersz: pełny, poprawny feed Abartha bywa krótszy
niż domyślne minimum 5.
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
                           "data", "abarth_model.csv")

BRAND = {
    "host": "www.abarth.pl",
    "slug": "abarth",
    "brand_code": "66",
    "make_label": "Abarth",
    "id_prefix": "ABA",
    "page_pattern": r"/(?:abarth-)?[0-9]{3}[a-z0-9-]*/?$",
    # 600e ma stronę, ale nie ma jej ani w sitemapie, ani w menu — bez tego
    # wpisu jedyny model spoza 500e dostawałby link do strony głównej
    "extra_pages": [
        {"text": "600e", "url": "https://www.abarth.pl/nowy-abarth-600e", "image": ""},
    ],
    "fallback_link": "https://www.abarth.pl/",
    "disclaimer": "Oferta ma charakter informacyjny. Szczegóły u autoryzowanego dealera Abarth.",
}


def main():
    print("=" * 60)
    print("Abarth Model Feed — cennik SCCF (abarth.pl)")
    print("=" * 60)

    rows = fca_sccf.scrape_brand(BRAND)

    print(f"\nZapisywanie {len(rows)} wierszy...")
    scraper_utils.safe_save_csv(rows, fca_sccf.FIELDNAMES, OUTPUT_FILE,
                                min_rows_threshold=1)
    print("Zakończono.")


if __name__ == "__main__":
    main()

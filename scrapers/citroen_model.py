# -*- coding: utf-8 -*-
"""
Citroën Model Feed
- Źródło: API configv3 (c-pl-pl-btoc + c-pl-pl-btob), wspólne: scrapers/configv3.py
- Rendery 3D: visuel3d-secure.citroen.com (ten sam wizualizator co DS)
- Wyjście: citroen_osobowe_model.csv + citroen_dostawcze_model.csv

Zakres `c-pl-pl-*` zwraca też modele DS (DS 3, DS 4, N°4, N°8...) — obie marki
siedzą na jednym konfiguratorze. Odsiewamy je, bo DS ma własny feed
(scrapers/ds_model.py) i inaczej te same auta byłyby w dwóch feedach.
"""
import os
import re
import sys

from bs4 import BeautifulSoup

if sys.stdout.encoding and sys.stdout.encoding.lower() != "utf-8":
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

try:
    from scrapers import scraper_utils, configv3
except ModuleNotFoundError:
    import scraper_utils
    import configv3

BRAND_SITE = "https://www.citroen.pl"
API_BTOC = "https://api-cdn.configv3.awsmpsa.com/api/v4/c-pl-pl-btoc/vehicles"
API_BTOB = "https://api-cdn.configv3.awsmpsa.com/api/v4/c-pl-pl-btob/vehicles"

OUTPUT_DIR = os.path.join(os.path.dirname(os.path.dirname(__file__)), "data")
OUTPUT_FILE_OSO = os.path.join(OUTPUT_DIR, "citroen_osobowe_model.csv")
OUTPUT_FILE_DOS = os.path.join(OUTPUT_DIR, "citroen_dostawcze_model.csv")

DISCLAIMER = ("Oferta ma charakter informacyjny. "
              "Szczegóły u autoryzowanego dealera Citroën.")

# Modele DS w zakresie Citroëna — mają własny feed (ds_model.py)
DS_MODEL_RX = re.compile(r"^(DS\b|N°)", re.IGNORECASE)

# Adresy stron modeli — sprawdzone ręcznie, bo sitemapa citroen.pl zwraca 403,
# a slugi bywają nieprzewidywalne ("Nowy C3" -> /modele/c3.html, dostawcze
# siedzą w /modele/utility/ i mają przedrostek e- niezależnie od napędu)
MODEL_LINKS = {
    "Nowy C3": f"{BRAND_SITE}/modele/c3.html",
    "Nowy C3 Aircross": f"{BRAND_SITE}/modele/nowy-c3-aircross.html",
    "C4": f"{BRAND_SITE}/modele/c4.html",
    "C4 X": f"{BRAND_SITE}/modele/c4-x.html",
    "Nowy C5 Aircross": f"{BRAND_SITE}/modele/nowy-c5-aircross.html",
    "Berlingo": f"{BRAND_SITE}/modele/nowy-berlingo.html",
    "SpaceTourer": f"{BRAND_SITE}/modele/new-e-spacetourer.html",
    "Berlingo Van": f"{BRAND_SITE}/modele/utility/nowy-e-berlingo-van.html",
    "Jumpy": f"{BRAND_SITE}/modele/utility/nowy-e-jumpy.html",
    "Jumper": f"{BRAND_SITE}/modele/utility/nowy-e-jumper.html",
    "C3 VAN": f"{BRAND_SITE}/modele/utility/eC3-van.html",
}
FALLBACK_LINK = f"{BRAND_SITE}/samochody-osobowe.html"


def render_url(lcdv, color_id, interior_id, rim_id):
    """Render 3D konkretnej konfiguracji (wizualizator Citroëna/DS)."""
    trim_param = f"&trim={interior_id}" if interior_id else ""
    opt_param = f"&opt1={rim_id}" if rim_id else ""
    return (f"https://visuel3d-secure.citroen.com/V3DImage.ashx"
            f"?client=CFGAP3D&mkt=PL&env=PROD&version={lcdv}"
            f"&ratio=1&format=jpg&quality=90&width=1280"
            f"&view=001&color={color_id}{trim_param}{opt_param}&back=0")


def fetch_lease(session, url, cache):
    """Rata z promocji na stronie modelu (jeśli marka jakąś prowadzi)."""
    if url in cache:
        return cache[url]
    lease = None
    try:
        r = session.get(url, timeout=30)
        if r.status_code == 200:
            text = BeautifulSoup(r.text, "html.parser").get_text(" ", strip=True)
            lease = scraper_utils.extract_lease_price(text)
    except Exception as e:
        print(f"    UWAGA: nie pobrano {url}: {e}")
    cache[url] = lease
    return lease


def scrape_segment(session, api_base, label, lease_cache, skip_labels=()):
    """Jeden segment (osobowe albo dostawcze) -> wiersze feedu."""
    models = configv3.fetch_derived_models(session, api_base)
    print(f"  {label}: {len(models)} modeli w API")

    rows = []
    seen_labels = []
    for model in models:
        model_label = model.get("label") or ""
        model_id = model.get("id") or ""
        if DS_MODEL_RX.match(model_label):
            print(f"    · {model_label} — model DS, pomijam (ma własny feed)")
            continue
        if model_label in skip_labels:
            print(f"    · {model_label} — jest już wśród osobowych, pomijam")
            continue

        versions = configv3.fetch_versions(session, api_base, model_id)
        if not versions:
            print(f"    UWAGA: {model_label}: brak wersji w API")
            continue

        trims = configv3.extract_trims(versions, render_url)
        page_url = MODEL_LINKS.get(model_label, FALLBACK_LINK)
        # strona zbiorcza pokazuje najniższą ratę całej gamy, nie tego modelu,
        # więc model bez własnej strony idzie bez raty (CASH)
        lease = (fetch_lease(session, page_url, lease_cache)
                 if model_label in MODEL_LINKS else None)
        model_rows = configv3.build_rows(
            "Citroën", "CIT", model_label, trims, page_url, lease, DISCLAIMER)
        rows.extend(model_rows)

        seen_labels.append(model_label)
        note = "" if model_label in MODEL_LINKS else "  (link zbiorczy)"
        print(f"    {model_label}: {len(trims)} trimów, "
              f"{len(model_rows)} wierszy{note}")
    return rows, seen_labels


def main():
    print("=" * 60)
    print("Citroën Model Feed — API configv3")
    print("=" * 60)
    os.makedirs(OUTPUT_DIR, exist_ok=True)

    session = configv3.make_session(BRAND_SITE)
    lease_cache = {}

    print("\n[1/3] Osobowe (btoc)...")
    osobowe, oso_labels = scrape_segment(session, API_BTOC, "osobowe", lease_cache)

    # Berlingo osobowe wisi w obu zakresach (btob to ten sam samochód
    # wystawiony firmom) — bez tego trafiłby do dwóch feedów naraz
    print("\n[2/3] Dostawcze (btob)...")
    dostawcze, _ = scrape_segment(session, API_BTOB, "dostawcze", lease_cache,
                                  skip_labels=set(oso_labels))

    print(f"\n[3/3] Zapisywanie: osobowe={len(osobowe)}, dostawcze={len(dostawcze)}")
    scraper_utils.safe_save_csv(osobowe, configv3.FIELDNAMES, OUTPUT_FILE_OSO,
                                min_rows_threshold=5)
    scraper_utils.safe_save_csv(dostawcze, configv3.FIELDNAMES, OUTPUT_FILE_DOS,
                                min_rows_threshold=5)
    print("Zakończono.")


if __name__ == "__main__":
    main()

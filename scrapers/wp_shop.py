# -*- coding: utf-8 -*-
"""
Wspólne helpery sklepów WordPress Stellantis (Opel, Citroën, Peugeot, DS)
=========================================================================

Rodzina sklep.*.pl: lista produktów z `/wp-json/wp/v2/product`
(title=VIN, class_list=atrybuty pa_*), raty przez scrapers/sfs_calculator.py.

Tu mieszka wyłącznie kod identyczny dla wszystkich czterech marek —
parsowanie atrybutów i budowa wierszy zostają w plikach marek, bo tam
realnie się różnią (mapy modeli, body style, paliwa).
"""
import json
import os
import time

import requests

try:
    from scrapers import scraper_utils
except ModuleNotFoundError:
    import scraper_utils

UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"


def fetch_wp_products(api_url, retries=3):
    """Pełna lista produktów z WP API (paginacja po 100 aż do HTTP 400).

    Koniec wyników WP sygnalizuje HTTP 400 (strona poza zakresem) albo pusta
    lista. Każdy inny błąd (timeout, 5xx, zły JSON) ponawiamy, a po
    wyczerpaniu prób rzucamy wyjątek: ucięta lista to ucięty feed, który
    zapisałby się jako pełny i wypchnął do Gista połowę aut.
    """
    all_products = []
    page = 1
    session = requests.Session()
    session.headers.update({"User-Agent": UA})
    while True:
        url = f"{api_url}?per_page=100&page={page}"
        for attempt in range(retries):
            try:
                r = session.get(url, timeout=30)
                if r.status_code == 400:
                    print(f"  Koniec wyników (HTTP 400 na stronie {page}).")
                    return all_products
                r.raise_for_status()
                data = r.json()
                break
            except Exception as e:
                if attempt == retries - 1:
                    msg = (f"WP API {api_url}: strona {page} niedostępna po "
                           f"{retries} próbach ({e}). Przerywam, żeby nie "
                           f"zapisać niepełnego feedu.")
                    scraper_utils.send_email_alert("WP API Error", msg)
                    raise RuntimeError(msg) from e
                wait = 3 * (2 ** attempt)
                print(f"  Błąd przy stronie {page}: {e}. Ponawiam za {wait}s...")
                time.sleep(wait)
        if not data:
            return all_products
        all_products.extend(data)
        print(f"  Strona {page} ({len(data)} aut, łącznie: {len(all_products)})")
        page += 1


def download_image(url, filepath):
    """Pobiera zdjęcie, jeśli nie ma go jeszcze w cache (data/images).

    Zapis przez plik .part i os.replace: przerwane pobieranie nie zostawia
    uciętego pliku, który przy następnym runie uchodziłby za gotowy.
    """
    if os.path.exists(filepath):
        return True
    part = filepath + ".part"
    try:
        r = requests.get(url, stream=True, timeout=30, headers={"User-Agent": UA})
        if r.status_code != 200:
            return False
        with open(part, "wb") as f:
            for chunk in r.iter_content(65536):
                f.write(chunk)
        if os.path.getsize(part) == 0:
            os.remove(part)
            return False
        os.replace(part, filepath)
        return True
    except Exception as e:
        print(f"  Nie pobrano zdjęcia {url}: {e}")
        if os.path.exists(part):
            try:
                os.remove(part)
            except OSError:
                pass
        return False


def format_address_json(street, city, city_to_region, default_region="Mazowieckie"):
    """Adres w formacie JSON wymaganym przez feedy (null-safe)."""
    street, city = street or "", city or ""
    region = city_to_region.get(city, default_region)
    return json.dumps({
        "addr1": street.upper(),
        "city": city.upper(),
        "region": region.upper(),
        "country": "PL",
    }, ensure_ascii=False)


def resolve_dealer(raw_city, raw_name, locations, allow_unknown=True):
    """Miasto z dataLayer -> (city, street, lat, lon).

    Znane miasto -> dane salonu z `locations`. Nieznane (gdy allow_unknown):
    samo miasto jako adres i PUSTE współrzędne — lepsze niż sklejka
    "ulica z Warszawy + obce miasto" (adres, który nie istnieje); puste
    lat/lon są już w feedach Fiata/Jeepa, więc odbiorcy je akceptują.
    """
    if raw_city:
        cand = raw_city.strip()
        for known, data in locations.items():
            if known.upper() == cand.upper():
                return known, data["street"], data["lat"], data["lon"]
        if allow_unknown and len(cand) > 1:
            return cand.title(), cand.title(), "", ""
    if raw_name:
        up = raw_name.upper()
        for known, data in locations.items():
            if known.upper() in up:
                return known, data["street"], data["lat"], data["lon"]
    fallback = locations["Warszawa"]
    return "Warszawa", fallback["street"], fallback["lat"], fallback["lon"]


def get_model_slug(product, skip_slugs=("bez-kategorii",)):
    """Slug kategorii (modelu) z class_list; None dla produktów-duchów."""
    classes = product.get("class_list", {})
    class_values = classes.values() if isinstance(classes, dict) else classes
    for cls in class_values:
        if cls.startswith("product_cat-"):
            slug = cls.replace("product_cat-", "")
            if slug not in skip_slugs:
                return slug
    return None

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

import requests

UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"


def fetch_wp_products(api_url):
    """Pełna lista produktów z WP API (paginacja po 100 aż do HTTP 400)."""
    all_products = []
    page = 1
    session = requests.Session()
    session.headers.update({"User-Agent": UA})
    while True:
        try:
            r = session.get(f"{api_url}?per_page=100&page={page}", timeout=15)
            if r.status_code == 400:
                print(f"  Koniec wyników (HTTP 400 na stronie {page}).")
                break
            r.raise_for_status()
            data = r.json()
            if not data:
                break
            all_products.extend(data)
            print(f"  Strona {page} ({len(data)} aut, łącznie: {len(all_products)})")
            page += 1
        except Exception as e:
            print(f"  Koniec wyników / Błąd przy stronie {page}: {e}")
            break
    return all_products


def download_image(url, filepath):
    """Pobiera zdjęcie, jeśli nie ma go jeszcze w cache (data/images)."""
    if os.path.exists(filepath):
        return True
    try:
        r = requests.get(url, stream=True, timeout=10, headers={"User-Agent": UA})
        if r.status_code == 200:
            with open(filepath, "wb") as f:
                for chunk in r.iter_content(1024):
                    f.write(chunk)
            return True
    except Exception:
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

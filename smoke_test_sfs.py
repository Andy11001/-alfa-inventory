# -*- coding: utf-8 -*-
"""Szybki test zdrowia ścieżki SFS (bez Selenium) dla wszystkich 4 marek.

Uruchomienie:  python smoke_test_sfs.py
Dla każdej marki bierze 3 auta z WP API i sprawdza, czy sfs_calculator
zwraca raty. Kończy się kodem != 0, gdy któraś marka nie zwróci nic —
nadaje się do ręcznej diagnozy i do CI.
"""
import os
import sys
import time

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "scrapers"))
if sys.stdout.encoding and sys.stdout.encoding.lower() != "utf-8":
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

os.environ.setdefault("SFS_DISABLE_SELENIUM_RESCUE", "1")

import requests
import sfs_calculator

WP_APIS = {
    "opel": "https://sklep.opel.pl/wp-json/wp/v2/product",
    "citroen": "https://sklep.citroen.pl/wp-json/wp/v2/product",
    "peugeot": "https://sklep.peugeot.pl/wp-json/wp/v2/product",
    "ds": "https://sklep.dsautomobiles.pl/wp-json/wp/v2/product",
}


def sample_links(api_url, n=3):
    links = []
    for page in range(1, 5):
        try:
            r = requests.get(f"{api_url}?per_page=50&page={page}",
                             headers={"User-Agent": "Mozilla/5.0"}, timeout=20)
            if r.status_code != 200:
                break
            for p in r.json():
                cl = p.get("class_list", {})
                vals = cl.values() if isinstance(cl, dict) else cl
                if any(c.startswith("product_cat-") and c != "product_cat-bez-kategorii"
                       for c in vals):
                    links.append(p["link"])
                if len(links) >= n:
                    return links
        except Exception:
            break
    return links


failed = []
for brand, api in WP_APIS.items():
    print(f"\n=== {brand} ===")
    links = sample_links(api)
    if not links:
        print("  ⚠ Nie udało się pobrać linków z WP API")
        failed.append(brand)
        continue
    t0 = time.monotonic()
    rates, stats = sfs_calculator.get_inventory_rates(brand, links)
    dt = time.monotonic() - t0
    for link, info in rates.items():
        print(f"  {info['installment']:>6} PLN [{info['product_type']}/{info['price_type']}]"
              f"  city={info['dealer_city']}  {link.split('/')[-2]}")
    print(f"  -> {len(rates)}/{len(links)} rat w {dt:.1f}s")
    if not rates:
        failed.append(brand)

print("\n" + "=" * 50)
if failed:
    print(f"❌ BRAK RAT dla: {', '.join(failed)} — sprawdź docs/SFS_CALCULATOR.md")
    sys.exit(1)
print("✅ Wszystkie marki zwracają raty przez API SFS.")

# -*- coding: utf-8 -*-
"""
Bezpośredni klient kalkulatora Stellantis Financial Services (SFS)
==================================================================

Zastępuje Selenium przy pobieraniu rat z product page'ów sklepów WordPress:
sklep.opel.pl / sklep.citroen.pl / sklep.peugeot.pl / sklep.dsautomobiles.pl.

Jak to działa (odkryte przez analizę financialCalculatorPlugin.min.js):
  1. Strona produktu zawiera w HTML (server-side) inline'owy JS:
       - `new FCP.FinancialCalculatorPlugin({calculatorApi: 'https://sfs...', brandSlug: '...'})`
       - `fcp.attachOffer('id-oferty-b2b', {<dane pojazdu>}, {<pola>}, [], true)`
       - konfiguracje suwaków noUiSlider (start = wartości domyślne kalkulatora)
       - dataLayer z `edealerCity` (miasto dealera)
  2. Przeglądarkowy kalkulator wysyła te dane WebSocketem/POST-em do
       https://sfs.stellantis-financial-services.pl/api/calculation/...
     i wstawia wynik do #top_sekcja_wysokosc_raty — my robimy ten sam POST
     bezpośrednio (batchowo, dziesiątki aut w jednym żądaniu).

Wyświetlana na stronie rata = produkt finansowy domyślnej zakładki z polami
z suwaków. Zweryfikowano empirycznie (Selenium vs API, czerwiec 2026):
  opel -> l101 ("Leasing 101,8%"), peugeot -> l101, citroen -> l101 (jedyny),
  ds-automobiles -> b2b ("Abonament SimplyDrive B2B").

Samonaprawialność:
  - kilka wariantów regexów na każdy parsowany element,
  - brakujące suwaki -> domyślne wartości marki (snapshot), API i tak
    przycina pola do dozwolonych wartości (availableFields),
  - brak preferowanego produktu -> łańcuch zapasowy (tylko produkty NET,
    żeby semantyka "rata netto/mies." w feedzie się nie zmieniła),
  - nieudany batch -> retry z backoffem, potem podział batcha na pół,
  - pokrycie < SELENIUM_RESCUE_THRESHOLD -> awaryjny Selenium (limitowany),
  - każda degradacja trafia do `stats` i (zbiorczo) do alertu e-mail.
"""
import os
import re
import json
import time
import uuid
import threading
from concurrent.futures import ThreadPoolExecutor, as_completed

import requests

try:
    from scrapers import scraper_utils
except ModuleNotFoundError:
    import scraper_utils

SFS_API = "https://sfs.stellantis-financial-services.pl/api"
UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36")

# Produkty rozliczane netto — tylko te mogą trafić do feedu "rata netto/mies."
NET_PRODUCTS = ("l101", "b2b")

BRAND_CONFIG = {
    "opel": {
        "slug": "opel",
        "origin": "https://sklep.opel.pl",
        "display_product": "l101",
        "default_fields": {
            "l101": {"period": 60, "contribution": 20, "repurchase": 26},
            "b2b": {"period": 48, "contribution": 10, "limitKm": 10000},
        },
    },
    "citroen": {
        "slug": "citroen",
        "origin": "https://sklep.citroen.pl",
        "display_product": "l101",
        "default_fields": {
            "l101": {"period": 48, "contribution": 20, "repurchase": 20},
            "b2b": {"period": 48, "contribution": 10, "limitKm": 10000},
        },
    },
    "peugeot": {
        "slug": "peugeot",
        "origin": "https://sklep.peugeot.pl",
        "display_product": "l101",
        "default_fields": {
            "l101": {"period": 60, "contribution": 20, "repurchase": 20},
            "b2b": {"period": 48, "contribution": 10, "limitKm": 10000},
        },
    },
    "ds": {
        "slug": "ds-automobiles",
        "origin": "https://sklep.dsautomobiles.pl",
        "display_product": "b2b",
        "default_fields": {
            "b2b": {"period": 24, "contribution": 15, "limitKm": 10000},
            "l101": {"period": 36, "contribution": 45, "repurchase": 41},
        },
    },
}

PAGE_WORKERS = int(os.environ.get("SFS_PAGE_WORKERS", "8"))
DETECT_CHUNK = int(os.environ.get("SFS_DETECT_CHUNK", "40"))
SELENIUM_RESCUE_THRESHOLD = float(os.environ.get("SFS_RESCUE_THRESHOLD", "0.5"))
SELENIUM_RESCUE_CAP = int(os.environ.get("SFS_RESCUE_CAP", "150"))

_thread_local = threading.local()


def _session():
    """Sesja requests per wątek (keep-alive bez współdzielenia między wątkami)."""
    s = getattr(_thread_local, "session", None)
    if s is None:
        s = requests.Session()
        s.headers.update({"User-Agent": UA})
        _thread_local.session = s
    return s


# ---------------------------------------------------------------------------
# Parsowanie strony produktu (czysty HTML, bez JS)
# ---------------------------------------------------------------------------

def _js_object_to_dict(src):
    """Zamienia inline'owy obiekt JS (z attachOffer) na dict.

    Wartości liczbowe bywają wyrażeniami ("176100/1.23") — liczymy je
    w ograniczonym eval (tylko literały i dzielenie, bez builtins).
    """
    src = re.sub(r"//[^\n]*", "", src)
    out = {}
    for m in re.finditer(r'"(\w+)"\s*:\s*([^,}]+)', src):
        key, raw = m.group(1), m.group(2).strip()
        if raw.startswith('"') or raw.startswith("'"):
            out[key] = raw.strip("\"'")
        elif re.fullmatch(r"[\d.\s/*+-]+", raw):
            try:
                out[key] = eval(raw, {"__builtins__": {}})  # noqa: S307 — tylko arytmetyka
            except Exception:
                out[key] = raw
        else:
            out[key] = raw
    return out


# Warianty regexów — gdy zmieni się formatowanie strony, próbujemy kolejnych.
_ATTACH_OFFER_PATTERNS = [
    # attachOffer('id-oferty-b2b', {…}, {…}, …)
    r"attachOffer\(\s*['\"][^'\"]+['\"]\s*,\s*(\{.*?\})\s*,\s*(\{.*?\})\s*,",
    # attachOffer z dowolnymi białymi znakami / bez drugiego obiektu
    r"attachOffer\(\s*['\"][^'\"]+['\"]\s*,\s*(\{.*?\})\s*,\s*(\{.*?\})",
]

_CITY_PATTERNS = [
    r'"edealerCity"\s*:\s*"([^"]+)"',
    r"'edealerCity'\s*:\s*'([^']+)'",
    r'"dealerCity"\s*:\s*"([^"]+)"',
]

_DEALER_NAME_PATTERNS = [
    r'"edealerName"\s*:\s*"([^"]+)"',
    r"'edealerName'\s*:\s*'([^']+)'",
]


def parse_product_page(html):
    """Wyciąga ze strony produktu wszystko, czego potrzebuje kalkulator i feed.

    Zwraca dict:
      vehicle      – payload pojazdu dla API SFS (None gdy nie znaleziono)
      sliders      – {typ_produktu: {period, contribution, ...}} z noUiSlider
      active_pane  – customer-type aktywnej zakładki (informacyjnie)
      dealer_city  – miasto dealera z dataLayer (lub None)
      dealer_name  – nazwa dealera z dataLayer (lub None)
      year         – rok produkcji, jeśli strona go podaje (lub None)
    """
    result = {"vehicle": None, "sliders": {}, "active_pane": None,
              "dealer_city": None, "dealer_name": None, "year": None}

    for pat in _ATTACH_OFFER_PATTERNS:
        m = re.search(pat, html, re.DOTALL)
        if m:
            vehicle = _js_object_to_dict(m.group(1))
            # Sanity: payload musi mieć cenę, inaczej szukaj dalej
            if isinstance(vehicle.get("grossPrice"), (int, float)):
                result["vehicle"] = vehicle
                break

    for ptype in ("b2b", "l101", "b2c", "p0p"):
        fields = {}
        for fld in ("period", "contribution", "repurchase", "limitKm"):
            m = re.search(
                re.escape(f"{ptype}_suwak_{fld}") + r"\s*,\s*\{[^}]*?start:\s*([\d.]+)",
                html, re.DOTALL)
            if m:
                val = float(m.group(1))
                fields[fld] = int(val) if val == int(val) else val
        if fields:
            result["sliders"][ptype] = fields

    m = re.search(r'tab-pane[^"]*\bactive\b[^>]*customer-type="(\w+)"', html)
    if m:
        result["active_pane"] = m.group(1)

    for pat in _CITY_PATTERNS:
        m = re.search(pat, html)
        if m and m.group(1).strip():
            result["dealer_city"] = m.group(1).strip()
            break

    for pat in _DEALER_NAME_PATTERNS:
        m = re.search(pat, html)
        if m and m.group(1).strip():
            result["dealer_name"] = m.group(1).strip()
            break

    m = re.search(r"Rok produkcji\s*[:\-]?\s*(\d{4})", html, re.IGNORECASE)
    if m:
        result["year"] = m.group(1)

    return result


# ---------------------------------------------------------------------------
# API SFS — batchowe detect/calculate
# ---------------------------------------------------------------------------

def _sfs_headers(origin):
    return {
        "User-Agent": UA,
        "Accept": "application/json",
        "Content-Type": "application/json",
        "Origin": origin,
        "Referer": origin + "/",
    }


def detect_products_batch(brand_slug, origin, items, chunk_size=DETECT_CHUNK,
                          retries=3):
    """Batchowe wywołanie detect-website-products.

    items: lista (key, vehicle, fields). Zwraca {key: {typ: dane_produktu}}.
    Nieudany chunk: retry z backoffem, potem rekurencyjny podział na pół —
    pojedyncze zepsute auto nie zabija całej paczki.
    """
    url = (f"{SFS_API}/calculation/detect-website-products/"
           f"{brand_slug}/salon/production"
           f"?withSolData=true&withCalculationParams=true")
    results = {}

    def post_chunk(chunk, attempt=0):
        body, keymap = {}, {}
        for key, vehicle, fields in chunk:
            u = str(uuid.uuid4())
            body[u] = {"vehicle": vehicle, "fields": fields, "extraServices": []}
            keymap[u] = key
        try:
            r = requests.post(url, json=body, headers=_sfs_headers(origin),
                              timeout=60)
            r.raise_for_status()
            data = r.json()
            for u, det in data.items():
                if u in keymap and isinstance(det, dict):
                    results[keymap[u]] = det
            return True
        except Exception as e:
            if attempt < retries - 1:
                time.sleep(2 * (attempt + 1))
                return post_chunk(chunk, attempt + 1)
            if len(chunk) > 1:
                mid = len(chunk) // 2
                post_chunk(chunk[:mid])
                post_chunk(chunk[mid:])
                return True
            scraper_utils.logger.warning(
                f"SFS detect nie powiódł się dla {chunk[0][0]}: {e}")
            return False

    for i in range(0, len(items), chunk_size):
        post_chunk(items[i:i + chunk_size])
    return results


def _effective_product(page, cfg):
    """Produkt, który ta KONKRETNA strona wyświetla, i pola jego suwaków.

    Kolejność: preferowany produkt marki (jeśli strona ma jego suwaki) ->
    aktywna zakładka, o ile NET -> dowolny produkt NET z suwakami ->
    preferowany produkt z domyślnymi polami (fields=None -> caller użyje
    defaults). Dzięki temu modele bez produktu marki (np. osobowe Peugeoty
    bez l101) dostają dokładnie to, co widzi użytkownik na stronie.
    """
    sliders = page.get("sliders", {})
    preferred = cfg["display_product"]
    if preferred in sliders:
        return preferred, sliders[preferred]
    active = page.get("active_pane")
    if active in NET_PRODUCTS and active in sliders:
        return active, sliders[active]
    for ptype in NET_PRODUCTS:
        if ptype in sliders:
            return ptype, sliders[ptype]
    return preferred, None


def pick_display_rate(detected, preferred):
    """Wybiera ratę tak, jak wyświetla ją strona.

    detected: {typ: dane_produktu} z detect-website-products.
    Zwraca (rata_int, typ_produktu, price_type) lub (None, None, None).
    Fallback ograniczony do produktów NET — feed obiecuje "netto/mies.".
    """
    order = [preferred] + [p for p in NET_PRODUCTS if p != preferred]
    for ptype in order:
        prod = detected.get(ptype)
        if isinstance(prod, dict):
            inst = prod.get("installment")
            if isinstance(inst, (int, float)) and inst > 100:
                return round(inst), ptype, prod.get("priceType")
    return None, None, None


# ---------------------------------------------------------------------------
# Wysoki poziom: lista produktów WP -> raty (+ dane ze stron)
# ---------------------------------------------------------------------------

def get_inventory_rates(brand_key, links, progress_label="aut"):
    """Główne wejście dla scraperów inwentarza.

    links: lista URL-i stron produktów.
    Zwraca (rates, stats):
      rates – {link: {"installment": int, "product_type": str, "price_type": str,
                      "dealer_city": str|None, "dealer_name": str|None,
                      "gross_price": float|None, "year": str|None}}
      stats – licznik degradacji do alertów (parse_failed, fallback_product,
              default_sliders, missing_rate, rescue_used, total).
    """
    cfg = BRAND_CONFIG[brand_key]
    stats = {"total": len(links), "page_failed": 0, "parse_failed": 0,
             "default_sliders": 0, "fallback_product": 0, "missing_rate": 0,
             "rescue_used": 0}

    # --- 1. Równoległe pobranie stron produktów (czyste GET-y) ---
    parsed = {}

    def fetch_and_parse(link):
        # Cichy retry (bez alertów e-mail per URL — degradacje raportujemy
        # zbiorczo w stats; pojedyncze 500-tki to często "duchy" po
        # skasowanych autach, nie awaria).
        for attempt in range(3):
            try:
                r = _session().get(link, timeout=30)
                r.raise_for_status()
                return link, parse_product_page(r.text)
            except Exception:
                if attempt < 2:
                    time.sleep(1.5 * (attempt + 1))
        return link, None

    with ThreadPoolExecutor(max_workers=PAGE_WORKERS) as ex:
        futures = [ex.submit(fetch_and_parse, l) for l in links]
        for i, fut in enumerate(as_completed(futures), 1):
            link, page = fut.result()
            parsed[link] = page
            if i % 50 == 0 or i == len(links):
                print(f"  Pobrano strony {i}/{len(links)} {progress_label}...")

    # --- 2. Budowa zapytań detect (pojazd + pola suwaków zakładki) ---
    # Produkt "efektywny" wybieramy per strona: nie każdy model ma preferowany
    # produkt marki (np. osobowe Peugeoty nie mają l101 — tylko b2b).
    items = []
    effective = {}
    for link, page in parsed.items():
        if page is None:
            stats["page_failed"] += 1
            continue
        if not page.get("vehicle"):
            stats["parse_failed"] += 1
            continue
        ptype, fields = _effective_product(page, cfg)
        if fields is None:
            fields = cfg["default_fields"].get(ptype, {"period": 48, "contribution": 10})
            stats["default_sliders"] += 1
        effective[link] = ptype
        items.append((link, page["vehicle"], fields))

    detected = detect_products_batch(cfg["slug"], cfg["origin"], items)
    print(f"  SFS API: obliczono raty dla {len(detected)}/{len(items)} zapytań.")

    # --- 3. Wybór wyświetlanej raty per auto ---
    rates = {}
    for link, page in parsed.items():
        det = detected.get(link)
        if not det:
            stats["missing_rate"] += 1
            continue
        preferred = effective.get(link, cfg["display_product"])
        rate, ptype, price_type = pick_display_rate(det, preferred)
        if rate is None:
            stats["missing_rate"] += 1
            continue
        if ptype != preferred:
            stats["fallback_product"] += 1
        vehicle = page.get("vehicle") or {}
        rates[link] = {
            "installment": rate,
            "product_type": ptype,
            "price_type": price_type,
            "dealer_city": page.get("dealer_city"),
            "dealer_name": page.get("dealer_name"),
            "gross_price": vehicle.get("grossPrice"),
            "year": page.get("year"),
        }

    # --- 4. Awaryjny Selenium, gdy API praktycznie nie działa ---
    coverage = len(rates) / max(1, len(links))
    if coverage < SELENIUM_RESCUE_THRESHOLD and \
            os.environ.get("SFS_DISABLE_SELENIUM_RESCUE") != "1":
        missing = [l for l in links if l not in rates][:SELENIUM_RESCUE_CAP]
        print(f"  ⚠ Pokrycie API tylko {coverage:.0%} — awaryjny Selenium "
              f"dla {len(missing)} aut...")
        rescued = _selenium_rescue(missing)
        for link, rate in rescued.items():
            page = parsed.get(link) or {}
            vehicle = (page.get("vehicle") or {}) if page else {}
            rates[link] = {
                "installment": rate, "product_type": "selenium",
                "price_type": "NET",
                "dealer_city": page.get("dealer_city") if page else None,
                "dealer_name": page.get("dealer_name") if page else None,
                "gross_price": vehicle.get("grossPrice"),
                "year": page.get("year") if page else None,
            }
        stats["rescue_used"] = len(rescued)

    _maybe_alert(brand_key, stats, coverage=len(rates) / max(1, len(links)))
    return rates, stats


def _selenium_rescue(links):
    """Ostatnia linia obrony: stary scraper Selenium, 1 driver, sekwencyjnie."""
    rescued = {}
    try:
        try:
            from scrapers.selenium_helper import get_b2b_price_selenium, init_driver
        except ModuleNotFoundError:
            from selenium_helper import get_b2b_price_selenium, init_driver
        driver = init_driver()
        try:
            for i, link in enumerate(links, 1):
                if i > 1 and i % 25 == 0:
                    try:
                        driver.quit()
                    except Exception:
                        pass
                    driver = init_driver()
                try:
                    val = get_b2b_price_selenium(link, driver=driver)
                    if val and val.isdigit():
                        rescued[link] = int(val)
                except Exception:
                    pass
        finally:
            try:
                driver.quit()
            except Exception:
                pass
    except Exception as e:
        scraper_utils.logger.error(f"Awaryjny Selenium niedostępny: {e}")
    return rescued


def _maybe_alert(brand_key, stats, coverage):
    """Jeden zbiorczy e-mail, gdy coś się zdegradowało (nie per auto)."""
    problems = []
    if coverage < 0.7 and stats["total"] > 10:
        problems.append(f"pokrycie rat tylko {coverage:.0%}")
    if stats["parse_failed"] > max(3, stats["total"] * 0.1):
        problems.append(f"{stats['parse_failed']} stron bez danych pojazdu "
                        f"(zmiana struktury attachOffer?)")
    if stats["fallback_product"] > 0:
        problems.append(f"{stats['fallback_product']} aut użyło zapasowego "
                        f"produktu finansowego (zmiana oferty na stronie?)")
    if stats["rescue_used"] > 0:
        problems.append(f"awaryjny Selenium uratował {stats['rescue_used']} aut "
                        f"(API SFS wymaga uwagi)")
    if problems:
        body = (f"Marka: {brand_key}\nStatystyki: {json.dumps(stats, ensure_ascii=False)}\n"
                f"Problemy:\n- " + "\n- ".join(problems) +
                "\n\nFeed został wygenerowany (degradacja kontrolowana), "
                "ale warto sprawdzić, czy strony sklepu się nie zmieniły.")
        scraper_utils.send_email_alert(f"Degradacja scrapera {brand_key}", body)

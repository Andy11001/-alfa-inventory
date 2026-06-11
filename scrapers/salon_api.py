# -*- coding: utf-8 -*-
"""
Wspólna obsługa rodziny salon.*.pl (Alfa Romeo, Jeep, Fiat, Fiat Professional)
==============================================================================

Te serwisy mają identyczne JSON API:
  - lista:     {api}/api/offers/list-<marka>.json?page=N
  - szczegóły: {api}/api/offers/offer-<marka>.json?id=<uid>
z ratą wprost w `price.financing_info.{b2b,l101,b2c}.installment`.

UWAGA — pułapka, która ubiła feed Fiata (13 czerwonych runów, 2026-06-08/11):
detail API potrafi zwrócić **jawne `null`** w polach dealera (region, street…)
zamiast pominąć klucz. `.get(k, "")` przepuszcza wtedy `None` i `.upper()`
wywala cały feed. Dlatego wszędzie koercja `x.get(k) or ""`, a każda oferta
jest przetwarzana w try/except — pojedyncze zepsute auto nie zabija feedu,
degradacje raportujemy jednym zbiorczym alertem.
"""
import requests

try:
    from scrapers import scraper_utils
except ModuleNotFoundError:
    import scraper_utils

FIELDNAMES = [
    "vehicle_id", "title", "description", "link", "image_link",
    "make", "model", "year", "mileage.value", "mileage.unit",
    "body_style", "exterior_color", "state_of_vehicle",
    "price", "currency", "address", "latitude", "longitude",
    "offer_type", "amount_price", "amount_qualifier",
    "fuel_type", "transmission", "drivetrain",
]


def format_address_json(street, city, region, country, post_code=None):
    import json
    # API potrafi zwrócić null zamiast pustego stringa — nie wywalaj się na .upper()
    street, city, region = street or "", city or "", region or ""
    country = country or "PL"
    country_code = "PL" if country.lower() in ["polska", "pl"] else country
    addr = {
        "addr1": street.upper(),
        "city": city.upper(),
        "region": region.upper(),
        "country": country_code.upper(),
    }
    if post_code:
        addr["postal_code"] = post_code
    return json.dumps(addr, ensure_ascii=False)


def fetch_all_offers(api_url):
    """Pobiera wszystkie oferty z paginowanego API listy."""
    all_offers = []
    r = scraper_utils.fetch_with_retry(
        requests, api_url, headers={"User-Agent": "Mozilla/5.0"})
    data = r.json()
    count = data["result"]["info"]["countOfResults"]
    per_page = data["result"]["info"]["offersPerPage"]
    total_pages = (count + per_page - 1) // per_page
    print(f"  {count} ofert ({total_pages} stron)")

    for page in range(1, total_pages + 1):
        d = scraper_utils.fetch_with_retry(
            requests, f"{api_url}?page={page}",
            headers={"User-Agent": "Mozilla/5.0"}).json()
        page_list = d["result"]["list"] or []
        all_offers.extend(page_list)
        print(f"  Strona {page}/{total_pages}: +{len(page_list)}")
    return all_offers


def get_fuel(eng):
    """Typ paliwa z engineType — wspólny dla całej rodziny (CNG tylko Fiat,
    dla pozostałych nieszkodliwy)."""
    if "Hybrid" in eng or "Hybryda" in eng:
        return "Hybrid"
    if "Elektryczn" in eng:
        return "Electric"
    if "Diesel" in eng:
        return "Diesel"
    if "CNG" in eng:
        return "CNG"
    return "Gasoline"


def build_offer_row(session, offer, uid, detail_url_tpl, base_url, make_label,
                    get_body_style, get_drivetrain):
    """Buduje wiersz feedu dla jednej oferty; None gdy brak ceny.

    get_body_style(model) i get_drivetrain(model, version, eng) to różnice
    per marka — reszta logiki jest identyczna dla całej rodziny.
    """
    # Pola z API mogą być jawnym null — .get(k, "") tego nie łapie, stąd `or ""`
    model = offer.get("model") or ""
    version = offer.get("version") or ""

    # Detail API: kolor + lokalizacja dealera
    street, city, region, post_code = "", "", "", ""
    lat, lon = "", ""
    color = "Standard"
    try:
        r_detail = session.get(detail_url_tpl.format(uid=uid), timeout=10)
        if r_detail.status_code == 200:
            d_json = r_detail.json()
            if "color" in d_json and isinstance(d_json["color"], dict):
                color = d_json["color"].get("name") or color
            dealer = d_json.get("dealer") or {}
            if dealer:
                street = dealer.get("street") or ""
                city = dealer.get("city") or ""
                region = dealer.get("region") or ""
                post_code = dealer.get("postCode") or ""
                coords = dealer.get("coordinates") or {}
                if coords:
                    lat = coords.get("latitude") or ""
                    lon = coords.get("longitude") or ""
    except Exception:
        pass

    if not city:
        loc_str = offer.get("localization") or ""
        parts = loc_str.split(",")
        city = parts[1].strip() if len(parts) > 1 else parts[0].strip()
        street = city

    # Cena
    price_data = offer.get("price") or {}
    price_brutto = (price_data.get("final") or {}).get("brutto") \
        or (price_data.get("base") or {}).get("brutto")
    if not price_brutto:
        return None

    # Finansowanie: pierwszy dostępny produkt wg priorytetu
    fin_info = price_data.get("financing_info") or {}
    installment = None
    for fin_key in ["b2b", "l101", "b2c"]:
        if fin_info.get(fin_key):
            installment = fin_info[fin_key].get("installment")
            if installment:
                break

    eng = offer.get("engineType") or ""
    fuel = get_fuel(eng)
    trans = "Manual" if "Manual" in eng else "Automatic"
    drive = get_drivetrain(model, version, eng)

    tiktok_title = scraper_utils.format_inventory_title(model, version, installment)
    tiktok_desc = scraper_utils.format_inventory_description(
        make_label, model, version, installment, city)

    return {
        "vehicle_id": uid,
        "title": tiktok_title,
        "description": tiktok_desc,
        "link": f"{base_url}/{uid}",
        "image_link": offer.get("image"),
        "make": make_label,
        "model": model,
        "year": offer.get("productionYear"),
        "mileage.value": offer.get("mileage") or 0,
        "mileage.unit": "KM",
        "body_style": get_body_style(model),
        "exterior_color": color,
        "state_of_vehicle": "New" if (offer.get("mileage") or 0) < 100 else "Used",
        "price": f"{price_brutto} PLN",
        "currency": "PLN",
        "address": format_address_json(street, city, region, "PL", post_code),
        "latitude": lat,
        "longitude": lon,
        "offer_type": "LEASE",
        "amount_price": f"{installment} PLN" if installment else "",
        "amount_qualifier": "per month" if installment else "",
        "fuel_type": fuel,
        "transmission": trans,
        "drivetrain": drive,
    }


def process_offers(offers, detail_url_tpl, base_url, make_label,
                   get_body_style, get_drivetrain):
    """Lista ofert -> wiersze feedu. Błędy per oferta zbierane i raportowane
    jednym alertem po przekroczeniu progu max(3, 10% ofert)."""
    session = requests.Session()
    session.headers.update({"User-Agent": "Mozilla/5.0"})
    rows = []
    failed = []

    for i, offer in enumerate(offers, 1):
        uid = str(offer.get("uid") or offer.get("id"))
        if i % 20 == 0:
            print(f"  Przetwarzanie {i}/{len(offers)}...")
        try:
            row = build_offer_row(session, offer, uid, detail_url_tpl,
                                  base_url, make_label,
                                  get_body_style, get_drivetrain)
        except Exception as e:
            failed.append(f"{uid}: {e!r}")
            continue
        if row:
            rows.append(row)

    if failed:
        msg = (f"{make_label}: pominięto {len(failed)}/{len(offers)} ofert "
               f"(błąd przetwarzania — możliwa zmiana struktury API):\n- "
               + "\n- ".join(failed[:10]))
        scraper_utils.logger.warning(msg)
        if len(failed) > max(3, len(offers) * 0.1):
            scraper_utils.send_email_alert(
                f"Degradacja scrapera {make_label}",
                msg + "\n\nFeed został wygenerowany bez tych ofert.")

    # Deduplikacja po vehicle_id (API potrafi zwrócić ofertę na 2 stronach)
    return list({r["vehicle_id"]: r for r in rows}.values())

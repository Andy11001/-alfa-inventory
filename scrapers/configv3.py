# -*- coding: utf-8 -*-
"""
Wspólna obsługa API konfiguratora configv3 (rodzina ex-PSA)
===========================================================

Stellantis wystawia cenniki marek ex-PSA pod jednym adresem, różnią się tylko
literą marki w ścieżce:

  https://api-cdn.configv3.awsmpsa.com/api/v4/{X}-pl-pl-{btoc|btob}/vehicles
  X: p = Peugeot, o = Opel, c = Citroën, d = DS

Z każdej wersji bierzemy trim, silnik, cenę i paletę kolorów z linkami do
renderów 3D. Moduł powstał przy dokładaniu Citroëna — peugeot_model.py i
opel_model.py mają jeszcze własne kopie tej logiki i mogą tu przejść przy
najbliższej okazji (nie ruszam ich teraz, żeby nie tykać działających feedów).

UWAGA: zakres `c-pl-pl-*` zwraca także modele DS (DS 3, DS 4, N°8...) —
Citroën i DS dzielą konfigurator. Filtrowanie marki jest po stronie pliku
marki, inaczej feed Citroëna dublowałby ds_model.py.
"""
import time

import requests

try:
    from scrapers import scraper_utils
except ModuleNotFoundError:
    import scraper_utils

# Format feedu modelowego — wspólny z peugeot_model.py / opel_model.py / fca_sccf.py
FIELDNAMES = [
    "vehicle_id", "title", "description", "rodzaj", "make", "model", "year",
    "link", "image_link", "exterior_color", "additional_image_link", "trim",
    "offer_disclaimer", "offer_disclaimer_url", "price", "offer_type",
    "term_length", "offer_term_qualifier", "amount_price", "amount_percentage",
    "amount_qualifier", "downpayment", "downpayment_qualifier",
    "emission_disclaimer", "emission_disclaimer_url",
    "emission_overlay_disclaimer", "emission_image_link", "fuel_type",
]

ENERGY_MAP = {
    "01": "Hybrid",
    "02": "Gasoline",
    "04": "Diesel",
    "05": "Electric",
    "07": "Electric",
    "10": "Plug-in Hybrid",
}



def make_session(brand_site):
    s = requests.Session()
    s.headers.update({
        "User-Agent": ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                       "AppleWebKit/537.36 (KHTML, like Gecko) "
                       "Chrome/120.0.0.0 Safari/537.36"),
        "Accept": "application/json, text/plain, */*",
        "Accept-Language": "pl-PL,pl;q=0.9,en-US;q=0.8,en;q=0.7",
        "Origin": brand_site,
        "Referer": f"{brand_site}/",
    })
    return s


def fetch_derived_models(session, api_base):
    """Lista modeli handlowych (derivedModels). Pusta lista przy awarii —
    drugi wariant (btoc/btob) ma szansę przejść mimo to."""
    for attempt in range(3):
        try:
            r = session.get(f"{api_base}/derivedModels", timeout=30)
            r.raise_for_status()
            time.sleep(1)
            return r.json()
        except Exception as e:
            print(f"  ⚠ derivedModels ({attempt + 1}/3): {e}")
            time.sleep(3)
    return []


def fetch_versions(session, api_base, derived_model_id):
    for attempt in range(3):
        try:
            r = session.get(f"{api_base}/versions?derivedModel={derived_model_id}",
                            timeout=30)
            r.raise_for_status()
            time.sleep(1)
            return r.json()
        except Exception as e:
            print(f"  ⚠ versions {derived_model_id} ({attempt + 1}/3): {e}")
            time.sleep(3)
    return []


def extract_trims(versions, render_url_builder):
    """Wersje z API -> {trim: {"engines": [...], "colors": [...]}}.

    render_url_builder(lcdv, color_id, interior_id, rim_id) buduje adres
    renderu 3D — jedyna rzecz, która różni marki (inny host wizualizatora).
    """
    trims = {}
    for v in versions:
        trim_label = (v.get("grCommercialName") or {}).get("label") or "Standard"
        energy_id = (v.get("energy") or {}).get("id") or "02"
        fuel_type = ENERGY_MAP.get(energy_id, "Gasoline")
        engine_label = (v.get("grEngine") or {}).get("label") or ""
        # API wrzuca część hybryd pod "Benzyna" — ratuje nas nazwa silnika
        if "hybrid" in engine_label.lower() and fuel_type == "Gasoline":
            fuel_type = "Hybrid"
        transmission = (v.get("grTransmissionType") or {}).get("label") or ""
        try:
            price = float(((v.get("prices") or {}).get("price") or {}).get("base") or 0)
        except (TypeError, ValueError):
            price = 0.0
        lcdv = v.get("lcdv") or ""

        looks = ((v.get("globalFeatures") or {}).get("looks") or {}).get("categories") or []
        interior_id = rim_id = ""
        for cat in looks:
            feats = cat.get("features") or []
            if cat.get("id") == "interiors" and feats and not interior_id:
                interior_id = feats[0].get("id") or ""
            elif cat.get("id") == "rims" and feats and not rim_id:
                rim_id = feats[0].get("id") or ""

        colors = []
        for cat in looks:
            if cat.get("id") != "exteriors":
                continue
            for feat in cat.get("features") or []:
                color_name = feat.get("label") or ""
                color_id = feat.get("id") or ""
                if not (color_name and color_id and lcdv):
                    continue
                # bez felg render 3D nie ma kompletu części — zostaje próbka koloru
                img = (render_url_builder(lcdv, color_id, interior_id, rim_id)
                       if rim_id else (feat.get("visuals") or {}).get("default") or "")
                if img:
                    colors.append({"name": color_name, "image": img})

        # Nadwozie jest częścią tożsamości wersji, nie ozdobnikiem: furgon
        # L1H1 i L3H2 mają ten sam silnik, ale inną cenę — bez tego wpadały
        # do feedu jako dwa wiersze z tym samym vehicle_id
        body_style = (v.get("bodyStyle") or {}).get("label") or ""

        trim = trims.setdefault(trim_label, {"engines": [], "colors": []})
        engine_key = f"{fuel_type}|{engine_label}|{transmission}|{body_style}"
        if engine_key not in {e["key"] for e in trim["engines"]}:
            trim["engines"].append({
                "key": engine_key,
                "fuel_type": fuel_type,
                "engine": engine_label,
                "transmission": transmission,
                "body_style": body_style,
                "price": int(price) if price > 0 else 0,
            })
        known = {c["name"] for c in trim["colors"]}
        for c in colors:
            if c["name"] not in known:
                trim["colors"].append(c)
                known.add(c["name"])
    return trims


def build_rows(make_label, id_prefix, model_label, trims, page_url, lease,
               disclaimer):
    """Trimy jednego modelu -> wiersze feedu (wiersz na trim × silnik × kolor)."""
    rows = []
    model_name = f"{make_label} {model_label}"
    for trim_label, trim in trims.items():
        colors = trim["colors"] or [{"name": "Standard", "image": ""}]
        for engine in trim["engines"]:
            price = engine["price"]
            if not price:
                continue
            full_title = (model_name if trim_label == "Standard"
                          else f"{model_name} {trim_label}")

            if lease:
                offer_type, amount_price = "LEASE", f"{lease} PLN"
                amount_qualifier = "per month"
                tiktok_title = scraper_utils.format_model_title(
                    full_title, f"{lease} PLN")
            else:
                offer_type, amount_price = "CASH", f"{price} PLN"
                amount_qualifier = "Total"
                tiktok_title = f"{full_title} · od {price} PLN"

            for color in colors:
                vid = (f"{id_prefix}-"
                       f"{scraper_utils.generate_stable_id(model_label, length=4)}-"
                       f"{scraper_utils.generate_stable_id(trim_label, length=4)}-"
                       f"{scraper_utils.generate_stable_id(color['name'], length=4)}-"
                       f"{scraper_utils.generate_stable_id(engine['key'], length=5)}")
                rows.append({
                    "vehicle_id": vid,
                    "title": tiktok_title,
                    # skrzynia w opisie, bo bywa jedyną różnicą między dwoma
                    # wierszami tego samego trimu i silnika (i ceny!)
                    "description": " · ".join(
                        p for p in [scraper_utils.with_new_prefix(full_title), engine["engine"],
                                    engine["transmission"], "Sprawdź ofertę!"] if p),
                    "rodzaj": "modelowy",
                    "make": make_label,
                    "model": model_name,
                    "year": scraper_utils.current_year(),
                    "link": page_url,
                    "image_link": color["image"],
                    "exterior_color": color["name"],
                    "additional_image_link": "",
                    "trim": trim_label,
                    "offer_disclaimer": disclaimer,
                    "offer_disclaimer_url": page_url,
                    "price": f"{price} PLN",
                    "offer_type": offer_type,
                    "term_length": "",
                    "offer_term_qualifier": "",
                    "amount_price": amount_price,
                    "amount_percentage": "",
                    "amount_qualifier": amount_qualifier,
                    "downpayment": "",
                    "downpayment_qualifier": "",
                    "emission_disclaimer": "",
                    "emission_disclaimer_url": "",
                    "emission_overlay_disclaimer": "",
                    "emission_image_link": "",
                    "fuel_type": engine["fuel_type"],
                })
    # siatka bezpieczeństwa: odbiorcy feedów odrzucają powtórzone vehicle_id
    return list({r["vehicle_id"]: r for r in rows}.values())

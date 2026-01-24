import requests
import csv
import json
import re
import time
import os
from datetime import datetime

# Konfiguracja
API_URL = "https://salon.alfaromeo.pl/api/offers/list-alfa-romeo.json"
OUTPUT_FILE = os.path.join(os.path.dirname(os.path.dirname(__file__)), "data", "alfa_romeo_inventory.csv")
BASE_URL = "https://salon.alfaromeo.pl/oferta"

BODY_STYLE_MAP = {
    "TONALE": "SUV", "STELVIO": "SUV", "GIULIA": "SEDAN",
    "JUNIOR": "SUV", "JUNIOR ELETTRICA": "SUV", "JUNIOR IBRIDA": "SUV"
}

def get_body_style(model_name):
    m = model_name.upper()
    for k, v in BODY_STYLE_MAP.items():
        if k in m: return v
    return "SUV"

def format_address_json(street, city, region, country, post_code=None):
    addr = {"addr1": street, "city": city, "region": region, "country": country}
    if post_code:
        addr["zip"] = post_code
    return json.dumps(addr, ensure_ascii=False)

def main():
    print(f"Pobieranie listy z {API_URL}...")
    all_offers = []
    try:
        r = requests.get(API_URL, headers={"User-Agent": "Mozilla/5.0"})
        data = r.json()
        count = data['result']['info']['countOfResults']
        per_page = data['result']['info']['offersPerPage']
        total_pages = (count + per_page - 1) // per_page
        for page in range(1, total_pages + 1):
            d = requests.get(f"{API_URL}?page={page}", headers={"User-Agent": "Mozilla/5.0"}).json()
            all_offers.extend(d['result']['list'])
    except Exception as e:
        print(f"Błąd pobierania listy: {e}")
        return

    print(f"Pobrano {len(all_offers)} ofert. Przetwarzanie szczegółów...")
    
    fieldnames = [
        "vehicle_id", "title", "description", "link", "image_link",
        "make", "model", "year", "mileage.value", "mileage.unit",
        "body_style", "exterior_color", "state_of_vehicle",
        "price", "currency", "address", "latitude", "longitude",
        "offer_type", "amount_price", "amount_qualifier", "fuel_type", "transmission", "drivetrain"
    ]

    processed_rows = []
    session = requests.Session()
    session.headers.update({"User-Agent": "Mozilla/5.0"})

    for i, offer in enumerate(all_offers, 1):
        uid = str(offer.get("uid") or offer.get("id"))
        
        if i % 10 == 0:
            print(f"Przetwarzanie {i}/{len(all_offers)}...", end='\r')

        # Domyślne wartości z listy (pobierzemy lepsze ze szczegółów)
        model = offer.get("model", "")
        version = offer.get("version", "")
        
        # Inicjalizacja pól lokalizacji
        street, city, region, post_code = "", "", "", ""
        lat, lon = "", ""

        # Pobieranie szczegółów (kolor + dokładna lokalizacja)
        color = "Standard"
        try:
            detail_url = f"https://salon.alfaromeo.pl/api/offers/offer-alfa-romeo.json?id={uid}"
            r_detail = session.get(detail_url, timeout=10)
            if r_detail.status_code == 200:
                d_json = r_detail.json()
                
                # 1. Kolor
                if "color" in d_json and isinstance(d_json["color"], dict):
                    color = d_json["color"].get("name") or color
                
                # 2. Lokalizacja (Dynamiczna!)
                dealer = d_json.get("dealer", {})
                if dealer:
                    street = dealer.get("street", "")
                    city = dealer.get("city", "")
                    region = dealer.get("region", "")
                    post_code = dealer.get("postCode", "")
                    coords = dealer.get("coordinates", {})
                    if coords:
                        lat = coords.get("latitude", "")
                        lon = coords.get("longitude", "")
        except Exception:
            pass # Fallback na puste lub dane z listy jeśli API padnie

        # Jeśli API szczegółów nie dało miasta, weź z listy
        if not city:
            loc_str = offer.get("localization", "")
            parts = loc_str.split(',')
            city = parts[1].strip() if len(parts) > 1 else parts[0].strip()
            street = city

        # Logika łączenia Model + Wersja
        m_up, v_up = model.upper(), version.upper()
        full_model_name = model if v_up in m_up else f"{model} {version}"

        # Cena
        price_data = offer.get("price", {})
        price_brutto = price_data.get("final", {}).get("brutto") or price_data.get("base", {}).get("brutto")
        if not price_brutto: continue
        
        # Finansowanie
        fin_info = price_data.get("financing_info", {})
        installment = None
        installment_desc = ""
        if fin_info.get("b2b"):
            installment = fin_info["b2b"].get("installment")
            installment_desc = f"RATA: {installment} PLN netto/M-C"
        elif fin_info.get("l101"):
            installment = fin_info["l101"].get("installment")
            installment_desc = f"RATA: {installment} PLN netto/M-C"
        elif fin_info.get("b2c"):
            installment = fin_info["b2c"].get("installment")
            installment_desc = f"RATA: {installment} PLN brutto/M-C"
        
        # Silnik i skrzynia
        eng = offer.get("engineType", "")
        fuel = "Hybrid" if "Hybrid" in eng or "Hybryda" in eng else "Electric" if "Elektryczny" in eng else "Diesel" if "Diesel" in eng else "Gasoline"
        trans = "Manual" if "Manual" in eng else "Automatic"
        drive = "AWD" if any(x in version or x in model or x in eng for x in ["Q4", "Na cztery"]) else "FWD"

        # Opis
        desc = f"{installment_desc}. " if installment_desc else ""
        desc += f"Alfa Romeo {full_model_name}. Lokalizacja: {street}, {city}."

        row = {
            "vehicle_id": uid,
            "title": full_model_name[:40],
            "description": desc[:500].strip(),
            "link": f"{BASE_URL}/{uid}",
            "image_link": offer.get("image"),
            "make": "Alfa Romeo",
            "model": model,
            "year": offer.get("productionYear"),
            "mileage.value": offer.get("mileage") or 0,
            "mileage.unit": "KM",
            "body_style": get_body_style(model),
            "exterior_color": color,
            "state_of_vehicle": "New" if (offer.get("mileage") or 0) < 100 else "Used",
            "price": f"{price_brutto} PLN",
            "currency": "PLN",
            "address": f"{street}, {city}, Polska",
            "latitude": lat,
            "longitude": lon,
            "offer_type": "LEASE",
            "amount_price": f"{installment} PLN" if installment else "",
            "amount_qualifier": "per month" if installment else "",
            "fuel_type": fuel,
            "transmission": trans,
            "drivetrain": drive
        }
        processed_rows.append(row)

    print(f"\nZapisywanie {len(processed_rows)} unikalnych ofert...")
    unique_rows = {r['vehicle_id']: r for r in processed_rows}.values()
    with open(OUTPUT_FILE, 'w', newline='', encoding='utf-8-sig') as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames, extrasaction='ignore')
        writer.writeheader()
        writer.writerows(unique_rows)
    print(f"Zakończono. Plik: {OUTPUT_FILE}")

if __name__ == "__main__": main()
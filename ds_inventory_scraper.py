import requests
import csv
import json
import re
import time
from bs4 import BeautifulSoup

API_URL = "https://sklep.dsautomobiles.pl/wp-json/wp/v2/product"
OUTPUT_FILE = "ds_inventory.csv"

# Mapa modeli (class_list -> ładna nazwa)
MODEL_MAP = {
    "ds-3": "DS 3",
    "ds-4": "DS 4",
    "n4": "N°4", 
    "ds-7": "DS 7",
    "ds-9": "DS 9",
    "n8": "N°8"
}

def clean_html_text(text):
    if not text: return ""
    return re.sub(r'\s+', ' ', text).strip()

def parse_detail_page(url, session):
    """Pobiera stronę produktu i wyciąga cenę, dealera oraz rok produkcji."""
    try:
        r = session.get(url, timeout=10)
        html_content = r.text
        soup = BeautifulSoup(r.content, 'html.parser')
        
        # 1. Cena - Regex (najskuteczniejszy)
        price = ""
        price_match = re.search(r'([\d\s\.]+.d{2}\s*z\ł)', html_content)
        if not price_match:
             price_match = re.search(r'([\d\s\.]+\s*z\ł)', html_content)

        if price_match:
            raw_price = price_match.group(1)
            clean_digits = re.sub(r'[^\d]', '', raw_price)
            if len(clean_digits) > 4:
                price = raw_price.replace(" ", "").replace("zł", "").replace(",00", "").strip() + " PLN"
        
        if not price or "Call" in price:
            price_tag = soup.find("p", class_="price")
            if price_tag:
                ins = price_tag.find("ins")
                price = ins.get_text(strip=True) if ins else price_tag.get_text(strip=True)

        # 2. Dealer / Lokalizacja / Rok produkcji (Precyzyjne wyciąganie z col-4/col-8)
        address_json = "{}"
        dynamic_year = "2025"
        
        cols_4 = soup.find_all("div", class_="col-4")
        extracted_data = {}
        for col in cols_4:
            label_text = col.get_text(strip=True).lower()
            value_div = col.find_next_sibling("div", class_="col-8")
            if value_div:
                value_text = value_div.get_text(strip=True)
                if "adres" in label_text: extracted_data["street"] = value_text
                elif "lokalizacja" in label_text: extracted_data["city"] = value_text
                elif "punkt" in label_text: extracted_data["dealer"] = value_text
                elif "rok produkcji" in label_text: extracted_data["year"] = value_text

        if "city" in extracted_data or "street" in extracted_data:
            addr_dict = {
                "addr1": extracted_data.get("street", extracted_data.get("city", "")),
                "city": extracted_data.get("city", ""),
                "country": "PL"
            }
            if "dealer" in extracted_data:
                 addr_dict["addr1"] = f"{extracted_data['dealer']}, {addr_dict['addr1']}"
            address_json = json.dumps(addr_dict, ensure_ascii=False)
        else:
            cities = ["Warszawa", "Kraków", "Poznań", "Wrocław", "Gdańsk", "Katowice", "Łódź", "Szczecin", "Opole", "Bielsko-Biała"]
            for city in cities:
                if city in html_content:
                    address_json = json.dumps({"addr1": city, "city": city, "country": "PL"}, ensure_ascii=False)
                    break

        if "year" in extracted_data:
            dynamic_year = extracted_data["year"]

        return price, address_json, dynamic_year
    except Exception as e:
        print(f"Błąd parsowania {url}: {e}")
        return "", "{}", "2025"

def main():
    print("Pobieranie listy pojazdów z API sklepu DS...")
    all_products = []
    page = 1
    session = requests.Session()
    session.headers.update({"User-Agent": "Mozilla/5.0"})

    while True:
        try:
            r = session.get(f"{API_URL}?per_page=100&page={page}", timeout=10)
            if r.status_code != 200:
                break
            data = r.json()
            if not data:
                break
            all_products.extend(data)
            print(f"Pobrano stronę {page} ({len(data)} aut)...")
            page += 1
        except Exception as e:
            print(f"Błąd API: {e}")
            break

    print(f"Łącznie znaleziono {len(all_products)} ofert. Pobieranie szczegółów...")

    fieldnames = [
        "vehicle_id", "title", "description", "link", "image_link",
        "make", "model", "year", "mileage.value", "mileage.unit",
        "body_style", "exterior_color", "state_of_vehicle",
        "price", "currency", "address", "latitude", "longitude",
        "offer_type", "amount_price", "amount_qualifier", "fuel_type", "transmission", "drivetrain"
    ]

    processed_rows = []

    for i, product in enumerate(all_products, 1):
        if i % 5 == 0:
            print(f"Przetwarzanie {i}/{len(all_products)}...", end='\r')

        pid = str(product.get("id"))
        link = product.get("link")
        title_raw = product.get("title", {}).get("rendered", "")
        vin = title_raw if len(title_raw) == 17 else f"DS-{pid}"
        
        classes = product.get("class_list", {})
        
        model = "DS Unknown"
        for cls in classes.values():
            if cls.startswith("product_cat-") and cls.replace("product_cat-", "") in MODEL_MAP:
                model = MODEL_MAP[cls.replace("product_cat-", "")]
        
        color = "Standard"
        fuel = "Gasoline"
        trans = "Automatic"
        drive = "FWD"
        trim = ""
        
        for cls in classes.values():
            if cls.startswith("pa_kolor-"):
                color = cls.replace("pa_kolor-", "").replace("-", " ").title()
            elif cls.startswith("pa_typ-paliwa-"):
                f_val = cls.replace("pa_typ-paliwa-", "")
                if "hybryda" in f_val: fuel = "Hybrid"
                elif "elektryczny" in f_val: fuel = "Electric"
                elif "diesel" in f_val: fuel = "Diesel"
            elif cls.startswith("pa_typ-skrzyni-"):
                if "manual" in cls: trans = "Manual"
            elif cls.startswith("pa_poziom-wyposazenia-"):
                trim = cls.replace("pa_poziom-wyposazenia-", "").replace("-", " ").title()

        price, address_raw, dynamic_year = parse_detail_page(link, session)

        desc_api = product.get("yoast_head_json", {}).get("description", "")
        rate_match = re.search(r'(\d[\d\s]+)\s*z\ł', desc_api)
        installment = rate_match.group(1).replace(" ", "") if rate_match else ""
        
        clean_installment = installment.replace(" ", "").replace("PLN", "").strip()
        if not clean_installment:
            continue
        try:
            if int(clean_installment) <= 0:
                continue
        except ValueError:
            continue
        
        amount_price_final = f"{installment} PLN"

        if model == "DS Unknown":
            if "ds-7" in link: model = "DS 7"
            elif "ds-3" in link: model = "DS 3"
            elif "ds-4" in link: model = "DS 4"
            elif "/n4/" in link: model = "N°4"
            elif "ds-9" in link: model = "DS 9"
            elif "/n8/" in link: model = "N°8"

        image = ""
        if "og_image" in product.get("yoast_head_json", {}):
            imgs = product.get("yoast_head_json")["og_image"]
            if imgs:
                image = imgs[0].get("url")

        desc = f"{desc_api[:450]}"

        row = {
            "vehicle_id": vin,
            "title": f"{model} {trim}"[:40],
            "description": desc.strip(),
            "link": link,
            "image_link": image,
            "make": "DS Automobiles",
            "model": model,
            "year": dynamic_year,
            "mileage.value": 0,
            "mileage.unit": "KM",
            "body_style": "SUV" if "7" in model or "3" in model else "Hatchback",
            "exterior_color": color,
            "state_of_vehicle": "New",
            "price": price.replace("&nbsp;", "").strip() if price else "",
            "currency": "PLN",
            "address": address_raw,
            "latitude": "",
            "longitude": "",
            "offer_type": "LEASE",
            "amount_price": amount_price_final,
            "amount_qualifier": "per month",
            "fuel_type": fuel,
            "transmission": trans,
            "drivetrain": drive
        }
        processed_rows.append(row)

    print(f"\nZapisano {len(processed_rows)} ofert.")
    
    with open(OUTPUT_FILE, 'w', newline='', encoding='utf-8-sig') as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames, extrasaction='ignore')
        writer.writeheader()
        writer.writerows(processed_rows)

if __name__ == "__main__": main()
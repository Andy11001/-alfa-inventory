import requests
import json
import os
import time

# Konfiguracja
API_URL = "https://salon.alfaromeo.pl/api/offers/list-alfa-romeo.json"
OUTPUT_FILE = os.path.join(os.path.dirname(os.path.dirname(__file__)), "data", "alfa_codes.json")

def extract_codes():
    print(f"Rozpoczynanie mapowania kodów z {API_URL}...")
    
    # Słowniki na dane
    mappings = {
        "models": {},
        "versions": {},
        "colors": {},
        "interiors": {},
        "trims": {}, # Czasami występuje jako oddzielne pole
        "series": {}
    }
    
    session = requests.Session()
    session.headers.update({"User-Agent": "Mozilla/5.0"})

    # 1. Pobranie listy wszystkich UID
    all_uids = []
    try:
        # Pierwsze zapytanie żeby dostać info o stronach
        r = session.get(API_URL)
        data = r.json()
        count = data['result']['info']['countOfResults']
        per_page = data['result']['info']['offersPerPage']
        total_pages = (count + per_page - 1) // per_page
        
        print(f"Znaleziono {count} ofert na {total_pages} stronach.")

        for page in range(1, total_pages + 1):
            print(f"Pobieranie listy: strona {page}/{total_pages}...")
            r_page = session.get(f"{API_URL}?page={page}")
            d_page = r_page.json()
            for item in d_page['result']['list']:
                uid = str(item.get("uid") or item.get("id"))
                all_uids.append(uid)
    except Exception as e:
        print(f"Błąd podczas pobierania listy: {e}")
        return

    # 2. Iteracja po szczegółach i zbieranie kodów
    print(f"Pobieranie szczegółów dla {len(all_uids)} ofert (to może chwilę potrwać)...")
    
    for i, uid in enumerate(all_uids, 1):
        try:
            detail_url = f"https://salon.alfaromeo.pl/api/offers/offer-alfa-romeo.json?id={uid}"
            r_detail = session.get(detail_url)
            
            if r_detail.status_code != 200:
                continue

            d = r_detail.json()
            
            # --- EKSTRAKCJA MODELI ---
            if "model" in d and isinstance(d["model"], dict):
                code = d["model"].get("code")
                name = d["model"].get("name")
                if code and name:
                    mappings["models"][code] = name

            # --- EKSTRAKCJA WERSJI ---
            if "version" in d and isinstance(d["version"], dict):
                code = d["version"].get("code")
                name = d["version"].get("name") # Często długa nazwa techniczna
                comm_code = d["version"].get("commercialCode")
                
                # Kluczem jest kod wersji, wartością obiekt z nazwą i kodem handlowym
                if code:
                    mappings["versions"][code] = {
                        "name": name,
                        "commercialCode": comm_code
                    }

            # --- EKSTRAKCJA KOLORÓW ---
            if "color" in d and isinstance(d["color"], dict):
                code = d["color"].get("code")
                name = d["color"].get("name")
                if code and name:
                    mappings["colors"][code] = name

            # --- EKSTRAKCJA WNĘTRZ ---
            if "interior" in d and isinstance(d["interior"], dict):
                code = d["interior"].get("code")
                name = d["interior"].get("name")
                if code and name:
                    mappings["interiors"][code] = name

            # --- EKSTRAKCJA SERII ---
            if "series" in d and isinstance(d["series"], dict):
                code = d["series"].get("code")
                if code:
                    mappings["series"][code] = d["series"]

            if i % 10 == 0:
                print(f"Przetworzono {i}/{len(all_uids)}...", end="\r")
            
            # Delikatne opóźnienie
            # time.sleep(0.05)

        except Exception as e:
            print(f"Błąd przy ofercie {uid}: {e}")

    # 3. Zapis do JSON
    print(f"\nZapisywanie bazy kodów do {OUTPUT_FILE}...")
    with open(OUTPUT_FILE, 'w', encoding='utf-8') as f:
        json.dump(mappings, f, indent=2, ensure_ascii=False, sort_keys=True)
    
    print("Gotowe! Zebrano:")
    print(f"- Modele: {len(mappings['models'])}")
    print(f"- Wersje: {len(mappings['versions'])}")
    print(f"- Kolory: {len(mappings['colors'])}")
    print(f"- Wnętrza: {len(mappings['interiors'])}")

if __name__ == "__main__":
    extract_codes()

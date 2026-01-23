# -*- coding: utf-8 -*-
import csv
import sys
from urllib.parse import urlparse

# Konfiguracja pliku do sprawdzenia
FILENAME = "alfa_romeo_feed.csv"

# Pola wymagane (krytyczne dla feedu)
REQUIRED_HEADERS = [
    "vehicle_id", 
    "title", 
    "make", 
    "model", 
    "year", 
    "link", 
    "image_link", 
    "offer_type",
    "amount_price" # Ważne dla ofert leasingowych
]

def is_valid_url(url):
    try:
        result = urlparse(url)
        return all([result.scheme, result.netloc]) and result.scheme in ['http', 'https']
    except:
        return False

def check_csv(filename):
    print(f"--- ROZPOCZYNAM WALIDACJĘ PLIKU: {filename} ---\n")
    
    try:
        with open(filename, mode='r', encoding='utf-8') as f:
            reader = csv.DictReader(f)
            headers = reader.fieldnames
            rows = list(reader)
            
            # 1. Sprawdzenie nagłówków
            print("[1/5] Sprawdzanie nagłówków...")
            missing_headers = [h for h in REQUIRED_HEADERS if h not in headers]
            if missing_headers:
                print(f"❌ BŁĄD: Brakuje wymaganych kolumn: {missing_headers}")
                return False
            print("✅ Nagłówki OK.")

            # 2. Sprawdzenie czy są dane
            print(f"\n[2/5] Sprawdzanie zawartości (znaleziono {len(rows)} wierszy)...")
            if len(rows) == 0:
                print("❌ BŁĄD: Plik CSV jest pusty (poza nagłówkiem)! Scraper nie znalazł żadnych ofert.")
                return False
            print("✅ Plik zawiera dane.")

            # 3. Sprawdzenie unikalności ID i pustych pól
            print("\n[3/5] Analiza wierszy (ID, puste pola, formaty)...")
            seen_ids = set()
            errors = 0
            warnings = 0

            for i, row in enumerate(rows, start=1):
                # Check Vehicle ID
                v_id = row.get("vehicle_id", "").strip()
                if not v_id:
                    print(f"❌ Wiersz {i}: Puste vehicle_id!")
                    errors += 1
                elif v_id in seen_ids:
                    print(f"❌ Wiersz {i}: Zduplikowane vehicle_id: '{v_id}'")
                    errors += 1
                else:
                    seen_ids.add(v_id)

                # Check Required Fields
                for field in REQUIRED_HEADERS:
                    if not row.get(field, "").strip():
                        print(f"❌ Wiersz {i} (ID: {v_id}): Puste pole '{field}'")
                        errors += 1

                # Check URLs
                if not is_valid_url(row.get("link", "")):
                    print(f"❌ Wiersz {i} (ID: {v_id}): Nieprawidłowy link do oferty")
                    errors += 1
                if not is_valid_url(row.get("image_link", "")):
                    print(f"⚠️ Wiersz {i} (ID: {v_id}): Nieprawidłowy link do zdjęcia")
                    warnings += 1

                # Check Price/Rate presence
                price = row.get("amount_price", "")
                if "zł" not in price and "PLN" not in price:
                     print(f"⚠️ Wiersz {i} (ID: {v_id}): Cena '{price}' może nie zawierać waluty.")
                     warnings += 1

            # 4. Podsumowanie
            print("\n--- RAPORT KOŃCOWY ---")
            if errors == 0:
                print("🟢 WALIDACJA POZYTYWNA. Plik gotowy do importu.")
                if warnings > 0:
                    print(f"⚠️ Zwróć uwagę na {warnings} ostrzeżeń powyżej.")
            else:
                print(f"🔴 WALIDACJA NEGATYWNA. Znaleziono {errors} błędów krytycznych.")

    except FileNotFoundError:
        print(f"❌ BŁĄD: Nie znaleziono pliku {filename}. Uruchom najpierw scraper.")
    except Exception as e:
        print(f"❌ BŁĄD KRYTYCZNY: {e}")

if __name__ == "__main__":
    check_csv(FILENAME)
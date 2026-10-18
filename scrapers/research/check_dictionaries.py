import requests
import json
import os

def check_dictionaries():
    base_url = "https://www.alfaromeo.pl/sccf/prod/alfaromeo/publish/data/fccf_mv/PL/pl/6305/1-1_3106555/"
    
    # Znany plik NPE
    npe_url = base_url + "NPE_STANDARD_3123D83_6305.json"
    
    # Zgadywany plik słownika (częsty schemat w FCA)
    dict_url = base_url + "DICT_3123D83_6305.json"
    dict_url_2 = base_url + "DICTIONARY_3123D83_6305.json"
    
    print(f"1. Sprawdzam NPE: {npe_url}")
    try:
        r = requests.get(npe_url)
        if r.status_code == 200:
            print("   ✅ Pobrano NPE. Szukam nazw kolorów...")
            text = r.text
            if "CL-" in text:
                print("   Znaleziono kody CL- w NPE!")
                # Zapisz do analizy
                with open("data/stelvio_npe.json", "w", encoding="utf-8") as f:
                    f.write(text)
            else:
                print("   Brak kodów CL- w NPE.")
        else:
            print(f"   ❌ Błąd: {r.status_code}")
    except Exception as e:
        print(f"   ❌ Wyjątek: {e}")

    print(f"\n2. Sprawdzam zgadywany Słownik: {dict_url}")
    try:
        r = requests.get(dict_url)
        if r.status_code == 200:
            print("   ✅ STRZAŁ W DZIESIĄTKĘ! Pobrano słownik.")
            with open("data/stelvio_dict.json", "w", encoding="utf-8") as f:
                f.write(r.text)
            
            # Wypiszmy próbkę
            data = r.json()
            # Szukamy czegoś co wygląda jak tłumaczenia
            print("   Próbka kluczy:", list(data.keys())[:5])
        else:
             print(f"   ❌ Nie znaleziono ({r.status_code}).")
    except:
        pass

if __name__ == "__main__":
    check_dictionaries()

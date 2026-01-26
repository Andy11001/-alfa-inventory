import requests
import json
import os
import time

# Konfiguracja
SCOPE_URL = "https://www.alfaromeo.pl/sccf/prod/alfaromeo/publish/data/fccf_mv/scope//3123D83.json"
BASE_URL = "https://www.alfaromeo.pl/sccf/prod/alfaromeo/publish/data/fccf_mv"
MARKET_CODE = "3123D83"
OUTPUT_FILE = os.path.join(os.path.dirname(os.path.dirname(__file__)), "data", "alfa_live_colors.json")

def main():
    print(f"Pobieranie SCOPE z {SCOPE_URL}...")
    try:
        r = requests.get(SCOPE_URL, timeout=10)
        r.raise_for_status()
        scope_data = r.json()
    except Exception as e:
        print(f"❌ Błąd pobierania SCOPE: {e}")
        return

    live_colors = {} # klucz: MVSS, wartość: { 'codes': [lista kodów], 'names': {kod: nazwa} }

    com_mods = scope_data.get("comMods", [])
    print(f"Znaleziono {len(com_mods)} modeli w SCOPE.")

    for i, mod in enumerate(com_mods):
        code = mod.get("code")
        nsbpath = mod.get("nsbpath")
        
        if not code or not nsbpath: continue
        
        # Konstrukcja URL do pliku modelu (Commercial Model)
        # URL: BASE + nsbpath + /CM_T5_MARKET_CODE + .json
        # Uwaga na slashe. nsbpath zaczyna się od /.
        
        model_url = f"{BASE_URL}{nsbpath}/CM_T5_{MARKET_CODE}_{code}.json"
        
        print(f"[{i+1}/{len(com_mods)}] Pobieranie danych dla modelu {code}: {model_url}")
        
        try:
            rm = requests.get(model_url, timeout=10)
            if rm.status_code == 404:
                # Czasem URL ma inną strukturę lub model jest stary?
                print(f"   ⚠️ 404 Not Found dla {code}")
                continue
                
            model_data = rm.json()
            
            # Iterujemy po pojazdach (Vehicle) w tym modelu
            vehs = model_data.get("Vehs", [])
            for v in vehs:
                mvss = v.get("Cod") # To jest pełny MVSS np. 83622MF33000
                if not mvss: continue
                
                # Szukamy grupy opcji "CL" (Color)
                opt_groups = v.get("OptGroups", [])
                cl_group = next((g for g in opt_groups if g.get("Cod") == "CL"), None)
                
                if cl_group:
                    valid_codes = []
                    valid_names = {}
                    
                    for opt in cl_group.get("Opts", []):
                        c_code = opt.get("Cod")
                        c_desc = opt.get("Des")
                        if c_code:
                            valid_codes.append(c_code)
                            valid_names[c_code] = c_desc
                    
                    live_colors[mvss] = {
                        "codes": valid_codes,
                        "names": valid_names
                    }
                    # print(f"   -> MVSS {mvss}: {len(valid_codes)} kolorów")
                else:
                    pass
                    # print(f"   -> MVSS {mvss}: Brak grupy CL")

        except Exception as e:
            print(f"   ❌ Błąd przetwarzania modelu {code}: {e}")
            
    # Zapis wyników
    with open(OUTPUT_FILE, 'w', encoding='utf-8') as f:
        json.dump(live_colors, f, indent=4, ensure_ascii=False)
        
    print(f"\n✅ Zapisano mapę kolorów dla {len(live_colors)} wersji MVSS do {OUTPUT_FILE}")

if __name__ == "__main__":
    main()

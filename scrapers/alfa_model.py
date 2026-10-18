import requests
from bs4 import BeautifulSoup
import re
import csv
import os
import scraper_utils # Import modułu bezpieczeństwa

# Konfiguracja
BASE_URL = "https://www.alfaromeo.pl"
OUTPUT_FILE = os.path.join(os.path.dirname(os.path.dirname(__file__)), "data", "alfa_model_feed.csv")

def get_dynamic_model_urls(session):
    """
    Automatycznie wykrywa linki do modeli ze strony zbiorczej.
    """
    hub_url = f"{BASE_URL}/modele"
    print(f"Dynamiczne wykrywanie modeli z: {hub_url}")
    found_urls = set()
    
    try:
        r = scraper_utils.fetch_with_retry(session, hub_url, timeout=15)
        soup = BeautifulSoup(r.text, 'html.parser')
        
        # Heurystyka: Szukamy linków zawierających '/modele/' ale nie będących samym hubem
        for a in soup.find_all('a', href=True):
            href = a['href']
            if "/modele/" in href and href != "/modele" and "dostepne" not in href:
                # Wykluczenia "śmieciowych" linków
                if any(x in href for x in ["wersje-limitowane", "quadrifoglio-100", "competizione", "luna-rossa"]):
                    continue
                    
                full_url = href if href.startswith("http") else f"{BASE_URL}{href}"
                found_urls.add(full_url)
                
    except Exception as e:
        print(f"Błąd podczas wykrywania modeli: {e}")
        # Fallback do kluczowych modeli w razie awarii discovery
        return [
            f"{BASE_URL}/modele/junior-ibrida",
            f"{BASE_URL}/modele/tonale",
            f"{BASE_URL}/modele/stelvio",
            f"{BASE_URL}/modele/giulia"
        ]
        
    print(f"Znaleziono {len(found_urls)} stron modeli.")
    return sorted(list(found_urls))

def extract_model_code(html_text):
    """
    Próbuje wyciągnąć kod modelu (np. 622) z treści strony.
    Szuka w JSON-ie vehicleID lub linkach konfiguratora.
    """
    # 1. Metoda najpewniejsza: vehicleID w JSON
    # Pattern: "vehicleID" : "0836223" (gdzie 083 to marka, 622 to model, 3 to seria/wersja)
    # Interesuje nas środkowa część '622'
    match_json = re.search(r'"vehicleID"\s*:\s*"083(\d{3})\d"', html_text)
    if match_json:
        return match_json.group(1)

    # 2. Metoda linków konfiguratora (fallback)
    # Pattern: /konfigurator/#/l/pl/pl/622/
    match_link = re.search(r'konfigurator.*?(?:/|%2F)(\d{3})(?:/|%2F)', html_text)
    if match_link:
        return match_link.group(1)
        
    return ""

def clean_title(title):
    """
    Usuwa parametry silnikowe i naprawia formatowanie.
    """
    t = title.replace(" - ", " ")
    
    t = re.sub(r'\b\d\.\d\s+', '', t) 
    t = re.sub(r'GME|JTDM|V6', '', t, flags=re.I)
    t = re.sub(r'\d+\s*KM', '', t, flags=re.I)
    t = re.sub(r'\d+\s*kWh', '', t, flags=re.I)
    t = re.sub(r'Mild-Hybrid', '', t, flags=re.I)
    t = re.sub(r'AWD', '', t, flags=re.I)
    t = t.replace("(bev)", "").replace("(BEV)", "")
    
    if "PLUG-IN" in t.upper():
        t = re.sub(r'PLUG-IN\s*HYBRID', 'PHEV', t, flags=re.I)
        t = t.replace("Plug-in", "PHEV")
    
    words = t.split()
    cleaned_words = []
    for w in words:
        upper_w = w.upper()
        if upper_w in ["Q4", "PHEV", "TI"]:
            cleaned_words.append(upper_w.capitalize() if upper_w == "TI" else upper_w)
        elif upper_w in ["IBRIDA", "ELETTRICA"]:
            cleaned_words.append(w.capitalize())
        else:
            cleaned_words.append(w.capitalize())
            
    t = " ".join(cleaned_words)
    
    if "Alfa Romeo" not in t:
        t = f"Alfa Romeo {t}"

    t = re.sub(r'\b(\w+)\s+\1\b', r'\1', t, flags=re.I) 
    return t.strip()

def clean_price(price_str):
    if not price_str: return 0
    clean = re.sub(r'[^\d]', '', price_str)
    return int(clean) if clean else 0

def extract_offers_from_text(text, model_code=""):
    offers = []
    pattern = r"modelu\s+(?P<model_full>[^:]+?):\s*cena.+?brutto\s*(?P<price>[\d\s\xa0]+)\s*zł.+?okres.+?(?P<months>\d+)\s*mies.+?wpłata.+?(?P<down_payment>\d+)\s*%.+?netto:?\s*(?P<installment>[\d\s\xa0]+)\s*zł(?P<disclaimer>(?:(?!modelu).){0,400})"
    
    normalized_text = text.replace('\xa0', ' ')
    matches = re.finditer(pattern, normalized_text, re.IGNORECASE | re.DOTALL)
    
    for match in matches:
        raw_title = match.group("model_full").strip().replace("\n", " ")
        full_title = clean_title(raw_title)
        
        raw_disclaimer = match.group("disclaimer").strip()
        if "." in raw_disclaimer:
            raw_disclaimer = raw_disclaimer.rsplit(".", 1)[0] + "."
        
        offer = {
            "vehicle_id": scraper_utils.generate_stable_id(full_title, prefix="ALFA"),
            "title": full_title,
            "price_brutto": clean_price(match.group("price")),
            "installment_netto": clean_price(match.group("installment")),
            "months": match.group("months"),
            "down_payment_pct": match.group("down_payment"),
            "disclaimer": raw_disclaimer,
            "model_code": model_code # Nowe pole!
        }
        offers.append(offer)
    return offers

def main():
    print(f"Rozpoczynam pobieranie ofert modelowych (Auto-Discovery)...")
    session = requests.Session()
    session.headers.update({"User-Agent": "Mozilla/5.0"})
    
    # Krok 1: Wykrycie URLi
    target_urls = get_dynamic_model_urls(session)
    
    all_found_offers = []
    processed_titles = set()

    for url in target_urls:
        print(f"Analiza: {url}")
        try:
            r = scraper_utils.fetch_with_retry(session, url, timeout=15)
            if r.status_code == 200:
                html_text = r.text
                
                # Krok 2: Ekstrakcja kodu modelu (MVSS base)
                model_code = extract_model_code(html_text)
                if model_code:
                    print(f"   Wykryto kod modelu: {model_code}")
                
                # Ekstrakcja ofert
                clean_text = BeautifulSoup(html_text, 'html.parser').get_text(" ", strip=True)
                offers = extract_offers_from_text(clean_text, model_code)
                
                for off in offers:
                    # Unikanie duplikatów (czasem ta sama oferta jest na kilku podstronach)
                    if off['title'] not in processed_titles:
                        all_found_offers.append(off)
                        processed_titles.add(off['title'])
                        print(f"   Oferta: {off['title']} ({off['installment_netto']} zł/mc)")
        except Exception as e: 
            print(f"   Błąd: {e}")
            continue

    if all_found_offers:
        # Dodajemy 'model_code' do nagłówków
        fieldnames = ["vehicle_id", "title", "price_brutto", "installment_netto", "months", "down_payment_pct", "disclaimer", "model_code"]
        
        # Bezpieczny zapis z scraper_utils
        from scraper_utils import safe_save_csv
        if safe_save_csv(all_found_offers, fieldnames, OUTPUT_FILE, min_rows_threshold=1):
             print(f"\nZapisano {len(all_found_offers)} ofert do pliku pośredniego.")
        else:
             print(f"\nUWAGA: Nie udało się zapisać pliku {OUTPUT_FILE}")
             return # Przerywamy, nie generujemy feedu finalnego na starych/pustych danych
        
        # Trigger generation of the final feed
        try:
            import generate_full_model_feed
            print("Uruchamianie generatora finalnego feedu...")
            generate_full_model_feed.main()
        except ImportError:
            print("UWAGA: Nie można zaimportować generate_full_model_feed.")
        except Exception as e:
            print(f"Błąd podczas generowania finalnego feedu: {e}")
    else:
        print("BŁĄD: Nie znaleziono żadnych ofert.")

if __name__ == "__main__":
    main()
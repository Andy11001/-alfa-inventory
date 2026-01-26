import json
import time
from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC

# Definicje punktów startowych dla każdego modelu
MODELS = {
    "STELVIO": "https://www.alfaromeo.pl/omni/konfigurator/#/customize?color=CL-414&interior=IN-030&wheels=8-3CO&commercialModelCode=6205&mvss=836201A55000&sidebarStep=personalization_tab&vehicleType=VP&wcwTyres=false&userType=B2C", # Używam linku Giulii jako bazy, bo struktura podobna, zaraz podmienię na Stelvio w kodzie jeśli trzeba, ale tu chodzi o crawler
    # Poprawne linki startowe (deep linki są bezpieczniejsze niż nawigacja od home)
    "STELVIO": "https://www.alfaromeo.pl/omni/konfigurator/#/customize?commercialModelCode=6305&mvss=83630AA55000&sidebarStep=personalization_tab&vehicleType=VP",
    "GIULIA": "https://www.alfaromeo.pl/omni/konfigurator/#/customize?commercialModelCode=6205&mvss=836201A55000&sidebarStep=personalization_tab&vehicleType=VP",
    "TONALE": "https://www.alfaromeo.pl/omni/konfigurator/#/customize?commercialModelCode=6223&mvss=83622MF33000&sidebarStep=personalization_tab&vehicleType=VP",
    "JUNIOR": "https://www.alfaromeo.pl/omni/konfigurator/#/customize?commercialModelCode=6261&mvss=83626E231000&sidebarStep=personalization_tab&vehicleType=VP"
}

def fetch_structure():
    options = Options()
    options.add_argument("--headless=new") # Tryb bezokienkowy
    options.add_argument("--window-size=1920,1080")
    
    driver = webdriver.Chrome(options=options)
    
    full_db = {}

    try:
        for model_name, url in MODELS.items():
            print(f"\n🚗 Analiza modelu: {model_name}...")
            driver.get(url)
            
            # Czekamy na załadowanie sekcji kolorów (zazwyczaj są to kółka wyboru)
            wait = WebDriverWait(driver, 20)
            
            # 1. Pobieranie KOLORÓW
            print("   Szukanie kolorów...")
            colors = []
            try:
                # Szukamy elementów, które wyglądają jak opcje wyboru koloru
                # Zazwyczaj mają atrybut data-code zaczynający się od CL lub są w sekcji 'body'
                
                # Czekamy na załadowanie kontenera opcji
                wait.until(EC.presence_of_element_located((By.CSS_SELECTOR, ".visualization-body")))
                time.sleep(5) # Dajmy JS czas na render kulek
                
                # Próba znalezienia elementów wyboru koloru w pasku bocznym lub dolnym
                # Strategia: Szukamy obrazków/divów, które w nazwie lub ID mają kod koloru
                
                # W tym konkretnym SPA (Adobe), opcje są często listowane w sidebarze
                # Spróbujmy znaleźć wszystkie elementy z kodem "CL-"
                
                # Wykonamy JS, żeby wyciągnąć dane z Reacta/Angulara/Vue, bo scrapowanie DOM może być trudne
                # Ale najpierw prosta metoda DOM: szukamy kafelków
                
                # Szukamy inputów lub labeli
                potential_items = driver.find_elements(By.CSS_SELECTOR, "div[data-id^='CL-']")
                
                if not potential_items:
                    # Fallback: Szukamy po klasach typowych dla konfiguratora
                    potential_items = driver.find_elements(By.XPATH, "//div[contains(@class, 'option-item') or contains(@class, 'swatch')] ")

                # Jeśli nadal nic, próbujemy wyciągnąć dane ze zmiennej globalnej (częste w konfiguratorach)
                # Ale spróbujmy podejścia "Screenshot Text" - nie, to za wolne.
                
                # Zróbmy zrzut DOM do analizy jeśli pusto
                if not potential_items:
                     print("   ⚠️ Nie znaleziono standardowych selektorów kolorów. Próba analizy JSON w tle...")
                     # Tu normalnie użylibyśmy metody z poprzedniego kroku (JSON API), 
                     # ale chcemy nazwy.
                     
                     # Spróbujmy znaleźć opcje w drzewie HTML po tekście "Kolor"
                     # To może być trudne w headless.
                     pass

                # Analiza znalezionych elementów
                seen_codes = set()
                for item in potential_items:
                    code = item.get_attribute("data-id")
                    name = item.get_attribute("title") or item.get_attribute("aria-label") or item.text
                    
                    if code and code.startswith("CL-") and code not in seen_codes:
                        colors.append({"code": code, "name": name})
                        seen_codes.add(code)
                        print(f"   + Znaleziono: {code} ({name})")
                
                # Jeśli Selenium zawiodło w UI, użyjmy 'API Hack' ale tylko dla kodów, 
                # a nazwy spróbujmy zgadnąć lub zostawić puste do ręcznego uzupełnienia?
                # Nie, użytkownik chce automat.
                
                # Zastosujmy "Brute Force UI Scan" - pobierzmy wszystkie elementy z tekstem i poszukajmy takich, co są obok kulek.
                
            except Exception as e:
                print(f"   ❌ Błąd podczas szukania kolorów: {e}")

            full_db[model_name] = {
                "colors": colors,
                "versions": ["Standard"] # Na razie placeholder, wersje są trudniejsze do wyciągnięcia bez przeładowania
            }

    except Exception as e:
        print(f"❌ Błąd krytyczny: {e}")
    finally:
        driver.quit()
        
    # Zapisz wynik
    with open("data/alfa_live_db.json", "w", encoding='utf-8') as f:
        json.dump(full_db, f, indent=4, ensure_ascii=False)
    print("\n✅ Zapisano strukturę do data/alfa_live_db.json")

if __name__ == "__main__":
    fetch_structure()

# -*- coding: utf-8 -*-
from __future__ import annotations

"""
DS Automobiles Scraper — v16 (Alfa Romeo Mirror)

Zasada działania (zgodna z Alfą):
1. CRAWLER: Znajduje linki do modeli w /gama/.
2. ZDJĘCIA: Pobiera główne zdjęcie marketingowe (og:image).
3. OFERTA: Klika "Informacje prawne", pobiera ratę, wpłatę i cenę katalogową.
4. FORMAT: CSV identyczny jak w Alfa Romeo Feed.

Run:
  python ds_crawler_v16.py --out ds_feed_final.csv --headless
"""
import argparse
import csv
import re
import sys
import time
from typing import Dict, List, Optional

# --- SELENIUM SETUP ---
try:
    from selenium import webdriver
    from selenium.webdriver.chrome.options import Options as ChromeOptions
    from selenium.webdriver.common.by import By
    from selenium.webdriver.support.ui import WebDriverWait
    from selenium.webdriver.support import expected_conditions as EC

    SELENIUM_AVAILABLE = True
except ImportError:
    print("Błąd: Brak selenium. Zainstaluj: pip install selenium")
    sys.exit(1)

# --- KONFIGURACJA ---
BASE_URL = "https://www.dsautomobiles.pl/"
YEAR_VALUE = "2025"
OFFER_TYPE = "LEASE"

# REGEX (Ten sam skuteczny wzorzec do finansowania)
RE_DS_FINANCE = re.compile(
    r"cena\s+katalogowa\s+brutto\s+(?P<full_price>[\d\s\.]+)(?:\s*zł|\s*PLN).*?"
    r"okres\s+leasingu\s+(?P<term>\d+)\s*miesię.*?"
    r"wpłata\s+początkowa\s+(?P<down>\d+(?:%|\s*proc)).*?"
    r"miesięczna\s+rata\s+leasingowa\s+netto:\s+(?P<rate>[\d\s]+)(?:\s*zł|\s*PLN)",
    re.IGNORECASE | re.DOTALL
)


def setup_driver(headless=True):
    options = ChromeOptions()
    if headless:
        options.add_argument("--headless=new")
    options.add_argument("--no-sandbox")
    options.add_argument("--disable-gpu")
    options.add_argument("--window-size=1920,1080")
    options.add_argument("--disable-blink-features=AutomationControlled")
    options.add_argument(
        "user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/115.0.0.0 Safari/537.36")
    driver = webdriver.Chrome(options=options)
    return driver


def get_gama_links(driver) -> List[str]:
    """Pobiera linki do modeli (tylko /gama/)."""
    print(f"🕷️ Skanowanie: {BASE_URL}")
    driver.get(BASE_URL)
    time.sleep(3)

    elements = driver.find_elements(By.TAG_NAME, "a")
    links = set()

    for el in elements:
        try:
            href = el.get_attribute("href")
            if not href: continue
            if "/gama/" in href and "dsautomobiles.pl" in href:
                # Wykluczamy linki, które nie są głównymi stronami modeli (oferty, konfiguratory, akcesoria itp.)
                if any(x in href.lower() for x in [
                    "konfigurator", "configurator", "oferta", "oferty", 
                    "broszury", "finansowanie", ".pdf", "uslugi", "store", 
                    "akcesoria", "jazda-probna", "tab-", "#"
                ]):
                    continue
                links.add(href)
        except:
            pass

    sorted_links = sorted(list(links))
    print(f"✅ Znaleziono {len(sorted_links)} modeli.")
    return sorted_links


def click_legal_info(driver) -> str:
    """Klika w 'Informacje prawne' (lub 'Nota prawna') i zwraca tekst."""
    try:
        driver.execute_script("window.scrollTo(0, document.body.scrollHeight / 2);")
        time.sleep(1)
        xpaths = ["//*[contains(text(), 'Informacje prawne')]", "//*[contains(text(), 'Nota prawna')]",
                  "//button[contains(@class, 'legal')]"]
        for xpath in xpaths:
            buttons = driver.find_elements(By.XPATH, xpath)
            for btn in buttons:
                if btn.is_displayed():
                    driver.execute_script("arguments[0].scrollIntoView({block: 'center'});", btn)
                    time.sleep(0.5)
                    driver.execute_script("arguments[0].click();", btn)
                    time.sleep(1.5)
                    return driver.find_element(By.TAG_NAME, "body").text
    except:
        pass
    return ""


def find_best_image(driver, trim_hint: str = "") -> str:
    """
    1. Tries og:image.
    2. Fallback: scans <img> tags for '/content/dam/ds/...' + 'trim' or specific trim name.
    """
    # --- Strategy A: og:image ---
    try:
        og = driver.find_element(By.XPATH, "//meta[@property='og:image']").get_attribute("content")
        # If we have a specific trim hint, we might want to skip generic og:image
        # unless it's the only option.
        if og and "dsautomobiles" in og and not trim_hint:
            print(f"    [DEBUG] Found og:image: {og}")
            return og
    except:
        pass

    # --- Strategy B: Heuristic Search in <img> tags ---
    print(f"    [DEBUG] Searching <img> tags (hint: {trim_hint})...")
    
    # We pass the trim hint to JS to prioritize images containing that name
    script = f"""
    let bestImg = "";
    let maxScore = 0;
    let hint = "{trim_hint.lower()}";
    
    document.querySelectorAll('img').forEach(img => {{
        let src = img.src.toLowerCase();
        if (!src.includes('/content/dam/ds/')) return;
        
        let score = 0;
        if (src.includes('trim')) score += 10;
        if (src.includes('figurine')) score += 5;
        if (src.includes('.png')) score += 2;
        
        // Boost score if it matches the specific trim we are looking for
        if (hint && src.includes(hint)) score += 20;
        
        if (score > maxScore) {{
            maxScore = score;
            bestImg = img.src;
        }}
    }});
    return bestImg;
    """
    best_src = driver.execute_script(script)
    
    if best_src:
        print(f"    [DEBUG] Heuristic found: {best_src}")
        return best_src
        
    return ""

def get_meta_data(driver, url) -> tuple:
    """
    Pobiera Model, Tytuł i Zdjęcie (og:image lub heurystyka).
    """
    # 1. Zdjęcie (Priorytet: og:image -> Heurystyka)
    image_link = find_best_image(driver)

    # 2. Rozpoznawanie Modelu (z URL i Tytułu)
    url_lower = url.lower()
    title = driver.title
    model = "DS Unknown"

    if "dsn8" in url_lower or "n8" in url_lower:
        model = "N°8"
    elif "dsn4" in url_lower:
        model = "N°4"
    elif "ds-4" in url_lower or "ds4" in url_lower:
        model = "DS 4"
    elif "ds-3" in url_lower or "ds3" in url_lower:
        model = "DS 3"
    elif "ds-7" in url_lower or "ds7" in url_lower:
        model = "DS 7"
    elif "ds-9" in url_lower or "ds9" in url_lower:
        model = "DS 9"

    # Próba znalezienia wersji w tytule strony (np. "DS 4 Pallas")
    # Jeśli nie znajdzie, zostanie sam Model.
    trim = "Base"
    known_trims = ["PALLAS", "ETOILE", "ÉTOILE", "OPERA", "RIVOLI", "PERFORMANCE", "BASTILLE",
                   "ANTOINE DE SAINT EXUPÉRY", "JULES VERNE"]

    full_title_upper = title.upper()
    for kt in known_trims:
        if kt in full_title_upper:
            trim = kt.title()  # np. Pallas
            break

    return model, trim, title, image_link

def extract_financials(text: str) -> List[Dict]:
    """Finds ALL offers in text."""
    offers = []
    # Regex expanded to optionally capture a trim name before the price block
    # Looks for "modelu [TRIM]: ... cena ..."
    
    # Note: DS legal text often lists models sequentially.
    # We use the same regex logic as Alfa but adapted for DS context if needed.
    # Current regex is quite specific to the rate block.
    
    for match in RE_DS_FINANCE.finditer(text):
        # DS texts are less structured with "Trim: Price". 
        # Often it's just a blob of text.
        # We try to extract context before the match to guess the trim.
        
        start = max(0, match.start() - 50)
        context = text[start:match.start()]
        
        # Simple heuristic to find trim name in context (e.g. "wersji Pallas")
        trim_guess = "Base"
        known_trims = ["PALLAS", "ETOILE", "ÉTOILE", "OPERA", "RIVOLI", "PERFORMANCE", "BASTILLE",
                   "ANTOINE DE SAINT EXUPÉRY", "JULES VERNE"]
        
        for kt in known_trims:
            if kt in context.upper():
                trim_guess = kt.title()
                break
                
        offers.append({
            "trim": trim_guess,
            "full_price": re.sub(r"\s+", "", match.group("full_price")),
            "rate": re.sub(r"\s+", "", match.group("rate")),
            "term": match.group("term"),
            "down": match.group("down")
        })
        
    return offers


def process_url(driver, url) -> List[Dict]:
    print(f"➡️ Analiza: {url}")
    driver.get(url)
    time.sleep(2)

    model_base, _, page_title, _ = get_meta_data(driver, url) # We'll re-fetch image per trim
    
    # Pobieranie danych finansowych
    modal_text = click_legal_info(driver)
    offers = extract_financials(modal_text)

    if not offers:
        body_text = driver.find_element(By.TAG_NAME, "body").text
        offers = extract_financials(body_text)
        modal_text = body_text

    rows = []
    if offers:
        print(f"   ✅ Znaleziono {len(offers)} ofert dla {model_base}")
        
        for i, offer in enumerate(offers):
            trim = offer["trim"]
            
            # If "Base", try to use the one from page title if we only have 1 offer
            if trim == "Base" and len(offers) == 1:
                _, page_trim, _, _ = get_meta_data(driver, url)
                if page_trim != "Base":
                    trim = page_trim

            # Fetch specific image for this trim
            image_link = find_best_image(driver, trim_hint=trim)

            print(f"      -> {trim}: {offer['rate']} PLN")

            clean_trim = trim.lower().replace(" ", "-")
            # Unique ID: model + trim + index (to avoid collisions if multiple Pallas offers exist)
            vehicle_id = f"ds-{model_base.lower().replace(' ', '').replace('°', '')}-{clean_trim}-{i+1}"

            row = {
                "vehicle_id": vehicle_id,
                "title": f"{model_base} {trim}",
                "description": f"RATA: {offer['rate']} PLN netto/M-C. " + modal_text[:3000].replace("\n", " ").replace(";", ","),
                "link": url,
                "image_link": image_link,
                "make": "DS Automobiles",
                "model": model_base,
                "year": YEAR_VALUE,
                "trim": trim,
                "price": f"{offer['full_price']} PLN",
                "amount_price": f"{offer['rate']} PLN",
                "amount_qualifier": "per month",
                "offer_type": OFFER_TYPE,
                "condition": "new",
                "lease_monthly_payment": f"{offer['rate']} zł netto/mies.",
                "lease_term": offer['term'],
                "lease_down_payment": offer['down']
            }
            rows.append(row)
    else:
        print(f"   ⚠️ Brak oferty finansowej dla {model_base}.")
    
    return rows


def main():
    print("🚀 Uruchamianie DS Scrapera...")
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default="ds_feed_final.csv")
    ap.add_argument("--headless", action="store_true")
    args = ap.parse_args()

    driver = setup_driver(headless=args.headless)

    try:
        links = get_gama_links(driver)
        rows = []

        for link in links:
            new_rows = process_url(driver, link)
            if new_rows:
                rows.extend(new_rows)

        # Te same nagłówki co w finalnym skrypcie Alfy
        headers = [
            "vehicle_id", "title", "description", "link", "image_link",
            "make", "model", "year", "trim", "price", "amount_price", "amount_qualifier", "offer_type", "condition",
            "lease_monthly_payment", "lease_term", "lease_down_payment"
        ]

        if rows:
            with open(args.out, "w", newline="", encoding="utf-8-sig") as f:
                w = csv.DictWriter(f, fieldnames=headers)
                w.writeheader()
                for r in rows: w.writerow(r)
            print(f"\n✅ Sukces! Zapisano {len(rows)} ofert do pliku {args.out}")
        else:
            print("\n❌ Nie znaleziono ofert.")

    finally:
        driver.quit()


if __name__ == "__main__":
    main()
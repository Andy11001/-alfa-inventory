# -*- coding: utf-8 -*-
from __future__ import annotations

"""
Alfa Romeo feed scraper (PL) — v6 (Final)

Changes in v6:
• FIX: Auto-sorts trim patterns by length (descending) to prevent partial matching 
  (e.g., ensuring "Ibrida Speciale" is matched before "Ibrida").
• FIX: Guarantees UNIQUE vehicle_ids. If a duplicate ID is generated (e.g., same trim listed twice),
  it appends a suffix (e.g., -2, -3).
• Logic: Uses disclaimer parsing as the source of truth.

Run:
  python alfa_romeo_feed_scraper_v6.py --out alfa_romeo_feed.csv [--use-selenium] [--headless]
"""
import argparse
import csv
import json
import re
import sys
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, List, Optional, Tuple

import requests
from bs4 import BeautifulSoup

SELENIUM_AVAILABLE = False
try:
    from selenium import webdriver  # type: ignore
    from selenium.webdriver.chrome.options import Options as ChromeOptions  # type: ignore
    from selenium.webdriver.common.by import By  # type: ignore
    from selenium.webdriver.support.ui import WebDriverWait  # type: ignore
    from selenium.webdriver.support import expected_conditions as EC  # type: ignore

    SELENIUM_AVAILABLE = True
except Exception:
    SELENIUM_AVAILABLE = False


@dataclass
class ModelConfig:
    key: str
    model: str
    url: str
    image_link: str
    title_base: str
    trim_patterns: List[str]


DEFAULT_MODELS: List[ModelConfig] = [
    ModelConfig(
        key="junior-ibrida",
        model="Junior",
        url="https://www.alfaromeo.pl/modele/junior-ibrida",
        image_link="https://www.alfaromeo.pl/content/dam/alfa/cross/junior-ibrida/figurini/AR_ALFAROMEOJUNIOR_MHEV_MY24_figurini_speciale.png.png",
        title_base="Alfa Romeo Junior",
        # Added distinct names to avoid overlap
        trim_patterns=[
            "Ibrida Q4 Sport Speciale", "Ibrida Sport Speciale", 
            "Ibrida Q4 Sprint", "Ibrida Sprint", 
            "Ibrida Q4 TI", "Ibrida TI", 
            "Ibrida Speciale", "Speciale", 
            "Sprint", "Ibrida"
        ],
    ),
    ModelConfig(
        key="junior-elettrica",
        model="Junior",
        url="https://www.alfaromeo.pl/modele/junior-elettrica",
        image_link="https://www.alfaromeo.pl/content/dam/alfa/cross/milano-elettrica/figurini/AR-Home-Trim-Junior-Elettrica.png",
        title_base="Alfa Romeo Junior",
        trim_patterns=["Elettrica Speciale", "Elettrica Sprint", "Elettrica TI", "Elettrica Veloce", "Veloce",
                       "Speciale", "Sprint", "Elettrica"],
    ),
    ModelConfig(
        key="tonale",
        model="Tonale",
        url="https://www.alfaromeo.pl/modele/new-tonale",
        image_link="https://www.alfaromeo.pl/content/dam/alfa/cross/tonale-mp/new-version-2025/figurines/AR-Tonale_MHEV-MCA_Base_Ibrida.png",
        title_base="Alfa Romeo Tonale",
        trim_patterns=["Sport Speciale", "Edizione Speciale", "Tributo Italiano", "Sprint", "Veloce", "TI", "Tonale"],
    ),
    ModelConfig(
        key="tonale-plug-in",
        model="Tonale Plug-In",
        url="https://www.alfaromeo.pl/modele/tonale-plug-in-hybrid",
        image_link="https://www.alfaromeo.pl/content/dam/alfa/cross/tonale-plug-in-hybrid/new-version-december/figurines/AR-Tonale_MCA_Base_Plug_in.png",
        title_base="Alfa Romeo Tonale Plug-In",
        trim_patterns=["Sport Speciale", "Edizione Speciale", "Tributo Italiano", "Sprint", "Veloce", "TI"],
    ),
    ModelConfig(
        key="giulia",
        model="Giulia",
        url="https://www.alfaromeo.pl/modele/giulia",
        image_link="https://www.alfaromeo.pl/content/dam/alfa/cross/giulia/white-label-update/figurini/AR-GIULIA-MY24-580X344-TRIM-HP-SPRINT.png",
        title_base="Alfa Romeo Giulia",
        trim_patterns=["Tributo Italiano", "Sprint", "Veloce", "Intensa", "Quadrifoglio"],
    ),
    ModelConfig(
        key="stelvio",
        model="Stelvio",
        url="https://www.alfaromeo.pl/modele/stelvio",
        image_link="https://www.alfaromeo.pl/content/dam/alfa/cross/stelvio/white-label-update/figurines/AR-STELVIO-MY24-580X344-TRIM_SPRINT.png",
        title_base="Alfa Romeo Stelvio",
        trim_patterns=["Tributo Italiano", "Sprint", "Veloce", "Intensa", "Quadrifoglio"],
    ),
]

YEAR_VALUE = "2026"
OFFER_TYPE_VALUE = "LEASE"
AMOUNT_QUALIFIER_VALUE = "per month"
GENERIC_OFFER_DISCLAIMER = (
    "Cena katalogowa i/lub warunki finansowania zgodnie z informacją na stronie Alfa Romeo PL. "
    "Dane mają charakter informacyjny i mogą ulec zmianie; szczegóły i ograniczenia oferty dostępne u dealerów."
)

# Regex matches: "...modelu [MODEL] [ENGINE] - [TRIM]: ... okres leasingu [TERM] ... wpłata [DOWN] ... rata [PRICE]"
RE_DISCLAIMER_BLOCK = re.compile(
    r"Założenia przyjęte do kalkulacji modelu.*?(?:-|–)\s*(?P<trim>[^:]+?):.*?"
    r"okres leasingu\s+(?P<term>\d+)\s*mies.*?"
    r"wpłata początkowa\s+(?P<down>\d+(?:%|\s*proc)).*?"
    r"rata leasingowa netto:\s+(?P<price>[\d\s]+)(?:\s*zł)?",
    re.IGNORECASE | re.DOTALL
)


def get_html(url: str, use_selenium: bool = False, headless: bool = True, timeout: int = 20) -> str:
    if not use_selenium:
        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/121 Safari/537.36"}
        r = requests.get(url, headers=headers, timeout=timeout)
        r.raise_for_status()
        return r.text
    if use_selenium and not SELENIUM_AVAILABLE:
        raise RuntimeError("--use-selenium specified but Selenium is not installed.")
    options = ChromeOptions()
    if headless:
        options.add_argument("--headless=new")
    options.add_argument("--no-sandbox")
    options.add_argument("--disable-gpu")
    driver = webdriver.Chrome(options=options)
    try:
        driver.get(url)
        WebDriverWait(driver, timeout).until(EC.presence_of_element_located((By.TAG_NAME, "body")))
        time.sleep(2)
        return driver.page_source
    finally:
        driver.quit()


def find_best_image(html: str) -> Optional[str]:
    """
    1. Tries og:image.
    2. Fallback: scans <img> tags for '/content/dam/alfa/...' + 'figurini'/'figurines'/'trim'.
    """
    soup = BeautifulSoup(html, "lxml")
    
    # --- Strategy A: og:image ---
    og_image = soup.find("meta", property="og:image")
    if og_image and og_image.get("content"):
        content = og_image.get("content").strip()
        # Reject generic root/domain images
        if content not in ["/", "https://www.alfaromeo.pl", "https://www.alfaromeo.pl/"]:
            if content.startswith("/"):
                return f"https://www.alfaromeo.pl{content}"
            return content

    # --- Strategy B: Heuristic Search in <img> tags ---
    # We look for src containing "/content/dam/alfa/" AND ("figurini" OR "figurines" OR "trim")
    print("    [DEBUG] og:image failed. Searching <img> tags...")
    
    candidates = []
    for img in soup.find_all("img"):
        src = img.get("src")
        if not src:
            continue
            
        if "/content/dam/alfa/" in src and (".png" in src or ".jpg" in src):
            # Check for high-value keywords
            score = 0
            if "figurini" in src or "figurines" in src:
                score += 5
            if "trim" in src:
                score += 3
            if "mhev" in src or "phev" in src:
                score += 1
            
            # If it looks like a car render
            if score > 0:
                candidates.append((score, src))

    if candidates:
        # Sort by score descending
        candidates.sort(key=lambda x: x[0], reverse=True)
        best_src = candidates[0][1]
        print(f"    [DEBUG] Heuristic found: {best_src}")
        
        if best_src.startswith("/"):
            return f"https://www.alfaromeo.pl{best_src}"
        return best_src

    return None


def extract_disclaimer(html: str) -> str:
    """
    Extracts the legal/financing disclaimer paragraph.
    Captures text until legal footer to ensure all trims are found.
    """
    MAX_LEN = 3000
    soup = BeautifulSoup(html, "lxml")

    for script in soup(["script", "style", "noscript"]):
        script.decompose()

    text = soup.get_text("\n", strip=True)
    text = re.sub(r"[\t\x0b\r]+", " ", text)

    # 1. Locate start of the financing block
    m_offer = re.search(r"(?:\*+\s*)?Oferta\s+abonamentu[\s\S]{0,4000}", text, re.I)

    parts: List[str] = []

    if m_offer:
        chunk = m_offer.group(0)

        # 2. Locate end of the financing block
        stop_markers = [
            r"Niniejsza informacja nie stanowi oferty",
            r"Szczegóły znajdą Państwo",
            r"Zgoda na udzielenie leasingu",
            r"Rzeczywisty wygląd i cechy pojazdu"
        ]

        min_stop_idx = len(chunk)
        found_stop = False

        for marker in stop_markers:
            m_stop = re.search(marker, chunk, re.I)
            if m_stop:
                min_stop_idx = min(min_stop_idx, m_stop.start())
                found_stop = True

        if found_stop:
            # Keep a bit of context or cut cleanly
            chunk = chunk[:min_stop_idx + 200]

        clean_chunk = re.sub(r"\s+", " ", chunk).strip()
        parts.append(clean_chunk)
    else:
        # Fallback
        m_legal = re.search(r"(?:\*+\s*)?Niniejsza informacja[\s\S]{0,1000}", text, re.I)
        if m_legal:
            parts.append(re.sub(r"\s+", " ", m_legal.group(0)).strip())

    if parts:
        joined = " \u2022 ".join(parts)
        return (joined[:MAX_LEN] + ("…" if len(joined) > MAX_LEN else ""))

    return GENERIC_OFFER_DISCLAIMER


def parse_rates_from_disclaimer(disclaimer_text: str) -> List[Dict[str, str]]:
    """
    Parses the disclaimer text to extract ALL financing details found.
    Returns a list of dicts.
    """
    found_rates = []
    for match in RE_DISCLAIMER_BLOCK.finditer(disclaimer_text):
        raw_trim = match.group("trim").strip()
        term = match.group("term")
        down = match.group("down")
        price_raw = match.group("price")

        price_clean = re.sub(r"\s+", "", price_raw)

        found_rates.append({
            "trim_raw": raw_trim,
            "monthly": f"{price_clean} zł netto/mies.",
            "term": term,
            "down": down
        })
    return found_rates


def discover_trims_and_rates(
        model: ModelConfig,
        disclaimer_text: str
) -> List[Tuple[str, str, str, str]]:
    # Sort patterns by length (Longest first) to avoid substring mismatch
    # e.g. "Ibrida Speciale" checked before "Ibrida"
    sorted_patterns = sorted(model.trim_patterns, key=len, reverse=True)

    parsed_rates = parse_rates_from_disclaimer(disclaimer_text)

    results: List[Tuple[str, str, str, str]] = []

    for rate in parsed_rates:
        raw_trim = rate["trim_raw"].upper()
        matched_trim_name = None

        for pattern in sorted_patterns:
            if pattern.upper() in raw_trim:
                matched_trim_name = pattern
                break

        if matched_trim_name:
            results.append((matched_trim_name, rate["monthly"], rate["term"], rate["down"]))

    return results


def slugify(*parts: str) -> str:
    s = "-".join(p.strip().lower() for p in parts if p and p.strip())
    s = re.sub(r"[^a-z0-9\-]+", "-", s)
    s = re.sub(r"-+", "-", s).strip("-")
    return s


CSV_COLUMNS = [
    "vehicle_id", "title", "description", "make", "model", "year", "link", "image_link",
    "exterior_color", "additional_image_link", "trim", "offer_disclaimer", "offer_disclaimer_url",
    "offer_type", "term_length", "offer_term_qualifier", "amount_price", "amount_percentage", "amount_qualifier",
    "downpayment", "downpayment_qualifier", "emission_disclaimer", "emission_disclaimer_url",
    "emission_overlay_disclaimer", "emission_image_link"
]


def build_rows(models: List[ModelConfig], use_selenium: bool, headless: bool) -> List[Dict[str, str]]:
    rows: List[Dict[str, str]] = []

    # Global tracker for IDs to prevent total duplicates across file (though usually per model is enough)
    # But here we track globally to be safe.
    global_seen_ids: Dict[str, int] = {}

    for mc in models:
        print(f"Processing: {mc.model} ({mc.url})")
        try:
            html = get_html(mc.url, use_selenium=use_selenium, headless=headless)
            
            # Dynamic Image Fetching
            dynamic_image = find_best_image(html)
            final_image_link = dynamic_image if dynamic_image else ""
            if dynamic_image:
                print(f"  + Dynamic Image Found: {dynamic_image}")
            else:
                print(f"  ⚠️ Warning: No dynamic image found for {mc.model}")
            
            disclaimer = extract_disclaimer(html)
            trim_info = discover_trims_and_rates(mc, disclaimer)

            if not trim_info:
                print(f"  Warning: No financing details found in disclaimer for {mc.model}")

            for (trim, monthly, term, down) in trim_info:
                print(f"  + Found: {trim} - {monthly}")

                # BASE ID GENERATION: model + trim
                base_id = slugify("alfa", mc.model, trim)

                # DUPLICATE PROTECTION
                # If we have "Junior Ibrida" twice, the second one becomes "alfa-junior-ibrida-2"
                if base_id in global_seen_ids:
                    global_seen_ids[base_id] += 1
                    vehicle_id = f"{base_id}-{global_seen_ids[base_id]}"
                else:
                    global_seen_ids[base_id] = 1
                    vehicle_id = base_id

                title = f"{mc.title_base} {trim}" if trim.lower() != "tonale" else mc.title_base
                
                # Format installment for description
                # monthly is already "XXXX zł netto/mies."
                inst_val = monthly.replace(" zł netto/mies.", "")
                installment_desc = f"RATA: {inst_val} PLN netto/M-C"

                row = {
                    "vehicle_id": vehicle_id,
                    "title": title,
                    "description": f"{installment_desc}. {mc.title_base} {trim}. {disclaimer[:500]}...",
                    "make": "Alfa Romeo",
                    "model": mc.model,
                    "year": YEAR_VALUE,
                    "link": mc.url,
                    "image_link": final_image_link,
                    "exterior_color": "",
                    "additional_image_link": "",
                    "trim": trim,
                    "offer_disclaimer": disclaimer,
                    "offer_disclaimer_url": mc.url,
                    "offer_type": OFFER_TYPE_VALUE,
                    "term_length": term,
                    "offer_term_qualifier": "months",
                    "amount_price": f"{inst_val} PLN",
                    "amount_percentage": "",
                    "amount_qualifier": AMOUNT_QUALIFIER_VALUE,
                    "downpayment": down,
                    "downpayment_qualifier": "percentage",
                    "emission_disclaimer": "",
                    "emission_disclaimer_url": "",
                    "emission_overlay_disclaimer": "",
                    "emission_image_link": "",
                }
                rows.append(row)
        except Exception as e:
            print(f"Error processing {mc.model}: {e}", file=sys.stderr)

    return rows


def main():
    ap = argparse.ArgumentParser(description="Build Alfa Romeo PL feed CSV (Strict Disclaimer Mode v6 - Unique IDs).")
    ap.add_argument("--out", default="alfa_romeo_feed.csv", help="Output CSV path")
    ap.add_argument("--use-selenium", action="store_true", help="Render pages with Selenium")
    ap.add_argument("--headless", action="store_true", help="Run Selenium in headless mode")
    ap.add_argument("--models-json", help="Optional JSON file to override DEFAULT_MODELS")
    args = ap.parse_args()

    models = DEFAULT_MODELS
    if args.models_json:
        p = Path(args.models_json)
        if not p.exists():
            print(f"Config file not found: {p}", file=sys.stderr)
            sys.exit(2)
        data = json.loads(p.read_text(encoding="utf-8"))
        models = [ModelConfig(**m) for m in data]

    if args.use_selenium and not SELENIUM_AVAILABLE:
        print("Selenium not available. Install selenium and a Chrome/Chromium driver.", file=sys.stderr)
        sys.exit(3)

    rows = build_rows(models, use_selenium=args.use_selenium, headless=args.headless)

    out_path = Path(args.out)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    with out_path.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=CSV_COLUMNS)
        writer.writeheader()
        for r in rows:
            writer.writerow(r)
    print(f"Written {len(rows)} rows to {out_path}")


if __name__ == "__main__":
    main()
# Project Rules & Guidelines

## 1. Project Structure & Architecture
The project is organized into a modular structure to separate logic, data, and the user interface.

- **Root Directory:** Contains the main controller (`dashboard.py`), automation scripts, and configuration.
- **`scrapers/`:** Contains all scraping and processing logic.
  - `alfa_inventory.py`: Scrapes actual stock/inventory from `salon.alfaromeo.pl`.
  - `ds_inventory.py`: Scrapes actual stock/inventory from `sklep.dsautomobiles.pl`.
  - `alfa_model.py`: Pobiera surowe oferty (ceny i raty) ze stron modelowych Alfy Romeo.
  - `fetch_live_colors.py`: Pobiera oficjalne konfiguracje (dostępne kolory) bezpośrednio z API JSON Alfy Romeo (SCCF).
  - `generate_full_model_feed.py`: Główny procesor tworzący finalną macierz (Model x Wersja x Kolor) z poprawnym mapowaniem MVSS.
  - `ds_model.py`: Dynamic scraper for DS Automobiles (Models, Prices, Images). Handles new models like N°4 and N°8.
  - `image_processor.py`: Downloads, resizes, and standardizes vehicle images (adds white background + frame).
  - `validator.py`: Centralized script to validate integrity of all CSV outputs.
- **`data/`:** The **ONLY** allowed destination for output files.
  - All scrapers must save their `.csv`, `.json`, or image files here using absolute paths.
  - `data/images/`: Stores locally processed vehicle images.
- **`templates/`:** Contains the HTML frontend (`index.html`) for the dashboard.
- **`.github/workflows/`:** CI/CD configuration for automated daily scraping.

## 2. Operational Workflow
The project supports two modes of operation:

### A. Manual (Dashboard)
- **Primary Interface:** Run `start_dashboard.bat`.
- **URL:** Access the interface at `http://127.0.0.1:5000`.
- **Function:** Allows on-demand scraping, validation, and visual inspection of the feed.

### B. Automated (CI/CD)
- **Schedule:** Runs daily at 2:00 UTC (3:00 PL time) via GitHub Actions (`daily_scrape.yml`).
- **Actions:**
  1. Sets up the environment.
  2. Runs scrapers (`alfa_inventory.py`, `ds_inventory.py`).
  3. Commits new data and images back to the repository.
  4. Deploys updated CSVs to GitHub Gists for external consumption.

## 3. Scraping & Processing Strategy
- **Priority:** Prefer static analysis (`requests` + `BeautifulSoup`) for speed. Use `selenium` only when necessary (e.g., DS Automobiles).
- **Alfa Romeo Model Feed (Proces):**
  1. `alfa_model.py` -> **Dynamic Discovery:** Automatycznie wykrywa modele na stronie `/modele`, wchodzi na ich podstrony i ekstrahuje:
     - Nazwy i Ceny (Regex).
     - **Kod Modelu (MVSS):** Np. `622` (Tonale), `627` (Junior) z JSON-a `vehicleID` lub linków konfiguratora.
  2. `fetch_live_colors.py` -> Pobiera bazę dostępnych kolorów z API JSON (SCCF). Mapuje kody kolorów na konkretne wersje silnikowe (MVSS).
  3. `generate_full_model_feed.py` -> Główny procesor.
     - **Inteligentne Mapowanie:** Używa wykrytego `model_code` (Krok 1) jako priorytetu, a dopiero potem słów kluczowych w tytule.
     - **Weryfikacja:** Generuje tylko te warianty kolorystyczne, które są potwierdzone jako dostępne przez API.
     - **Cross-Model Fallback:** W przypadku braku szablonów zdjęć dla rzadszych napędów (PHEV, Elettrica), system automatycznie "pożycza" szablony od ich odpowiedników spalinowych/hybrydowych (np. 638 -> 622), zachowując spójność wizualną.
- **Resilience:**
  - Scrapers **must not crash** on missing individual fields. Use `try-except` blocks.
  - Implement fallback logic for selectors.
- **Image Processing:**
  - Raw images from URLs should be processed via `image_processor.py`.
  - Standard output: 600x600px, white background, specific colored border (Alfa: RGB 181,162,152).
  - Saved as high-quality JPEGs in `data/images/`.

## 4. Data Integrity & Output
- **Format:** 
  - Main feeds: **CSV** (`csv.DictWriter`).
  - Auxiliary data/mappings: **JSON** (e.g., `alfa_colors.json`).
- **Location:** `data/` directory (absolute paths).
- **Critical Columns (CSV):**
  - `vehicle_id`: MUST be unique.
  - `amount_price`: Leasing rate (netto/brutto) or full price.
  - `image_link`: Can be a remote URL or a local path (relative to repo root if committed).
- **Validation:** 
  - Use `scrapers/validator.py` to check file health.

## 5. Code Style
- **Language:** Python 3.10+
- **Paths:** Always use `os.path.join` and `os.path.dirname(__file__)` for portability.
- **Dependencies:** Managed in `requirements.txt`.
- **Logging:** Use `print()` for CLI feedback (emojis allowed: 🕷️, ✅, ❌) which is captured by the Dashboard console.
- **Git:** Ensure `data/` changes (CSVs and images) are strictly managed to avoid repo bloat (though current workflow commits them).

## 6. Maintenance
- **Refactoring:** When updating selectors, verify against the live website.
- **Gist Secrets:** Deployment requires `GIST_TOKEN` in GitHub Secrets.

---

## 7. Session Handoff & Status (2026-01-26)

**Context:** Maintenance & Monitoring.

### ✅ Completed (Wdrożone):
1.  **DS Automobiles Full Pipeline:**
    - **Dynamic Discovery:** `scrapers/ds_model.py` automatycznie wykrywa modele (DS 3, DS 4, DS 7, DS 9, N°4, N°8) i ich ceny.
    - **Color Extraction:** `scrapers/extract_ds_colors.py` i `scrapers/finalize_ds_colors.py` pobierają palety kolorów i mapują je na wersje.
    - **Image Processing:** `scrapers/download_ds_images.py` pobiera i przetwarza zdjęcia w wysokiej jakości.
    - **Feed Generation:** Finalne pliki `ds_model_feed.csv` oraz `ds_model_colors_complete.csv` są generowane poprawnie.
    - **Dashboard:** Pełna integracja w `dashboard.py` oraz `templates/index.html`.
2.  **Alfa Romeo Feed Automation:**
    - **Auto-Discovery:** `alfa_model.py` sam wykrywa listę modeli ze strony głównej.
    - **MVSS Extraction:** Automatyczne pobieranie kodów technicznych (np. 622) z JSON-a strony, co eliminuje zgadywanie.
    - Stabilny proces generowania `alfa_model_final.csv` z wykorzystaniem wykrytych kodów.

### 🚀 Next Steps (Plany):
1.  **Monitoring:** Obserwacja działania skryptów w cyklu dobowym (GitHub Actions).
2.  **Maintenance:** Reagowanie na ewentualne zmiany w strukturze stron źródłowych (selektory CSS/API).
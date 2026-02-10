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
- **Schedule:** Runs daily at **02:00 AM Warsaw time** (01:00 UTC) via GitHub Actions (`daily_scrape.yml`).
- **Actions:**
  1. Sets up the environment (Python, Chrome/Selenium).
  2. Runs scrapers (`alfa_inventory.py`, `ds_inventory.py`, `alfa_model.py`, `ds_model.py`).
  3. Updates model feeds (`alfa_model_final.csv`, `ds_model_feed.csv`).
  4. Commits new data and processed images back to the repository.
  5. Deploys updated CSVs to GitHub Gists for external consumption (TikTok/Meta Catalog).

## 3. Scraping & Processing Strategy
- **Priority:** Prefer static analysis (`requests` + `BeautifulSoup`) for speed. Use `selenium` only when necessary.
- **DS Automobiles Model Feed (Proces):**
  1. `ds_model.py` -> Pobiera listę modeli z menu bocznym (`WlUnifiedHeader`).
  2. **Image Selection Logic:**
     - **Primary:** `ds_colors.json` - używa precyzyjnych renderów 3D (visuel3d) lub lokalnych plików `data/images/MODEL_COLORCODE.jpg`.
     - **Secondary:** `ds_inventory.csv` - fallback do zdjęć z otomoto/sklepu.
     - **Tertiary:** Domyślne miniatury ze strony głównej modelu.
  3. `download_colors_json.py` -> Narzędzie do synchronizacji lokalnego folderu `images/` z bazą kolorów JSON.
- **Alfa Romeo Model Feed (Proces):**
  1. `alfa_model.py` -> Dynamiczne wykrywanie kodów MVSS (np. 622, 627) z JSON-a strony.
  2. `fetch_live_colors.py` -> Pobiera bazę kolorów z API SCCF.
  3. `generate_full_model_feed.py` -> Tworzy finalny plik na podstawie macierzy Model x Wersja x Kolor.
- **Image Processing:**
  - Standard output: 600x600px, white background.
  - **Dynamic Borders:** Każdy kolor ma przypisany kolor ramki (np. Lazurite Blue: RGB 0,107,125) zdefiniowany w `COLOR_CONFIG`.
  - Saved in `data/images/`.

## 4. Data Integrity & Output
- **Format:** CSV (DictWriter).
- **Critical Links:**
  - **Alfa Romeo Gist:** `https://gist.githubusercontent.com/Andy11001/541bf43832813acb7d55ded0f686e37c/raw/alfa_model_final.csv`
  - **DS Automobiles Gist:** `https://gist.githubusercontent.com/Andy11001/51716d19f2de2e7b0105659ad35dbc2b/raw/ds_model_feed.csv`

---

## 7. Session Handoff & Status (2026-01-26)

**Context:** Full Automation & Image Accuracy Fix.

### ✅ Completed (Wdrożone):
1.  **Gist Automation:** Pełna synchronizacja feedów modelowych z Gistami poprzez GitHub Actions.
2.  **Image Accuracy Fix (DS):** Naprawiono problem błędnych zdjęć dla wariantów kolorystycznych (np. Cashmere, Lazurite Blue). Teraz system używa specyficznych plików `.jpg` zintegrowanych z `ds_colors.json`.
3.  **Schedule:** Ustawiono odświeżanie na 02:00 czasu polskiego (idealnie pod katalogi reklamowe).
4.  **GitHub CLI:** Zintegrowano `gh` do zarządzania gistami.

### 🚀 Next Steps (Plany):
1.  **Validation:** Monitorowanie poprawności linków w TikToku po pierwszej nocnej aktualizacji.
2.  **Performance:** Optymalizacja pobierania obrazów (pobieranie tylko nowych kodów kolorów).
# Project Rules & Guidelines

## 1. Project Structure & Architecture
The project is organized into a modular structure to separate logic, data, and the user interface.

- **Root Directory:** Contains the main controller (`dashboard.py`), documentation, and configuration.
- **`scrapers/`:** Contains all scraping logic. Each script is standalone.
  - `alfa_inventory.py`: Scrapes actual stock/inventory from `salon.alfaromeo.pl`.
  - `ds_inventory.py`: Scrapes actual stock/inventory from `sklep.dsautomobiles.pl`.
  - `alfa_model.py`: (Planned) Generates generic ads based on configurator models.
  - `ds_model.py`: (Planned) Generates generic ads based on configurator models.
  - `validator.py`: Centralized script to validate integrity of all CSV outputs.
- **`data/`:** The **ONLY** allowed destination for output files.
  - All scrapers must save their `.csv` or `.json` files here using absolute paths.
- **`templates/`:** Contains the HTML frontend (`index.html`) for the dashboard.
- **`archive/`:** Storage for old or debug scripts.

## 2. operational Workflow
- **Primary Interface:** The project is designed to be run via the **Dashboard**.
  - **Start:** Run `start_dashboard.bat`.
  - **URL:** Access the interface at `http://127.0.0.1:5000`.
- **Feed Types:**
  1.  **Inventory Feeds:** Real cars currently available for sale (VIN-specific).
  2.  **Model Feeds:** Generic marketing representations of a Model + Trim + Color combination (Configurator-based).

## 3. Scraping Strategy
- **Priority:** Prefer static analysis (`requests` + `BeautifulSoup`) for speed and stability. Use `selenium` only when data is rendered dynamically via JavaScript (e.g., DS Automobiles).
- **Resilience:** 
  - Scrapers **must not crash** if a single field is missing. Use `try-except` blocks for individual element extraction.
  - Implement fallback logic for selectors.
- **User-Agent:** Always define a realistic `User-Agent` header.
- **Selenium Config:**
  - Run in `headless` mode by default.
  - Include arguments: `--no-sandbox`, `--disable-gpu`, `--disable-blink-features=AutomationControlled`.

## 4. Data Integrity & Output
- **Format:** Output must be a **CSV** file using `csv.DictWriter`.
- **Location:** Files must be saved to the `data/` directory.
- **Critical Columns:**
  - `vehicle_id`: MUST be unique.
  - `amount_price`: Leasing rate (netto/brutto).
  - `image_link`: Must be a valid URL.
- **Validation:** 
  - Use `scrapers/validator.py` to check file health.
  - Ensure `price` and `vehicle_id` are never empty.

## 5. Code Style
- **Language:** Python 3.x
- **Paths:** Always use `os.path.join` and `os.path.dirname(__file__)` to ensure scripts work regardless of where they are executed from.
- **Logging:** Use `print()` for CLI feedback (emojis allowed: 🕷️, ✅, ❌) which is captured by the Dashboard console.
- **Typing:** Use strict type hinting.

## 6. Maintenance
- **Refactoring:** When updating selectors, verify against the live website.
- **Dependencies:** Managed in `requirements.txt`.
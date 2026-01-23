# Context & Goal
We are building a Python-based automation suite to generate **Facebook Product Feeds (CSV)** for **Alfa Romeo** (and DS Automobiles) leasing offers in Poland. The core requirement is to include a **specific image URL** for every combination of Model, Trim (Version), and Color available in the configurator, ensuring the ad matches the offer perfectly.

# Current Architecture
1.  **Feed Scraper (`alfa_romeo_feed_scraper.py`):**
    *   Uses `requests` + `BeautifulSoup` to parse static model pages.
    *   Successfully extracts financial data (price, down payment, term) from legal disclaimers.
    *   *Problem:* Currently uses a single static image per model, missing the visual variety of trims/colors.

2.  **Configurator Crawler (`alfa_configurator_crawler.py` & `alfa_interactive_logger.py`):**
    *   Attempted to use **Selenium** to crawl the dynamic SPA configurator (`https://www.alfaromeo.pl/omni/konfigurator`).
    *   The site is a heavy SPA (Single Page Application) that uses URL hash parameters to manage state (e.g., `#/customize?color=CL-268&commercialModelCode=6261...`).

# The Problem
We are struggling to reliably map **Model + Trim + Color -> Image URL**.

## 1. Automated Crawling Failed
The fully automated crawler failed because:
*   The landing page (`/omni/konfigurator`) uses dynamic tiles that are hard to click programmatically.
*   Inside the configurator, the "Trim" (Version) selection and "Color" picker have complex, dynamic DOM structures (e.g., styled-components classes like `TabIcon-sc-ng0gy4-2`).
*   Standard XPaths for finding "active" elements (e.g., `class='selected'`) often fail or return multiple invisible elements.

## 2. Interactive Logging Partial Success
We built a "human-assisted" logger (`alfa_interactive_logger.py`) where a human clicks through the configurator, and the script records the state.
*   **Success:** It reliably captures the **Image URL** and **URL Parameters** (`commercialModelCode`, `mvss`, `color`).
*   **Failure:** It fails to scrape the **Human-Readable Trim Name** (e.g., "Veloce", "Sprint") from the UI. The script currently records raw codes like `Version_83626E431JFS` instead of "Junior Ibrida Speciale".
*   **Color Names:** It captures some color codes (e.g., `CL-268`) but fails to find the text label "Biały Sempione" in the DOM reliably.

# What We Need (The Task for Claude)
We need a **robust strategy or script** to solve the mapping problem.

**Specific Goals:**
1.  **Fix the Trim/Color Name Scraping:** Look at the provided HTML structure (or suggest a "spy" strategy) to identify the *exact* element containing the "Sprint" / "Veloce" header in the active card. The current checkmark/active-class detection is flaky.
2.  **OR Reverse-Engineer the API/URL:** If scraping the UI is too hard, can we map the `mvss` / `commercialModelCode` parameters to Trim names using a known pattern or a lookup table?
3.  **Final Output:** A JSON file (`alfa_colors.json`) mapping:
    ```json
    {
      "Junior": {
        "Ibrida Speciale": {
          "Biały Sempione": "https://.../white.png",
          "Czerwony Brera": "https://.../red.png"
        },
        "Veloce": { ... }
      }
    }
    ```

# Technical Details
*   **Target URL:** `https://www.alfaromeo.pl/omni/konfigurator`
*   **Deep Link Examples (Discovered SPA States):**
    *   `https://www.alfaromeo.pl/omni/konfigurator#/customize?color=CL-268&interior=IN-033&wheels=8-1M3&commercialModelCode=6261&mvss=83626E231000&sidebarStep=configuration_tab&vehicleType=VP&wcwTyres=false&userType=B2C`
    *   `https://www.alfaromeo.pl/omni/konfigurator#/customize?color=CL-636&interior=IN-XMH&wheels=8-WP8&commercialModelCode=6271&mvss=83627E2E1JFR&sidebarStep=personalization_tab&vehicleType=VP&wcwTyres=false&userType=B2C`
    *   `https://www.alfaromeo.pl/omni/konfigurator#/customize?color=CL-268&interior=IN-070&wheels=8-WP8&commercialModelCode=6271&mvss=83627E2E1JFS&sidebarStep=configuration_tab&vehicleType=VP&wcwTyres=false&userType=B2C`
*   **Stack:** Python, Selenium (Chrome).
*   **Observation:** The "Trims" are vertical cards on the right. The "Colors" are usually accessed via a "Colors & Options" tab or button, displaying a row of circular swatches.

# Current "Broken" Output Example
```json
"Junior": {
    "Version_83626E431JFS": {  <-- WE NEED "Ibrida Speciale" HERE
        "CL-268": "https://..." <-- WE PREFER "Biały Sempione"
    }
}
```

Please provide a refined `Selenium` script or a smart strategy to accurately extract these text labels from the SPA state, effectively bridging the gap between technical codes and marketing names.

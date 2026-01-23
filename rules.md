# Project Rules & Guidelines

## 1. General Architecture
- **Language:** Python 3.x
- **Encoding:** All files must start with `# -*- coding: utf-8 -*-`.
- **Typing:** Use strict type hinting (`from typing import ...`) and `from __future__ import annotations` for forward references.
- **Structure:** Scripts should be standalone executable modules with a `main()` function protected by `if __name__ == "__main__":`.

## 2. Scraping Strategy
- **Priority:** Prefer static analysis (`requests` + `BeautifulSoup`) for speed and stability. Use `selenium` only when data is rendered dynamically via JavaScript (e.g., DS Automobiles).
- **Resilience:** 
  - Scrapers **must not crash** if a single field is missing. Use `try-except` blocks for individual element extraction.
  - Implement fallback logic for selectors (e.g., if a specific class name changes, look for generic containers or text patterns).
- **User-Agent:** Always define a realistic `User-Agent` header to avoid blocking.
- **Selenium Config:**
  - Run in `headless` mode by default for performance.
  - Include arguments: `--no-sandbox`, `--disable-gpu`, `--disable-blink-features=AutomationControlled`.

## 3. Data Integrity & Output
- **Format:** Output must be a **CSV** file using `csv.DictWriter`.
- **Critical Columns:**
  - `vehicle_id`: MUST be unique across the entire file. Use slugification of model + trim + (optional) counter suffix.
  - `amount_price`: Leasing rate (netto/brutto) is the primary value.
  - `image_link`: Must be a valid URL (prefer `og:image` meta tags).
- **Validation:** 
  - Ensure `price` and `vehicle_id` are never empty.
  - Trim whitespace from all extracted text.

## 4. Code Style
- **Config:** Use `dataclasses` for model configuration (e.g., URLs, image links) to separate data from logic.
- **Regex:** Use `re.compile` for complex extraction patterns (especially for disclaimer text parsing) to improve performance and readability.
- **Logging:** Use `print()` for CLI feedback (emojis allowed for better readability: 🕷️, ✅, ❌) or `sys.stderr` for errors.

## 5. Maintenance
- **Refactoring:** When updating selectors, verifying against the live website is mandatory.
- **Dependencies:** Keep dependencies minimal (`requests`, `beautifulsoup4`, `selenium`, `lxml`).

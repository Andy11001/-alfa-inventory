# Feedy samochodowe Stellantis (TikTok/Meta Automotive Ads)

Automatyczne pobieranie inwentarza i feedów modelowych dla marek:
**Alfa Romeo, DS, Opel, Peugeot, Citroën, Fiat (+ Professional), Jeep,
SpotiCar, Leapmotor**. Wyniki trafiają do `data/*.csv`, a GitHub Actions
publikuje je do Gistów co 4–6 h.

## Architektura scrapowania (od czerwca 2026 — bez Selenium w inwentarzach)

| Źródło | Marki | Metoda |
|--------|-------|--------|
| `salon.*.pl` JSON API | Alfa, Jeep, Fiat, Fiat Prof. | czyste API (rata w `financing_info`) |
| `sklep.*.pl` WordPress | Opel, Citroën, Peugeot, DS | WP JSON API + **bezpośrednie API kalkulatora SFS** |
| `spoticar.pl` | SpotiCar | curl_cffi (TLS impersonation, omija Akamai) |

Sklepy WordPress nie podają raty w API — liczy ją kalkulator Stellantis
Financial Services w przeglądarce. Zamiast uruchamiać Chrome/Selenium
(godziny działania, OOM na GitHub Actions), `scrapers/sfs_calculator.py`
parsuje konfigurację kalkulatora z HTML strony i woła API SFS bezpośrednio,
batchami. **Pełny run = minuty zamiast godzin, ~0 dodatkowego RAM.**
Szczegóły protokołu: [docs/SFS_CALCULATOR.md](docs/SFS_CALCULATOR.md).

Selenium (`selenium_helper.py`) zostaje wyłącznie jako automatyczna ścieżka
awaryjna, gdy pokrycie rat z API spadnie poniżej progu — dlatego workflowy
nadal instalują Chrome.

## Samonaprawialność

- wielowariantowe regexy + domyślne parametry marki, gdy strona się zmieni,
- retry z backoffem i dzielenie batchy przy błędach API,
- awaryjny Selenium przy niskim pokryciu (limitowany — bez nawrotu OOM),
- null-safe parsowanie API salon.* (`x.get(k) or ""` + try/except per oferta —
  patrz incydent Fiata 2026-06: jawne `null` w polach dealera ubiło 13 runów),
- `safe_save_csv`: zapis atomowy, backup, próg minimalnej liczby wierszy,
  ochrona przed nadpisaniem pełnego feedu niekompletnym (`no_shrink`),
  alert przy spadku liczby ofert > 60%,
- zbiorcze alerty e-mail przy każdej degradacji (sekrety `EMAIL_*`),
- `concurrency: cancel-in-progress` w workflowach — zawieszony stary run
  nie nadpisze świeżych danych,
- canary (`canary.yml`): codzienny smoke test protokołu SFS — czerwony run
  oznacza zmianę po stronie Stellantis, zanim ucierpią feedy.

## Uruchomienie

```bash
pip install -r requirements.txt
PYTHONPATH=. python scrapers/opel_inventory.py      # i analogicznie pozostałe
```

Przydatne zmienne: `SFS_LIMIT=20` (szybki test na 20 autach),
`SFS_DISABLE_SELENIUM_RESCUE=1` (lokalnie bez Chrome). Pełna lista w
[docs/SFS_CALCULATOR.md](docs/SFS_CALCULATOR.md).

## Struktura

- `scrapers/sfs_calculator.py` — klient kalkulatora SFS (serce projektu),
- `scrapers/wp_shop.py` — wspólne helpery sklepów WordPress (Opel/Citroën/Peugeot/DS),
- `scrapers/salon_api.py` — wspólna, null-safe obsługa rodziny salon.* (Alfa/Jeep/Fiat),
- `scrapers/*_inventory.py` — feedy stockowe (auta z VIN; cienkie pliki marek),
- `scrapers/*_model.py` — feedy modelowe (cenniki/konfigurator),
- `scrapers/scraper_utils.py` — zapis CSV, alerty, retry, formaty tytułów,
- `scrapers/selenium_helper.py` — ścieżka awaryjna (Chrome headless),
- `scrapers/research/` — jednorazowe narzędzia warsztatowe (nieużywane przez workflowy),
- `.github/workflows/*.yml` — harmonogramy, canary i publikacja Gistów,
- `docs/` — protokół SFS, notatki projektowe,
- `data/` — wynikowe CSV + zdjęcia, `archive/` — lokalne backupy (poza gitem).

## Automatyzacja językowa

`scraper_utils.get_availability_word()` dobiera "dostępny/dostępna" po marce
(DS → męski, Alfa Romeo → żeński) — nowe modele nie wymagają zmian w kodzie.

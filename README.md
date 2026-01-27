# Integracja Feedów Alfa Romeo i DS Automobiles

Projekt ten służy do automatycznego pobierania, przetwarzania i udostępniania danych o inwentarzu oraz modelach samochodów marek **Alfa Romeo** i **DS Automobiles**. System składa się ze skryptów scrapujących, które pobierają dane i zapisują je w formacie CSV.

## Funkcjonalności

- **Pobieranie inwentarza**: Automatyczne pobieranie ofert sprzedaży samochodów z oficjalnych stron salonów.
- **Generowanie feedów modelowych**: Tworzenie zestawień modeli wraz ze specyfikacjami i zdjęciami.
- **Weryfikacja danych**: Sprawdzanie poprawności linków do zdjęć i innych kluczowych danych.
- **Eksport danych**: Zapis przetworzonych danych w formacie CSV.

## Wymagania

- Python 3.8+
- Google Chrome (wymagany dla Selenium)

Zależności Python (znajdują się w `requirements.txt`):
- `requests`
- `pandas`
- `beautifulsoup4`
- `selenium`
- `Pillow`

## Instalacja

1. Sklonuj repozytorium lub pobierz pliki projektu.
2. Zainstaluj wymagane biblioteki:
   ```bash
   pip install -r requirements.txt
   ```

## Uruchomienie

Skrypty znajdują się w katalogu `scrapers/`. Można je uruchamiać bezpośrednio z wiersza poleceń.

### Pobieranie inwentarza

**Alfa Romeo:**
```bash
python scrapers/alfa_inventory.py
```

**DS Automobiles:**
```bash
python scrapers/ds_inventory.py
```

### Generowanie feedów modelowych

**Alfa Romeo:**
```bash
python scrapers/alfa_model.py
```

**DS Automobiles:**
```bash
python scrapers/ds_model.py
```

### Weryfikacja danych

```bash
python scrapers/validator.py
```

Po uruchomieniu skryptów, przetworzone pliki CSV pojawią się w katalogu `data/`.

### Opis plików i katalogów

- **`scrapers/`**: Katalog zawierający logikę pobierania danych.
  - `alfa_inventory.py`: Pobiera inwentarz Alfa Romeo.
  - `ds_inventory.py`: Pobiera inwentarz DS Automobiles.
  - `alfa_model.py`: Generuje feed modelowy dla Alfa Romeo.
  - `ds_model.py`: Generuje feed modelowy dla DS Automobiles.
  - `validator.py`: Narzędzie do weryfikacji danych.
  - `scraper_utils.py`: Funkcje pomocnicze (logowanie, obsługa błędów, zapis plików).
- **`data/`**: Katalog, w którym zapisywane są wyniki działania skryptów (pliki CSV).

## Uwagi

- Skrypty wykorzystują połączenia sieciowe do zewnętrznych API i stron internetowych. Upewnij się, że masz stabilne połączenie internetowe.
- W przypadku problemów z Selenium, upewnij się, że masz zainstalowaną najnowszą wersję przeglądarki Chrome.

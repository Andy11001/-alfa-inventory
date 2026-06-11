# Kalkulator SFS — jak pobieramy raty bez Selenium

> Dokumentacja protokołu odkrytego w czerwcu 2026. Jeśli scraper przestanie
> zwracać raty, zacznij diagnozę od tego pliku.

## Skąd strona bierze ratę

Sklepy stockowe Stellantis na WordPressie:

| Marka | Sklep | brandSlug | Wyświetlany produkt |
|-------|-------|-----------|---------------------|
| Opel | sklep.opel.pl | `opel` | `l101` (Leasing 101,8%) |
| Citroën | sklep.citroen.pl | `citroen` | `l101` |
| Peugeot | sklep.peugeot.pl | `peugeot` | `l101` |
| DS | sklep.dsautomobiles.pl | `ds-automobiles` | `b2b` (Abonament SimplyDrive) |

Strona produktu zawiera w HTML (renderowane serwerowo, **bez JS**):

1. Konfigurację pluginu kalkulatora:
   ```js
   new FCP.FinancialCalculatorPlugin({
       calculatorApi: 'https://sfs.stellantis-financial-services.pl/api',
       wsHost: 'sfs.stellantis-financial-services.pl', wsPath: '/ws',
       brandSlug: 'opel', websiteId: 'salon', isProduction: true, ...})
   ```
2. Dane pojazdu w wywołaniach `fcp.attachOffer('id-oferty-b2b', {...}, {...}, [], true)`:
   `modelName, modelCode, grossPrice, netPrice, baseGrossPrice, baseNetPrice,
   fuelType, LCDV` — to jest payload `vehicle` dla API.
3. Domyślne wartości suwaków kalkulatora (noUiSlider):
   `l101_suwak_period: {start: 60, ...}`, `l101_suwak_contribution: {start: 20}`,
   `l101_suwak_repurchase: {start: 26}` itd. — **różnią się per strona/model!**
4. `dataLayer` z `edealerCity` / `edealerName` (miasto dealera).

Plugin w przeglądarce wysyła te dane WebSocketem (lub XHR fallbackiem) do API
SFS i wpisuje wynik do `#top_sekcja_wysokosc_raty`. Stary scraper czekał na to
Selenium — nowy (`scrapers/sfs_calculator.py`) woła API bezpośrednio.

## Endpointy API

**Detekcja produktów + kalkulacja w jednym** (tego używamy):

```
POST https://sfs.stellantis-financial-services.pl/api/calculation/
     detect-website-products/{brandSlug}/salon/production
     ?withSolData=true&withCalculationParams=true

Body:    { "<uuid>": {"vehicle": {...}, "fields": {period, contribution,
                       repurchase|limitKm}, "extraServices": []}, ... }
         (batch: wiele aut w jednym żądaniu — testowane 168 naraz)

Response: { "<uuid>": { "b2b":  {calculatorId, installment, priceType: "NET", ...},
                        "l101": {...}, "b2c": {...GROSS}, "p0p": {...} } }
```

**Sama kalkulacja** (gdy znasz `calculatorId` z detekcji):

```
POST .../api/calculation/calculate/{brandSlug}
Body: { "<uuid>": {"calculatorId": 9536, "vehicle": {...}, "fields": {...},
                   "extraServices": []} }
```

Nagłówki: `Content-Type: application/json` + `Origin`/`Referer` sklepu.

## Wyświetlana rata = co?

`round(installment)` produktu **domyślnej zakładki** policzonego dla **startowych
wartości suwaków z danej strony**. Produkty `l101`/`b2b` są NET (feed: "rata
netto/mies."), `b2c`/`p0p` są GROSS — dlatego fallback w `pick_display_rate`
ogranicza się do produktów NET.

Zweryfikowano empirycznie (Selenium vs API, 2026-06):
Opel Grandland 1815/1655 ✓, Peugeot Boxer 2549 ✓, DS 7 1110 ✓,
Citroën Jumper 2387 (Selenium w ogóle nie umiał odczytać tej strony).

## Samonaprawialność (sfs_calculator)

1. Parsery mają warianty regexów; brak suwaków → domyślne pola marki
   (API i tak przycina wartości do `availableFields`).
2. Brak preferowanego produktu → fallback na drugi produkt NET + wpis w stats.
3. Nieudany batch → retry z backoffem → podział batcha na pół → pojedynczo.
4. Pokrycie < `SFS_RESCUE_THRESHOLD` (domyślnie 50%) → awaryjny **Selenium**
   (stary `selenium_helper.py`, limit `SFS_RESCUE_CAP=150` aut) — dlatego
   workflowy nadal instalują Chrome.
5. Każda degradacja → JEDEN zbiorczy e-mail (nie per auto).

## Zmienne środowiskowe

| Zmienna | Domyślnie | Po co |
|---------|-----------|-------|
| `SFS_LIMIT` | 0 (bez limitu) | Smoke testy: przetwórz tylko N aut |
| `SFS_PAGE_WORKERS` | 8 | Równoległość pobierania stron |
| `SFS_DETECT_CHUNK` | 40 | Aut na jeden batch do API |
| `SFS_RESCUE_THRESHOLD` | 0.5 | Próg pokrycia uruchamiający Selenium |
| `SFS_RESCUE_CAP` | 150 | Maks. aut ratowanych Selenium |
| `SFS_DISABLE_SELENIUM_RESCUE` | – | `1` = nigdy nie odpalaj Selenium |

## Gdy coś się zepsuje — ścieżka diagnozy

1. Czy WP API żyje? `GET https://sklep.opel.pl/wp-json/wp/v2/product?per_page=1`
2. Czy strona produktu ma `attachOffer` i `new FCP.FinancialCalculatorPlugin`?
   (jeśli zniknęły — sklep zmienił kalkulator; sprawdź nowy plugin JS)
3. Czy API SFS odpowiada 200 na detect? (payload z pkt. 2)
4. `calculatorApi`/`brandSlug` w configu strony — czy się zmieniły?
   `sfs_calculator.py` ma je w `BRAND_CONFIG`; zaktualizuj, jeśli trzeba.

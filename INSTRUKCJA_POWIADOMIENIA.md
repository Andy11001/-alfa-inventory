# Instrukcja konfiguracji powiadomień mailowych 📧

Twój system generowania feedów potrafi teraz wysyłać maile, gdy coś pójdzie nie tak (np. awaria strony importera). Aby to działało, musisz wykonać poniższą konfigurację.

---

## KROK 1: Przygotowanie hasła do Gmaila (Ważne!)

Zwykłe hasło do Gmaila **nie zadziała** ze względu na zabezpieczenia Google. Musisz wygenerować tzw. "Hasło aplikacji".

1.  Zaloguj się na swoje konto Google.
2.  Wejdź pod ten link: [https://myaccount.google.com/apppasswords](https://myaccount.google.com/apppasswords)
    *   *(Jeśli link nie działa, wejdź w: Konto Google -> Bezpieczeństwo -> Weryfikacja dwuetapowa -> (na dole) Hasła do aplikacji)*.
3.  Zostaniesz poproszony o ponowne zalogowanie.
4.  W polu "Nazwa aplikacji" wpisz np. `Car Feed Scraper` i kliknij **Utwórz**.
5.  Wyświetli się **16-znakowe hasło** w żółtej ramce (np. `abcd efgh ijkl mnop`).
6.  **SKOPIUJ JE** – to jest Twoje `EMAIL_PASSWORD`.

---

## KROK 2: Konfiguracja na komputerze (Lokalnie)

Dzięki temu powiadomienia będą działać, gdy uruchomisz skrypt ręcznie u siebie.

1.  Wejdź do głównego folderu projektu `Feed`.
2.  Znajdź plik o nazwie `.env.example`.
3.  Zrób jego kopię i zmień nazwę na `.env` (po prostu `.env`, bez żadnego txt na końcu).
4.  Otwórz plik `.env` w Notatniku.
5.  Wypełnij go swoimi danymi:

```ini
EMAIL_HOST=smtp.gmail.com
EMAIL_PORT=587
EMAIL_USER=twoj.prawdziwy.mail@gmail.com
EMAIL_PASSWORD=wklej_tutaj_to_haslo_z_kroku_1
EMAIL_RECIPIENT=twoj.mail@gmail.com
```

Zapisz plik. Gotowe! Plik `.env` jest prywatny i nikt go nie zobaczy na GitHubie.

---

## KROK 3: Konfiguracja na GitHubie (Automatyzacja)

Dzięki temu otrzymasz maila, jeśli skrypt wywali się w nocy podczas automatycznego uruchomienia.

1.  Wejdź na stronę swojego repozytorium na GitHubie.
2.  W górnym menu kliknij **Settings** (Ustawienia).
3.  W menu po lewej stronie znajdź sekcję **Secrets and variables**, rozwiń ją i kliknij **Actions**.
4.  Kliknij zielony przycisk **New repository secret**.
5.  Dodaj dwa sekrety (kopiuj-wklej nazwy dokładnie tak jak poniżej):

    **Sekret 1:**
    *   **Name:** `EMAIL_USER`
    *   **Secret:** `twoj.prawdziwy.mail@gmail.com`
    *   Kliknij *Add secret*.

    **Sekret 2:**
    *   **Name:** `EMAIL_PASSWORD`
    *   **Secret:** `wklej_tutaj_to_haslo_z_kroku_1`
    *   Kliknij *Add secret*.

    *(Opcjonalnie) Sekret 3:*
    *   **Name:** `EMAIL_RECIPIENT`
    *   **Secret:** `adres.na.ktory.ma.przyjsc.alert@gmail.com`
    *   *(Jeśli tego nie dodasz, mail przyjdzie na ten sam adres, z którego został wysłany).*

---

## Kiedy dostaniesz maila?

System wyśle alert tylko w sytuacjach awaryjnych:
1.  **Awaria sieci:** Gdy skrypt 3 razy pod rząd nie połączy się ze stroną (np. `salon.alfaromeo.pl`).
2.  **Pusty feed:** Gdy importer zwróci 0 aut (ochrona przed nadpisaniem Twojego pliku pustą listą).
3.  **Spadek ofert:** Gdy liczba aut nagle spadnie o ponad 60% (np. z 500 na 50).

Tytuł maila będzie zaczynał się od `[FEED ALERT]`.

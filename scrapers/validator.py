# -*- coding: utf-8 -*-
"""
Walidator feedów CSV
====================

Sprawdza wszystkie feedy w data/ (albo w podanym katalogu / plikach):
  - wymagane kolumny (vehicle_id, title, link, image_link, cena),
  - puste i powtórzone vehicle_id,
  - wiersze bez ceny i bez zdjęcia,
  - liczbę wierszy względem wersji z HEAD w gicie (spadek > 60% = błąd).

Kod wyjścia 1, gdy jest choć jeden błąd — można go wstawić jako krok CI
przed commitem, żeby zepsuty feed nie trafił do repo i Gista.

Użycie:
  PYTHONPATH=. python scrapers/validator.py              # całe data/
  PYTHONPATH=. python scrapers/validator.py data/smoke   # próbka z SFS_LIMIT
  PYTHONPATH=. python scrapers/validator.py data/opel_osobowe_inventory.csv
"""
import csv
import glob
import os
import subprocess
import sys
from collections import Counter

if sys.stdout.encoding and sys.stdout.encoding.lower() != "utf-8":
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA_DIR = os.path.join(PROJECT_ROOT, "data")

# Pliki pośrednie i pomocnicze — nie są feedami dla odbiorców
NOT_FEEDS = {
    "alfa_model_feed.csv",          # wejście generate_full_model_feed.py
    "alfa_configurator_images.csv",
    "leapmotor_model_feed.csv",     # surowe oferty, żaden workflow go nie publikuje
}
# Feedy, które bywają legalnie puste (Abarth zwykle nie ma stocku)
MAY_BE_EMPTY = {"abarth_inventory.csv"}
# Feedy, w których brak zdjęć jest znany i akceptowany (Abarth nie ma źródła zdjęć)
IMAGES_OPTIONAL = {"abarth_model.csv", "abarth_inventory.csv"}

REQUIRED = ["vehicle_id", "title", "link", "image_link"]
PRICE_COLUMNS = ("price", "amount_price")
MAX_DROP = 0.6
MAX_NO_IMAGE = 0.2


def read_rows(path):
    with open(path, encoding="utf-8-sig", newline="") as f:
        reader = csv.DictReader(f)
        return reader.fieldnames or [], list(reader)


def previous_row_count(path):
    """Liczba wierszy tego pliku w HEAD (None, gdy plik nie jest w gicie)."""
    try:
        rel = os.path.relpath(os.path.abspath(path), PROJECT_ROOT).replace(os.sep, "/")
    except ValueError:  # inny dysk niż repo (Windows)
        return None
    if rel.startswith("../"):
        return None
    try:
        out = subprocess.run(["git", "show", f"HEAD:{rel}"], cwd=PROJECT_ROOT,
                             capture_output=True, check=True).stdout
    except (subprocess.CalledProcessError, FileNotFoundError):
        return None
    text = out.decode("utf-8-sig", errors="replace")
    return max(0, len(list(csv.reader(text.splitlines()))) - 1)


def validate(path):
    """Zwraca (błędy, ostrzeżenia, liczba wierszy) dla jednego feedu."""
    name = os.path.basename(path)
    errors, warnings = [], []
    try:
        fieldnames, rows = read_rows(path)
    except Exception as e:
        return [f"nie da się odczytać CSV: {e}"], [], 0

    if not fieldnames:
        if name in MAY_BE_EMPTY:
            return [], ["pusty plik (bez nagłówka)"], 0
        return ["pusty plik (bez nagłówka)"], [], 0

    missing = [c for c in REQUIRED if c not in fieldnames]
    price_col = next((c for c in PRICE_COLUMNS if c in fieldnames), None)
    if not price_col:
        missing.append("price/amount_price")
    if missing:
        errors.append(f"brak kolumn: {', '.join(missing)}")

    if not rows:
        (warnings if name in MAY_BE_EMPTY else errors).append("0 wierszy")
        return errors, warnings, 0

    if "vehicle_id" in fieldnames:
        ids = [(r.get("vehicle_id") or "").strip() for r in rows]
        empty = sum(1 for i in ids if not i)
        if empty:
            errors.append(f"{empty} wierszy bez vehicle_id")
        dups = {i: n for i, n in Counter(ids).items() if i and n > 1}
        if dups:
            sample = ", ".join(list(dups)[:3])
            errors.append(f"{sum(n - 1 for n in dups.values())} powtórzonych "
                          f"vehicle_id ({len(dups)} różnych, np. {sample})")

    if price_col:
        no_price = sum(1 for r in rows if not (r.get(price_col) or "").strip())
        if no_price:
            errors.append(f"{no_price} wierszy bez ceny ({price_col})")

    if "image_link" in fieldnames:
        no_image = sum(1 for r in rows if not (r.get("image_link") or "").strip())
        if no_image:
            msg = f"{no_image}/{len(rows)} wierszy bez zdjęcia"
            if name in IMAGES_OPTIONAL or no_image / len(rows) <= MAX_NO_IMAGE:
                warnings.append(msg)
            else:
                errors.append(msg)

    prev = previous_row_count(path)
    if prev:
        drop = (prev - len(rows)) / prev
        if drop > MAX_DROP:
            errors.append(f"spadek liczby wierszy o {drop:.0%} ({prev} -> {len(rows)})")
        elif drop > 0.2:
            warnings.append(f"spadek liczby wierszy o {drop:.0%} ({prev} -> {len(rows)})")

    return errors, warnings, len(rows)


def collect(args):
    targets = args or [DATA_DIR]
    files = []
    for t in targets:
        if os.path.isdir(t):
            files.extend(sorted(glob.glob(os.path.join(t, "*.csv"))))
        else:
            files.append(t)
    return [f for f in files if os.path.basename(f) not in NOT_FEEDS]


def main(argv):
    files = collect(argv)
    if not files:
        print("Brak plików CSV do sprawdzenia.")
        return 1
    total_errors = 0
    for path in files:
        errors, warnings, n = validate(path)
        status = "BŁĄD" if errors else ("UWAGA" if warnings else "OK")
        print(f"[{status:5}] {os.path.basename(path)}: {n} wierszy")
        for e in errors:
            print(f"        błąd: {e}")
        for w in warnings:
            print(f"        uwaga: {w}")
        total_errors += len(errors)
    print(f"\n{len(files)} feedów, błędów: {total_errors}")
    return 1 if total_errors else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))

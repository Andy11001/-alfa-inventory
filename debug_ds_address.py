import requests
import sys

url = "https://sklep.dsautomobiles.pl/produkt/ds-7/vr1j45gb2sy590176/"
r = requests.get(url, headers={"User-Agent": "Mozilla/5.0"})
with open("ds_debug_location.html", "w", encoding="utf-8") as f:
    f.write(r.text)

# Szukaj "Adres:" i kawałka tekstu wokół
idx = r.text.find("Adres:")
if idx != -1:
    print("--- KONTEKST ADRESU ---")
    print(r.text[idx-100:idx+300])
else:
    print("Nie znaleziono ciągu 'Adres:'")

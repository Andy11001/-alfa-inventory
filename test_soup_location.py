import requests
from bs4 import BeautifulSoup
import json

url = "https://sklep.dsautomobiles.pl/produkt/ds-7/vr1j45gb2sy590176/"
r = requests.get(url, headers={"User-Agent": "Mozilla/5.0"})
html = r.text
soup = BeautifulSoup(html, 'html.parser')

print(f"URL: {url}")
# Sprawdźmy wszystkie divy z klasą col-4
cols = soup.find_all("div", class_="col-4")
print(f"Found {len(cols)} divs with class 'col-4'")
for col in cols:
    print(f"COL TEXT: '{col.get_text(strip=True)}'")
    sibling = col.find_next_sibling("div", class_="col-8")
    if sibling:
        print(f"   SIBLING: '{sibling.get_text(strip=True)}'")

# Sprawdźmy czy "Adres:" w ogóle istnieje w tekście
if "Adres:" in html:
    print("Słowo 'Adres:' ISTNIEJE w HTML")
else:
    print("Słowa 'Adres:' BRAK w HTML")

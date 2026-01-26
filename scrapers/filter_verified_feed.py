import csv
import requests
from PIL import Image
from io import BytesIO
import os

# Konfiguracja
INPUT_FILE = os.path.join(os.path.dirname(os.path.dirname(__file__)), "data", "alfa_model_final.csv")
OUTPUT_FILE = os.path.join(os.path.dirname(os.path.dirname(__file__)), "data", "alfa_model_final_filtered.csv")

def is_black_hole(url):
    """
    Wykrywa 'czarną dziurę' na podstawie ilości IDEALNIE czarnych pikseli (0,0,0).
    """
    try:
        # Zmniejszamy rozmiar dla szybkości
        test_url = url.replace("width=1445", "width=300").replace("height=768", "height=160")
        r = requests.get(test_url, timeout=10, headers={"User-Agent": "Mozilla/5.0"})
        if r.status_code != 200: return True
        
        img = Image.open(BytesIO(r.content)).convert("RGB")
        w, h = img.size
        
        # Wycinamy obszar karoserii (środek)
        crop = img.crop((w//4, h//3, 3*w//4, 2*h//3))
        pixels = list(crop.getdata())
        
        # Liczymy TYLKO idealną czerń (0,0,0)
        pure_black = sum(1 for p in pixels if p == (0, 0, 0))
        pure_black_ratio = pure_black / len(pixels)

        # Na podstawie testów:
        # Prawdziwe czarne auto (601) -> ok 5.8%
        # Czarna dziura (035) -> ok 7.9% (często więcej na większych renderach)
        # Ustawiamy próg na 7.2% dla bezpieczeństwa
        if pure_black_ratio > 0.072:
            return True
            
        return False
    except Exception as e:
        return True

def main():
    print("Rozpoczynanie filtracji 'Czarnych Dziur' (Próg: 7.2% czystej czerni)...")
    
    verified_rows = []
    with open(INPUT_FILE, 'r', encoding='utf-8') as f:
        reader = csv.DictReader(f)
        rows = list(reader)
        
    total = len(rows)
    for i, row in enumerate(rows):
        if i % 10 == 0 or i == total - 1:
            print(f"[{i+1}/{total}] Sprawdzanie: {row['title']} - {row['color_name']}...", end="\r")
        
        if not is_black_hole(row['image_link']):
            verified_rows.append(row)

    print(f"\n\nFILTRACJA ZAKOŃCZONA:")
    print(f"- Oryginalna liczba wariantów: {total}")
    print(f"- Usunięto (czarne dziury): {total - len(verified_rows)}")
    print(f"- Pozostało poprawnych: {len(verified_rows)}")
    
    with open(OUTPUT_FILE, 'w', newline='', encoding='utf-8') as f:
        writer = csv.DictWriter(f, fieldnames=rows[0].keys())
        writer.writeheader()
        writer.writerows(verified_rows)
    print(f"Zapisano do: {OUTPUT_FILE}")

if __name__ == "__main__":
    main()

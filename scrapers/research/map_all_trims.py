import csv
import json
import os

# Konfiguracja
INPUT_FILE = os.path.join(os.path.dirname(os.path.dirname(__file__)), "data", "alfa_model_final.csv")
OUTPUT_FILE = os.path.join(os.path.dirname(os.path.dirname(__file__)), "data", "alfa_model_final_verified.csv")
TEMPLATES_FILE = os.path.join(os.path.dirname(os.path.dirname(__file__)), "data", "other_templates.json")

# Stelvio Template (Hardcoded from previous success)
STELVIO_TEMPLATE = "https://lb.assets.fiat.com/vl-picker-service/rest/getImage?wheel=WHK&fuel=2&body={COLOR}&packs=B24&resolution=BIG&mmvs={MVSS}&market=3123&seat=071&view=EXT&opt=015,189,316,365,392,41X,4DK,508,510,55B,9FX,BNH,JKJ,NH3,SJB,XNW,02X,070,19W,3KL,3KM,5F3,5FE,5IH,5PN,6YL,LCB,MFF,MMR,XF3,03A,03B,0MK,129,1ZN,217,2CZ,2J4,2L5,3OS,4G9,4GO,4I4,6HQ,78E,78N,858,8CF,A5A,JKD,03V,396,4CS,79U,BFQ,BV5,BV6,051,110,136,156,195,347,384,3KJ,410,452,4H0,4M6,4WE,50X,543,57E,5DE,631,64L,693,7H6,7XF,83Z,845,8CL,CDE,CSD,GTD,GX4,JRC,LCA,NHS,RFX,XCR,18Q,1D8,939,SDD,499,4DD,BV7,4JF,5BH,83X,8EW,8TW,9YP,RDG,RS3,RS9,RTK,52N,58B,412,8G2,9YZ,B24&trim=040&engine=MOT012&angle=1&model=6305&drive=5&brand=83&gear=64&client=OMNICS&consumer=high&source=omnimto&width=1445&height=768&skipReconcile=true"

def clean_template_url(url):
    """Zamienia view=INT na view=EXT i angle=2 na angle=1"""
    return url.replace("view=INT", "view=EXT").replace("angle=2", "angle=1").replace("width=706", "width=1445").replace("height=375", "height=768")

def map_trims():
    print("Mapowanie szablonów dla wszystkich modeli...")

    # Wczytaj szablony
    with open(TEMPLATES_FILE, 'r') as f:
        templates = json.load(f)

    # Przygotuj szablony (czyszczenie URLi)
    T_GIULIA = clean_template_url(templates.get("GIULIA", ""))
    T_TONALE_HYBRID = clean_template_url(templates.get("TONALE_HYBRID", ""))
    T_TONALE_HYBRID_H = clean_template_url(templates.get("TONALE_HYBRID_H", ""))
    T_TONALE_PHEV = clean_template_url(templates.get("TONALE_PHEV", ""))

    rows = []
    with open(INPUT_FILE, 'r', encoding='utf-8') as f:
        reader = csv.DictReader(f)
        rows = list(reader)

    updated_count = 0
    
    for row in rows:
        title = row['title'].upper()
        mvss = row['mvss']
        color = row['color_code']
        
        new_url = None

        # 1. STELVIO
        if "STELVIO" in title:
            new_url = STELVIO_TEMPLATE.format(COLOR=color, MVSS=mvss)
        
        # 2. GIULIA
        elif "GIULIA" in title:
            # Wstawiamy kolor i MVSS do szablonu Giulii
            # Uwaga: Szablony z capture_others.py mają już wpisane konkretne body=... i mmvs=...
            # Musimy je podmienić dynamicznie
            if T_GIULIA:
                base = T_GIULIA
                # Prosta podmiana stringów w URLu (zakładamy format z capture)
                # Szukamy parametrów w URLu i podmieniamy je
                # Najbezpieczniej jest użyć replace na znanych wartościach z szablonu, 
                # ale te wartości mogą być różne w zależności od tego co złapał capture.
                # Lepiej użyć regex lub parsowania, ale dla prostoty zrobimy replace na parametrach query.
                
                # Zamiast parsować, po prostu podmienimy 'body=XXX' na 'body={color}'
                import re
                base = re.sub(r'body=[^&]+', f'body={color}', base)
                base = re.sub(r'mmvs=[^&]+', f'mmvs={mvss}', base)
                new_url = base

        # 3. TONALE
        elif "TONALE" in title:
            selected_template = None
            
            # Logika doboru szablonu
            if mvss.startswith("83638"):
                selected_template = T_TONALE_PHEV
            elif mvss.startswith("83622MFD") or mvss.startswith("83622DER"):
                selected_template = T_TONALE_HYBRID_H # 160 KM & Veloce
            elif mvss.startswith("83622MF3") or mvss.startswith("83622MET"):
                selected_template = T_TONALE_HYBRID # 130 KM & Sprint
            else:
                # Fallback
                selected_template = T_TONALE_HYBRID_H
            
            if selected_template:
                import re
                base = selected_template
                base = re.sub(r'body=[^&]+', f'body={color}', base)
                base = re.sub(r'mmvs=[^&]+', f'mmvs={mvss}', base)
                new_url = base

        # 4. JUNIOR (Zostawiamy bez zmian lub używamy istniejącego jeśli działa)
        # Zakładamy, że Junior jest już OK z poprzednich kroków, ale jeśli chcemy być pewni,
        # możemy też tu dodać logikę. Na razie zostawiamy Juniora w spokoju, bo nie był zgłaszany jako problem teraz.

        if new_url:
            row['image_link'] = new_url
            updated_count += 1

    # Zapisz wynik
    with open(OUTPUT_FILE, 'w', newline='', encoding='utf-8') as f:
        writer = csv.DictWriter(f, fieldnames=rows[0].keys())
        writer.writeheader()
        writer.writerows(rows)

    print(f"Zaktualizowano {updated_count} wierszy. Wynik w: {OUTPUT_FILE}")

if __name__ == "__main__":
    map_trims()
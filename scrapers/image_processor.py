import requests
from PIL import Image, ImageOps
from io import BytesIO
import os

def process_image(url, output_path):
    """Pobiera zdjęcie, dodaje białe tło 600x600 i złotą ramkę."""
    try:
        response = requests.get(url, timeout=10)
        img = Image.open(BytesIO(response.content)).convert("RGBA")
        
        # Docelowy rozmiar płótna
        canvas_size = (600, 600)
        # Margines dla auta wewnątrz płótna
        inner_margin = 40
        
        # Skalowanie zdjęcia, aby zmieściło się wewnątrz z marginesem
        max_size = (canvas_size[0] - inner_margin * 2, canvas_size[1] - inner_margin * 2)
        img.thumbnail(max_size, Image.Resampling.LANCZOS)
        
        # Tworzenie białego tła
        background = Image.new("RGB", canvas_size, (255, 255, 255))
        
        # Centrowanie zdjęcia na tłe
        offset = ((canvas_size[0] - img.size[0]) // 2, (canvas_size[1] - img.size[1]) // 2)
        
        # Jeśli zdjęcie ma przezroczystość, używamy jej jako maski
        if img.mode == 'RGBA':
            background.paste(img, offset, img)
        else:
            background.paste(img, offset)
            
        # Dodawanie złotej ramki (kolor złoty: #D4AF37)
        gold_color = (212, 175, 55)
        border_width = 8
        background = ImageOps.expand(background, border=border_width, fill=gold_color)
        
        # Ponowne skalowanie do 600x600 (po dodaniu ramki obrazek się powiększył)
        background = background.resize(canvas_size, Image.Resampling.LANCZOS)
        
        # Zapisywanie jako JPG (oszczędność miejsca)
        background.convert("RGB").save(output_path, "JPEG", quality=90)
        return True
    except Exception as e:
        print(f"Błąd przetwarzania obrazu {url}: {e}")
        return False

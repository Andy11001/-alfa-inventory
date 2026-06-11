import os
import shutil
import time
import tempfile
import csv
import logging
import smtplib
from email.message import EmailMessage
from datetime import datetime
from dotenv import load_dotenv

# Ładowanie zmiennych z pliku .env (jeśli istnieje)
load_dotenv(os.path.join(os.path.dirname(os.path.dirname(__file__)), '.env'))

# Konfiguracja logowania
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# --- NOWA SEKCJA: Formatting Description ---
def get_availability_word(model_name):
    """
    Automatycznie określa rodzaj gramatyczny (Męski/Żeński) dla modelu samochodu.
    Zwraca "dostępny" (Męski) lub "dostępna" (Żeński).
    """
    if not model_name: 
        return "dostępny"
        
    m = model_name.upper().strip()

    # 1. Logika dla DS (Marka męska - "Ten DS")
    if "DS" in m or m.startswith("DS"):
        return "dostępny"
    
    # 2. Logika dla Alfa Romeo (Marka żeńska - "Ta Alfa")
    # Zgodnie z sugestią i powszechną praktyką marketingową ("Ta Alfa Romeo"),
    # dla wszystkich modeli Alfa Romeo przyjmujemy rodzaj żeński.
    # Np. "Alfa Romeo Junior dostępna", "Alfa Romeo Stelvio dostępna".
    return "dostępna"

def format_model_description(title, price_str):
    """
    Tworzy opis modelu zoptymalizowany pod TikTok Automotive Ads.
    Format: "{Title} · Rata od {Price} netto/mies. · Leasing B2B · Sprawdź ofertę!"
    """
    if price_str:
        return f"{title} · Rata od {price_str} netto/mies. · Leasing B2B · Sprawdź ofertę!"
    else:
        return f"{title} · Leasing B2B · Sprawdź ofertę!"

def format_model_title(title, price_str):
    """
    Tworzy tytuł modelu zoptymalizowany pod TikTok Automotive Ads.
    Format: "{Title} · od {Price}/mies."
    """
    if price_str:
        return f"{title} · od {price_str}/mies."
    return title

def format_inventory_title(model, trim, installment):
    """
    Tworzy tytuł oferty stockowej zoptymalizowany pod TikTok Automotive Ads.
    Format: "{Model} {Trim} · od {rata} PLN/mies."
    """
    base = f"{model} {trim}".strip()
    if installment:
        return f"{base} · od {installment} PLN/mies."
    return base

def format_inventory_description(make, model, trim, installment, city=""):
    """
    Tworzy opis oferty stockowej zoptymalizowany pod TikTok Automotive Ads.
    Format: "{Make} {Model} {Trim} · Rata od {rata} PLN netto/mies. · Leasing B2B · {City} · Sprawdź!"
    """
    full_name = f"{make} {model} {trim}".strip()
    parts = [full_name]
    if installment:
        parts.append(f"Rata od {installment} PLN netto/mies.")
    parts.append("Leasing B2B")
    if city:
        parts.append(city)
    parts.append("Sprawdź ofertę!")
    return " · ".join(parts)
# ------------------------------------------

import hashlib

def generate_stable_id(text, prefix="", length=10):
    """
    Generuje stabilny, deterministyczny ID na podstawie tekstu (MD5).
    """
    if not text:
        text = "unknown"
    
    # MD5 hash
    hash_object = hashlib.md5(text.strip().lower().encode('utf-8'))
    hex_dig = hash_object.hexdigest()
    
    # Bierzemy N pierwszych znaków
    id_suffix = hex_dig[:length].upper()
    
    if prefix:
        return f"{prefix}-{id_suffix}"
    return id_suffix

def send_email_alert(subject, body):
    """
    Wysyła powiadomienie e-mail, jeśli skonfigurowano zmienne środowiskowe:
    Processing error alert.
    Requires: EMAIL_HOST, EMAIL_PORT, EMAIL_USER, EMAIL_PASSWORD in os.environ
    """
    host = os.environ.get("EMAIL_HOST", "smtp.gmail.com")
    port = int(os.environ.get("EMAIL_PORT", 587))
    user = os.environ.get("EMAIL_USER")
    password = os.environ.get("EMAIL_PASSWORD")
    recipient = os.environ.get("EMAIL_RECIPIENT", user) # Wyślij do siebie jeśli brak odbiorcy

    if not user or not password:
        logger.warning("⚠️ Konfiguracja e-mail (EMAIL_USER/EMAIL_PASSWORD) nie jest ustawiona. Alert nie został wysłany.")
        return

    msg = EmailMessage()
    msg.set_content(body)
    msg['Subject'] = f"[FEED ALERT] {subject}"
    msg['From'] = user
    msg['To'] = recipient

    try:
        server = smtplib.SMTP(host, port)
        server.starttls()
        server.login(user, password)
        server.send_message(msg)
        server.quit()
        logger.info(f"📧 Wysłano alert e-mail: {subject}")
    except Exception as e:
        logger.error(f"❌ Nie udało się wysłać maila: {e}")

def create_backup(file_path, logger_instance=None):
    """Tworzy kopię zapasową pliku w folderze archive/ z datą."""
    log = logger_instance or logger
    if not os.path.exists(file_path):
        return
    
    archive_dir = os.path.join(os.path.dirname(os.path.dirname(file_path)), 'archive')
    if not os.path.exists(archive_dir):
        os.makedirs(archive_dir)
        
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    filename = os.path.basename(file_path)
    backup_path = os.path.join(archive_dir, f"{filename}_{timestamp}.bak")
    
    try:
        shutil.copy2(file_path, backup_path)
        log.info(f"Utworzono głośną kopię zapasową: {backup_path}")
    except Exception as e:
        log.error(f"Nie udało się utworzyć kopii zapasowej: {e}")

def safe_save_csv(data_rows, fieldnames, output_file, min_rows_threshold=5, no_shrink=False):
    """
    Bezpieczny zapis pliku CSV:
    1. Sprawdza czy liczba wierszy > min_rows_threshold.
    2. Zapisuje do pliku tymczasowego.
    3. Tworzy backup starego pliku.
    4. Podmienia plik docelowy (atomic write).

    no_shrink=True: nie nadpisuj istniejącego pliku, jeśli nowy zestaw ma MNIEJ
    wierszy niż obecny (używane przy zapisie częściowym po sygnale/timeoucie —
    nigdy nie zamieniamy pełnego feedu na niekompletny).
    """
    if len(data_rows) < min_rows_threshold:
        msg = f"ZBYT MAŁO DANYCH! Próbowano zapisać {len(data_rows)} wierszy (wymagane min. {min_rows_threshold}). Zapis anulowany."
        logger.error(msg)
        send_email_alert("Data Threshold Error", f"{msg}\nPlik: {output_file}")
        return False

    # Sprawdzenie drastycznego spadku liczby ofert (opcjonalne, np. max 50% spadku)
    if os.path.exists(output_file):
        try:
            with open(output_file, 'r', encoding='utf-8') as f:
                old_lines = sum(1 for _ in f) - 1 # minus header

            if no_shrink and old_lines > len(data_rows):
                logger.info(f"[no_shrink] Pomijam zapis {output_file}: {len(data_rows)} < {old_lines} istniejących wierszy (zachowuję pełny feed).")
                return False

            if old_lines > 0:
                drop_ratio = (old_lines - len(data_rows)) / old_lines
                if drop_ratio > 0.6: # Jeśli spadek o więcej niż 60%
                    msg = f"Drastyczny spadek liczby ofert (-{int(drop_ratio*100)}%). Było: {old_lines}, Jest: {len(data_rows)}."
                    logger.warning(f"OSTRZEŻENIE: {msg}")
                    send_email_alert("Data Drop Warning", f"{msg}\nPlik: {output_file}\n(Zapis kontynuowany)")
        except Exception:
            pass

    # Krok 1 & 2: Zapis do tymczasowego pliku
    temp_dir = tempfile.gettempdir()
    temp_path = os.path.join(temp_dir, f"temp_{os.path.basename(output_file)}")
    
    try:
        with open(temp_path, 'w', newline='', encoding='utf-8-sig') as f:
            writer = csv.DictWriter(f, fieldnames=fieldnames, extrasaction='ignore')
            writer.writeheader()
            writer.writerows(data_rows)
        
        # Weryfikacja czy plik tymczasowy nie jest pusty
        if os.path.getsize(temp_path) < 10:
            raise Exception("Wygenerowany plik tymczasowy jest podejrzanie mały/pusty.")

        # Krok 3: Backup
        create_backup(output_file)

        # Krok 4: Atomowa podmiana
        shutil.move(temp_path, output_file)
        logger.info(f"Sukces! Zapisano {len(data_rows)} ofert do {output_file}")
        return True

    except Exception as e:
        logger.error(f"Błąd podczas bezpiecznego zapisu: {e}")
        if os.path.exists(temp_path):
            os.remove(temp_path)
        return False

def fetch_with_retry(session, url, retries=3, delay=3, **kwargs):
    """Wykonuje żądanie HTTP z automatycznym ponawianiem."""
    for i in range(retries):
        try:
            response = session.get(url, **kwargs)
            response.raise_for_status()
            return response
        except Exception as e:
            if i < retries - 1:
                logger.warning(f"Błąd pobierania {url}: {e}. Ponawianie za {delay}s... ({i+1}/{retries})")
                time.sleep(delay)
            else:
                topic = "Network Error"
                msg = f"Nie udało się pobrać {url} po {retries} próbach. Błąd: {e}"
                logger.error(msg)
                send_email_alert(topic, msg)
                raise e

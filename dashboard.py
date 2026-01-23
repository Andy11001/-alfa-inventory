import sys
import subprocess
import os
import pandas as pd
from flask import Flask, render_template, jsonify

app = Flask(__name__)

# Konfiguracja ścieżek
ALFA_SCRIPT = "alfa_romeo_inventory_scraper.py"
DS_SCRIPT = "DS_feed_scraper.py"
VALIDATOR_SCRIPT = "Walidator.py"

ALFA_CSV = "alfa_romeo_inventory.csv"
DS_CSV = "ds_feed_final.csv"

@app.route('/')
def index():
    return render_template('index.html')

@app.route('/run/<script_name>', methods=['POST'])
def run_script(script_name):
    cmd = []
    if script_name == 'alfa':
        cmd = [sys.executable, ALFA_SCRIPT]
    elif script_name == 'ds':
        # Dodajemy flagę headless dla DS
        cmd = [sys.executable, DS_SCRIPT, "--headless"]
    elif script_name == 'validate':
        cmd = [sys.executable, VALIDATOR_SCRIPT]
    else:
        return jsonify({'error': 'Nieznany skrypt', 'output': ''}), 400

    try:
        # Force Python subprocess to output UTF-8
        env = os.environ.copy()
        env["PYTHONIOENCODING"] = "utf-8"

        # Uruchomienie procesu i przechwycenie wyjścia
        result = subprocess.run(
            cmd, 
            capture_output=True, 
            text=True, 
            encoding='utf-8',
            errors='replace',  # Zapobiega błędom dekodowania (np. 0xb3)
            cwd=os.getcwd(), # Uruchom w bieżącym katalogu
            env=env
        )
        
        output = result.stdout
        if result.stderr:
            output += "\n--- STDERR ---\n" + result.stderr

        return jsonify({
            'success': result.returncode == 0,
            'output': output,
            'error': None if result.returncode == 0 else "Proces zwrócił błąd."
        })
    except Exception as e:
        return jsonify({'success': False, 'output': '', 'error': str(e)}), 500

@app.route('/data/<feed_type>')
def get_data(feed_type):
    file_path = ALFA_CSV if feed_type == 'alfa' else DS_CSV
    
    if not os.path.exists(file_path):
        return f'<div class="alert alert-warning">Plik {file_path} nie istnieje. Uruchom scraper.</div>'

    try:
        # Czytanie CSV i konwersja do HTML table z klasami Bootstrap
        df = pd.read_csv(file_path)
        # Ograniczenie podglądu do 50 wierszy dla wydajności
        df_preview = df.head(50)
        
        # Skracanie długich tekstów do wyświetlania
        def truncate(x):
            if isinstance(x, str) and len(x) > 100:
                return x[:100] + "..."
            return x
            
        df_preview = df_preview.map(truncate) if hasattr(df_preview, 'map') else df_preview.applymap(truncate)
        
        table_html = df_preview.to_html(
            classes="table table-striped table-hover table-bordered table-sm",
            index=False,
            border=0
        )
        return table_html
    except Exception as e:
        return f'<div class="alert alert-danger">Błąd odczytu pliku: {e}</div>'

if __name__ == '__main__':
    print("🚀 Uruchamianie Dashboardu...")
    print("Otwórz w przeglądarce: http://127.0.0.1:5000")
    app.run(debug=True, port=5000)

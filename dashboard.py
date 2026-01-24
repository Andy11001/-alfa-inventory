import sys
import subprocess
import os
import pandas as pd
from flask import Flask, render_template, jsonify, send_file

app = Flask(__name__)

# Konfiguracja ścieżek
SCRAPERS_DIR = os.path.join(os.path.dirname(__file__), 'scrapers')
DATA_DIR = os.path.join(os.path.dirname(__file__), 'data')

SCRIPTS = {
    'alfa_inventory': os.path.join(SCRAPERS_DIR, "alfa_inventory.py"),
    'ds_inventory': os.path.join(SCRAPERS_DIR, "ds_inventory.py"),
    'alfa_model': os.path.join(SCRAPERS_DIR, "alfa_model.py"),
    'ds_model': os.path.join(SCRAPERS_DIR, "ds_model.py"),
    'validate': os.path.join(SCRAPERS_DIR, "validator.py")
}

DATA_FILES = {
    'alfa_inventory': os.path.join(DATA_DIR, "alfa_romeo_inventory.csv"),
    'ds_inventory': os.path.join(DATA_DIR, "ds_inventory.csv"),
    'alfa_model': os.path.join(DATA_DIR, "alfa_model.csv"),
    'ds_model': os.path.join(DATA_DIR, "ds_model.csv")
}

@app.route('/')
def index():
    return render_template('index.html')

@app.route('/run/<script_name>', methods=['POST'])
def run_script(script_name):
    script_path = SCRIPTS.get(script_name)
    
    if not script_path:
        return jsonify({'error': 'Nieznany skrypt', 'output': ''}), 400

    cmd = [sys.executable, script_path]
    if script_name == 'ds_inventory':
         # Example flag if needed, though new structure might handle it differently
         # keeping consistency with previous logic if it expected args
         pass 

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
            errors='replace',
            cwd=os.getcwd(), 
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

@app.route('/download/<feed_type>')
def download_feed(feed_type):
    file_path = DATA_FILES.get(feed_type)
    
    if not file_path or not os.path.exists(file_path):
        return "Plik nie istnieje. Najpierw uruchom scraper.", 404
        
    return send_file(file_path, as_attachment=True)

@app.route('/data/<feed_type>')
def get_data(feed_type):
    file_path = DATA_FILES.get(feed_type)
    
    if not file_path:
         return f'<div class="alert alert-warning">Podgląd dla {feed_type} niedostępny.</div>'
    
    if not os.path.exists(file_path):
        return f'<div class="alert alert-warning">Plik {file_path} nie istnieje. Uruchom scraper.</div>'

    try:
        df = pd.read_csv(file_path)
        df_preview = df.head(50)
        
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

@echo off
echo ==========================================
echo    AUTOMATYZACJA FEED SCRAPER DASHBOARD
echo ==========================================

echo [1/2] Sprawdzanie i instalacja zaleznosci (Flask, Pandas)...
python -m pip install flask pandas selenium beautifulsoup4 requests lxml

echo.
echo [2/2] Uruchamianie Dashboardu...
echo Otworz przegladarke na: http://127.0.0.1:5000
echo (Aby zakonczyc, zamknij to okno lub wcisnij CTRL+C)
echo.

python dashboard.py

pause
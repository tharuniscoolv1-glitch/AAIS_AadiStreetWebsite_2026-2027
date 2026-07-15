@echo off
REM ─────────────────────────────────────────────────────────────────────────
REM  start.bat — One-click launcher for the LAN POS Flask app (Windows)
REM  Double-click this file OR run it from PowerShell / CMD.
REM ─────────────────────────────────────────────────────────────────────────

echo.
echo  [1/3] Checking Python...
python --version || (echo Python not found. Install from https://python.org && pause && exit /b 1)

echo.
echo  [2/3] Installing Flask...
pip install -r requirements.txt --quiet

echo.
echo  [3/3] Starting LAN POS server...
echo.
echo  ========================================================
echo   Open in browser: http://127.0.0.1:5000
echo   For other LAN devices: run 'ipconfig' to get your IP
echo   e.g. http://192.168.1.X:5000
echo  ========================================================
echo.

python app.py
pause

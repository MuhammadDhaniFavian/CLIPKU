@echo off
title CliperKu - AI Auto Clipper
echo ====================================================
echo   Menjalankan CliperKu (Local Web Application)
echo ====================================================
echo.

echo [1/2] Menjalankan Backend FastAPI di http://127.0.0.1:8000 ...
start "CliperKu Backend" /min cmd /c "cd /d "%~dp0backend" && venv\Scripts\python.exe -m uvicorn app.main:app --host 127.0.0.1 --port 8000"

echo [2/2] Menjalankan Frontend Vite di http://localhost:5173 ...
cd /d "%~dp0frontend"
npm run dev

pause


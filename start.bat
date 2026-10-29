@echo off
title CliperKu - AI Auto Clipper Launcher
color 0B
echo ====================================================
echo         CliperKu - AI Auto Video Clipper
echo        100%% Offline, Cepat, dan Bebas Kuota
echo ====================================================
echo.

echo [1/3] Menjalankan Backend FastAPI di http://127.0.0.1:8000 ...
start "CliperKu Backend (Uvicorn)" /min cmd /c "cd /d "%~dp0backend" && venv\Scripts\python.exe -m uvicorn app.main:app --host 127.0.0.1 --port 8000"

echo [2/3] Menyiapkan Frontend Web UI ...
start "CliperKu Frontend (Vite)" /min cmd /c "cd /d "%~dp0frontend" && npm run dev"

echo [3/3] Membuka CliperKu di Peramban Web Browser...
timeout /t 3 /nobreak >nul
start http://localhost:5173

echo.
echo ====================================================
echo  CliperKu berhasil berjalan!
echo  - Web App  : http://localhost:5173
echo  - API Docs : http://127.0.0.1:8000/docs
echo.
echo  Untuk menghentikan aplikasi, jalankan stop.bat
echo ====================================================
echo.
pause

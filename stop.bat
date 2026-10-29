@echo off
title Hentikan CliperKu
color 0C
echo ====================================================
echo        Menghentikan Layanan CliperKu...
echo ====================================================
echo.

echo Menghentikan proses Backend (Uvicorn / Python)...
taskkill /F /FI "WINDOWTITLE eq CliperKu Backend*" >nul 2>&1

echo Menghentikan proses Frontend (Vite / Node)...
taskkill /F /FI "WINDOWTITLE eq CliperKu Frontend*" >nul 2>&1

echo.
echo ====================================================
echo  Semua layanan CliperKu telah dihentikan.
echo ====================================================
echo.
timeout /t 2 >nul
exit

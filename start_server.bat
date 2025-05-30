@echo off
cd /d E:\MarinKino

:: Zaženi Flask preko Waitress
start "" python app.py

:: Počakaj 22 sekund (da se Flask zažene)
timeout /t 22 >nul

:: Zaženi Caddy s HTTPS podporo
start "" C:\Caddy\caddy.exe run

@echo off
setlocal EnableDelayedExpansion

:: Nastavi pot do log datoteke
for /f %%i in ('wmic os get localdatetime ^| find "."') do set dt=%%i
set LOGDATE=%dt:~0,4%-%dt:~4,2%-%dt:~6,2%_%dt:~8,2%-%dt:~10,2%
set LOGFILE=E:\.MarinKinoCache\logs\server_start_%LOGDATE%.txt

:: Zapiši začetni čas
echo. >> %LOGFILE%
echo ===== Zagon [%DATE% %TIME%] ===== >> %LOGFILE%

:: --- 1. Preveri ali je zagnano kot administrator ---
NET SESSION >nul 2>&1
if %errorlevel% NEQ 0 (
    echo [NAPAKA] Skripto moraš zagnati kot Administrator! >> %LOGFILE%
    echo [NAPAKA] Skripto moraš zagnati kot Administrator!
    pause
    exit /b
)

:: --- 2. Preveri ali so porti 80 ali 443 že zasedeni ---
echo [INFO] Preverjam ali sta porta 80 ali 443 zasedena... >> %LOGFILE%
echo [INFO] Preverjam ali sta porta 80 ali 443 zasedena...

for %%P in (80 443) do (
    netstat -aon | find ":%%P " | find /i "LISTENING" >nul
    if !errorlevel! EQU 0 (
        echo [NAPAKA] Port %%P je že zaseden! Uporablja ga drug program. >> %LOGFILE%
        echo [NAPAKA] Port %%P je že zaseden! Uporablja ga drug program.
        pause
        exit /b
    )
)

:: --- 3. Preveri ali že teče python app.py (Waitress) ---
tasklist | find /i "python.exe" >nul
if %errorlevel% EQU 0 (
    echo [OPOZORILO] Python že teče. Morda je Flask že zagnan. >> %LOGFILE%
)

:: --- 4. Preveri ali že teče caddy.exe ---
tasklist | find /i "caddy.exe" >nul
if %errorlevel% EQU 0 (
    echo [OPOZORILO] Caddy je že zagnan. Morda teče v ozadju. >> %LOGFILE%
)

:: --- 5. Premik v mapo projekta ---
cd /d E:\MarinKino

:: --- 6. Zagon Flask/Waitress ---
echo [INFO] Zagon Flask aplikacije prek Waitress... >> %LOGFILE%
start "" /B cmd /c "python app.py >> %LOGFILE% 2>&1"

:: --- 7. Počakaj da se Flask zažene ---
timeout /t 22 >nul

:: --- 8. Zagon Caddy strežnika ---
echo [INFO] Zagon Caddy z HTTPS podporo... >> %LOGFILE%
start "" /B cmd /c "C:\Caddy\caddy.exe run >> %LOGFILE% 2>&1"

:: --- 9. Zaključno sporočilo ---
echo [USPEH] Flask in Caddy sta bila zagnana! >> %LOGFILE%
echo [USPEH] Flask in Caddy sta bila zagnana!
echo Obišči: https://anzemarinko.duckdns.org >> %LOGFILE%

echo ===== Konec [%DATE% %TIME%] ===== >> %LOGFILE%
timeout /t 120 >nul
endlocal

@echo off
setlocal EnableDelayedExpansion

forfiles /p "E:\.MarinKinoCache\logs" /m *.log /d -7 /c "cmd /c del @file"

:: --- Pripravi timestamp in pot do log datoteke ---
for /f %%i in ('wmic os get localdatetime ^| find "."') do set dt=%%i
set LOGDATE=%dt:~0,4%-%dt:~4,2%-%dt:~6,2%_%dt:~8,2%-%dt:~10,2%
set LOGFILE=E:\.MarinKinoCache\logs\duckdns_refresh_%LOGDATE%.txt

echo ===== DuckDNS posodobitev [%DATE% %TIME%] ===== >> %LOGFILE%

:: --- Preberi .env datoteko ---
for /f "usebackq tokens=1,* delims==" %%A in (".env") do (
    set "key=%%A"
    set "value=%%B"
    set "!key!=!value!"
)

:: --- Preveri obvezne spremenljivke ---
if not defined DUCKDNS_DOMAIN (
    echo [NAPAKA] DUCKDNS_DOMAIN ni definiran v .env datoteki >> %LOGFILE%
    echo DUCKDNS_DOMAIN ni definiran v .env datoteki
    goto :konec
)

if not defined DUCKDNS_TOKEN (
    echo [NAPAKA] DUCKDNS_TOKEN ni definiran v .env datoteki >> %LOGFILE%
    echo DUCKDNS_TOKEN ni definiran v .env datoteki
    goto :konec
)

:: --- Pošlji zahtevek ---
echo [INFO] Pošiljam zahtevek na DuckDNS... >> %LOGFILE%
curl "https://www.duckdns.org/update?domains=!DUCKDNS_DOMAIN!&token=!DUCKDNS_TOKEN!&ip=" >> %LOGFILE% 2>&1

echo [INFO] DuckDNS posodobitev zaključena. >> %LOGFILE%

:konec
echo ===== Konec [%DATE% %TIME%] ===== >> %LOGFILE%
timeout /t 120 >nul
endlocal

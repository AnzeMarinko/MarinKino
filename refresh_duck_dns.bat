@echo off
setlocal EnableDelayedExpansion

:: Preberi .env datoteko in nastavi spremenljivke
for /f "usebackq tokens=1,* delims==" %%A in (".env") do (
    set "%%A=%%B"
)

:: Pošlji zahtevek na DuckDNS
curl "https://www.duckdns.org/update?domains=%DUCKDNS_DOMAIN%&token=%DUCKDNS_TOKEN%&ip="

endlocal

#!/bin/bash
# ========================================
# DuckDNS IP osvežitev + čiščenje starih logov
# ========================================

# --- Nastavitve ---
LOG_DIR="/media/marinko/Local2TB/.MarinKinoCache/logs"
ENV_FILE=".env"

# --- Ustvari log datoteko s časovnim žigom ---
LOGDATE=$(date +"%Y-%m-%d_%H-%M")
LOGFILE="$LOG_DIR/duckdns_refresh_$LOGDATE.txt"

echo "===== DuckDNS posodobitev [$(date)] =====" >> "$LOGFILE"

# --- Pobriši stare loge, starejše od 3 dni ---
find "$LOG_DIR" -type f -name "*.txt" -mtime +3 -delete

# --- Preberi .env datoteko (če obstaja) ---
if [ -f "$ENV_FILE" ]; then
    export $(grep -v '^#' "$ENV_FILE" | xargs)
else
    echo "[NAPAKA] Datoteka $ENV_FILE ne obstaja." | tee -a "$LOGFILE"
    exit 1
fi

# --- Preveri obvezne spremenljivke ---
if [ -z "$DUCKDNS_DOMAIN" ]; then
    echo "[NAPAKA] DUCKDNS_DOMAIN ni definiran v .env datoteki." | tee -a "$LOGFILE"
    exit 1
fi

if [ -z "$DUCKDNS_TOKEN" ]; then
    echo "[NAPAKA] DUCKDNS_TOKEN ni definiran v .env datoteki." | tee -a "$LOGFILE"
    exit 1
fi

# --- Pošlji zahtevek na DuckDNS ---
echo "[INFO] Pošiljam zahtevek na DuckDNS..." | tee -a "$LOGFILE"
curl -s "https://www.duckdns.org/update?domains=$DUCKDNS_DOMAIN&token=$DUCKDNS_TOKEN&ip=" >> "$LOGFILE" 2>&1

echo "" >> "$LOGFILE"
echo "[INFO] DuckDNS posodobitev zaključena." | tee -a "$LOGFILE"
echo "===== Konec [$(date)] =====" >> "$LOGFILE"

# --- Počakaj 120 sekund (če želiš podobno vedenje kot timeout) ---
sleep 120

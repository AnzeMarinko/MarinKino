#!/bin/bash

# === Nastavitve ===
LOG_DIR="/home/marinko/Desktop/MarinKinoCache/logs"
PROJECT_DIR="/home/marinko/Desktop/MarinKino"
PYTHON_APP="$PROJECT_DIR/app.py"

# Ustvari log mapo, če še ne obstaja
mkdir -p "$LOG_DIR"

# Datum za ime log datoteke
LOGDATE=$(date +"%Y-%m-%d_%H-%M")
LOGFILE="$LOG_DIR/server_start_${LOGDATE}.txt"

echo "" >> "$LOGFILE"
echo "===== Zagon [$(date)] =====" >> "$LOGFILE"

# === 1. Preveri, ali je zagnano kot root ===
if [ "$EUID" -ne 0 ]; then
  echo "[NAPAKA] Skripto moraš zagnati kot root (sudo)!" | tee -a "$LOGFILE"
  exit 1
fi

# === 2. Preveri, ali je port 80 zaseden ===
echo "[INFO] Preverjam, ali je port 80 zaseden..." | tee -a "$LOGFILE"

if ss -tuln | grep -q ":80 "; then
  echo "[NAPAKA] Port 80 je že zaseden!" | tee -a "$LOGFILE"
  # exit 1
fi

# === 3. Preveri, ali python app že teče ===
if pgrep -f "$PYTHON_APP" >/dev/null; then
  echo "[OPOZORILO] Python ($PYTHON_APP) že teče." | tee -a "$LOGFILE"
fi

cd "$PROJECT_DIR" || { echo "[NAPAKA] Mapa $PROJECT_DIR ne obstaja!" | tee -a "$LOGFILE"; exit 1; }

# === 4. Zagon Flask/Waitress ===
echo "[INFO] Zagon Flask aplikacije prek Waitress..." | tee -a "$LOGFILE"

$PROJECT_DIR/.venv/bin/python -u "$PYTHON_APP" >> "$LOGFILE" 2>&1

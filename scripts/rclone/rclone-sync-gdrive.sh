#!/bin/bash
# ============================================
# rclone sync skripta za sinhronizacijo sprememb v Google Drive
# ============================================
set -e

# Nastavitve poti
LOG_DIR="/home/marinko/Desktop/MarinKino/cache/logs/rclone"
LOG_FILE="${LOG_DIR}/rclone_sync_$(date +'%Y-%m-%d_%H-%M').log"
IGNORE_FILE="/home/marinko/Desktop/MarinKino/scripts/rclone/rclone-ignore.txt"
RCLONE_CONF="/home/marinko/.config/rclone/rclone.conf"
CACHE_DIR="/home/marinko/.cache/rclone"
LOCK_FILE="/tmp/rclone-bisync-MarinKino.lock"

# Ustvari mapo za loge, če ne obstaja
mkdir -p "$LOG_DIR"

### ====== LOCK ======
exec 9>"$LOCK_FILE"
if ! flock -n 9; then
  echo "❌ rclone sync že teče – exit" >> "$LOG_FILE"
  exit 1
fi

echo "▶️ START sync $(date)" >> "$LOG_FILE"

/usr/bin/rclone --config "$RCLONE_CONF" sync "/home/marinko/Desktop/MarinKino" "gdrive:MarinKino" \
  --exclude-from "$IGNORE_FILE" \
  --drive-chunk-size 512M \
  --checkers=8 \
  --transfers=2 \
  --metadata \
  --cache-dir "$CACHE_DIR" \
  --drive-acknowledge-abuse \
  --log-file "$LOG_FILE" \
  --max-delete 500 \
  --verbose \
  --use-server-modtime \
  --fast-list --modify-window 5s

### ====== CLEAN LOGS ======

MAX_LOGS=10
cd "$LOG_DIR"
ls -t | grep -v '/$' | tail -n +$((MAX_LOGS+1)) | xargs -r rm --

echo "✅ FINISHED $(date)" >> "$LOG_FILE"

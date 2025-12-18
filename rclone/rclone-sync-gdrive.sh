#!/bin/bash
# ============================================
# rclone sync skripta za sinhronizacijo sprememb v Google Drive
# ============================================
set -e

# Nastavitve poti
LOG_DIR="/home/marinko/Desktop/MarinKinoCache/rclone-logs"
LOG_FILE="${LOG_DIR}/rclone_sync_$(date +'%Y-%m-%d_%H-%M').log"
IGNORE_FILE="/home/marinko/Desktop/MarinKino/rclone/rclone-ignore.txt"
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

/usr/bin/rclone sync "/home/marinko/Desktop/MarinKino" "gdrive:MarinKino" \
  --exclude-from "$IGNORE_FILE" \
  --drive-chunk-size 512M \
  --checkers=8 \
  --transfers=2 \
  --metadata \
  --cache-dir "$CACHE_DIR" \
  --drive-acknowledge-abuse \
  --log-file "$LOG_FILE" \
  --max-delete 50 \
  --verbose \
  --use-server-modtime \
  --fast-list --modify-window 5s

### ====== CLEAN LOGS ======

ls -tp "$LOG_DIR" | grep -v '/$' | tail -n +$((MAX_LOGS+1)) | xargs -r rm --

echo "✅ FINISHED $(date)" >> "$LOG_FILE"

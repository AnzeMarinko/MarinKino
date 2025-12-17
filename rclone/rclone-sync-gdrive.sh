#!/bin/bash
# ============================================
# rclone sync skripta za kopiranje sprememb na Google Drive
# ============================================

# Nastavitve poti
LOG_DIR="/home/marinko/Desktop/MarinKinoCache/rclone-logs"
LOG_FILE="${LOG_DIR}/rclone_sync_$(date +'%Y-%m-%d_%H-%M').log"
IGNORE_FILE="/home/marinko/Desktop/MarinKino/rclone/rclone-ignore.txt"
CACHE_DIR="/home/marinko/.cache/rclone"

# Ustvari mapo za loge, če ne obstaja
mkdir -p "$LOG_DIR"

# Sinhronizacija lokalnih map v oblak
/usr/bin/rclone sync "/media/marinko/Desktop/MarinKino" "gdrive:MarinKino" \
	--exclude-from "$IGNORE_FILE" \
	--drive-chunk-size 512M \
	--checkers=8 \
	--transfers=2 \
	--metadata \
	--cache-dir "$CACHE_DIR" \
	--drive-acknowledge-abuse \
	--log-file "$LOG_FILE" \
	--max-delete 100 \
	--verbose \
	--use-server-modtime \
	--fast-list --modify-window 5s

# Očisti stare log datoteke (ohrani zadnjih 10)
cd "$LOG_DIR"
ls -tp | grep -v '/$' | tail -n +11 | xargs -r rm -- 2>/dev/null


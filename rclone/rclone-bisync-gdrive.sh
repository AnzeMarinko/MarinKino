#!/bin/bash
# ============================================
# rclone bisync skripta za Google Drive Mirror
# ============================================

# Nastavitve poti
LOG_DIR="/media/marinko/Local2TB/GoogleDriveMirrorLogs"
LOG_FILE="${LOG_DIR}/rclone_bisync_$(date +'%Y-%m-%d_%H-%M-%S').log"
IGNORE_FILE="/media/marinko/Local2TB/GoogleDriveMirror/rclone-ignore.txt"
CACHE_DIR="/home/marinko/.cache/rclone"

# Ustvari mapo za loge, če ne obstaja
mkdir -p "$LOG_DIR"

# Sinhronizacija lokalnih map v oblak
for DIR in "Slike" "MarinKino"; do
  /usr/bin/rclone sync "/media/marinko/Local2TB/GoogleDriveMirror/${DIR}" "gdrive:${DIR}" \
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
done

# Sinhronizacija oblaka v lokalno
for DIR in "Dokumenti" "Druzinsko" "OsebniZapisi" "KolednikiHomec"; do
  /usr/bin/rclone sync "gdrive:${DIR}" "/media/marinko/Local2TB/GoogleDriveMirror/${DIR}" \
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
done

# Očisti stare log datoteke (ohrani zadnjih 10)
cd "$LOG_DIR"
ls -tp | grep -v '/$' | tail -n +11 | xargs -r rm -- 2>/dev/null


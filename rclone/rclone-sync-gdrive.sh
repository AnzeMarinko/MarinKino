#!/bin/bash
# ============================================
# rclone bisync skripta za sinhronizacijo sprememb z Google Drive
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

EMAIL_ALERT="anze.marinko96@gmail.com"

### ====== LOCK ======
exec 9>"$LOCK_FILE"
if ! flock -n 9; then
  echo "❌ rclone bisync že teče – exit" >> "$LOG_FILE"
  exit 1
fi

### ====== FUNKCIJE ======

send_alert() {
  MSG="$1"

  # Email
  if [[ -n "$EMAIL_ALERT" ]]; then
    echo "$MSG" | mail -s "⚠️ rclone bisync ALERT" "$EMAIL_ALERT"
  fi
}

run_bisync() {
  /usr/bin/rclone bisync "/media/marinko/Desktop/MarinKino" "gdrive:MarinKino" \
    # --resync \
    --exclude-from "$IGNORE_FILE" \
    --drive-chunk-size 512M \
    --checkers=8 \
    --transfers=2 \
    --metadata \
    --cache-dir "$CACHE_DIR" \
    --drive-acknowledge-abuse \
    --conflict-resolve newer \
    --conflict-loser backup \
    --backup-dir "gdrive:_conflicts/MarinKino" \
    --log-file "$LOG_FILE" \
    --max-delete 50 \
    --verbose \
    --use-server-modtime \
    --fast-list --modify-window 5s
}

run_dryrun() {
  /usr/bin/rclone bisync "/media/marinko/Desktop/MarinKino" "gdrive:MarinKino" \
    # --resync \
    --dry-run \
    --exclude-from "$IGNORE_FILE" \
    --drive-chunk-size 512M \
    --checkers=8 \
    --transfers=2 \
    --metadata \
    --cache-dir "$CACHE_DIR" \
    --drive-acknowledge-abuse \
    --conflict-resolve newer \
    --conflict-loser backup \
    --backup-dir "gdrive:_conflicts/MarinKino" \
    --log-file "$LOG_FILE" \
    --max-delete 50 \
    --verbose \
    --use-server-modtime \
    --fast-list --modify-window 5s
}

### ====== ZAGON ======

echo "▶️ START bisync $(date)" >> "$LOG_FILE"

if ! run_bisync; then
  echo "❌ BISYNC FAILED – running dry-run" >> "$LOG_FILE"
  run_dryrun

  send_alert "❌ rclone bisync FAILED

Lokacija: $LOCAL_DIR
Čas: $(date)

Dry-run izveden – preveri log:
$LOG_FILE"
  exit 1
fi

### ====== KONFLIKTI ======

if grep -qi "conflict" "$LOG_FILE"; then
  send_alert "⚠️ rclone bisync KONFLIKT zaznan

Preveri:
gdrive:_conflicts/MarinKino

Log:
$LOG_FILE"
fi

### ====== CLEAN LOGS ======

ls -tp "$LOG_DIR" | grep -v '/$' | tail -n +$((MAX_LOGS+1)) | xargs -r rm --

echo "✅ FINISHED $(date)" >> "$LOG_FILE"

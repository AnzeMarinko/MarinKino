#!/usr/bin/env bash
# Mirror persistent project files, including private configuration, to Drive.
set -Eeuo pipefail
PATH=/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin
export PATH
umask 077
project=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/../.." && pwd)
config=/etc/marinkino-security/rclone.conf
dry_run=false
while (($#)); do
    case "$1" in
        --project) project=$2; shift 2 ;;
        --config) config=$2; shift 2 ;;
        --dry-run) dry_run=true; shift ;;
        *) echo "Unknown option: $1" >&2; exit 2 ;;
    esac
done
[[ $EUID == 0 ]] || { echo 'Run with sudo so certificates and private data can be read.' >&2; exit 2; }
project=$(realpath -- "$project")
[[ -f "$project/.env" && -f "$project/scripts/rclone/rclone-ignore.txt" && -s "$config" ]] || {
    echo 'Project .env, rclone filter and configured rclone.conf are required.' >&2; exit 2;
}
command -v rclone >/dev/null || { echo 'Install rclone first.' >&2; exit 2; }
cache=/var/cache/marinkino-rclone
logs="$project/cache/logs/rclone"
install -d -m 700 "$cache" "$logs"
exec 9>"$cache/sync.lock"
flock -n 9 || { echo 'Rclone backup already running'; exit 0; }
stamp=$(date -u +%Y-%m-%d_%H-%M-%S)
log="$logs/rclone_sync_$stamp.log"
printf 'Dnevnik: %s\n' "$log"
exec >>"$log" 2>&1
redis_stage=''
finish() {
    result=$?
    trap - EXIT
    if [[ -n "$redis_stage" ]]; then rm -rf -- "$redis_stage"; fi
    printf '[%s] Rclone finished; exit=%s\n' "$(date -Is)" "$result"
    exit "$result"
}
trap finish EXIT
printf '[%s] Rclone started\n' "$(date -Is)"
common=(--config "$config" --cache-dir "$cache" --log-file "$log"
    --log-level NOTICE --stats 5m --stats-one-line --stats-log-level NOTICE
    --checkers 4 --transfers 2 --drive-chunk-size 32M "--dry-run=$dry_run")
# Publish dated archives first. Copy retains older remote archives.
if [[ -d /var/backups/marinkino ]]; then
    rclone copy /var/backups/marinkino gdrive:MarinKino-backups \
        --include '*.tar.age' "${common[@]}"
fi
# Redis data lives in a named Docker volume, outside the project mirror.
if [[ "$dry_run" == false ]] && command -v docker >/dev/null; then
    running=$(docker inspect --format '{{.State.Running}}' marinkino-redis 2>/dev/null || true)
    if [[ "$running" == true ]]; then
        redis_stage=$(mktemp -d "$cache/redis.XXXXXXXX")
        # SAVE completes the RDB before copying it; the Redis dataset is bounded.
        timeout 60 docker exec marinkino-redis redis-cli -e SAVE
        docker cp marinkino-redis:/data/dump.rdb "$redis_stage/redis.rdb"
        rclone copyto "$redis_stage/redis.rdb" "gdrive:MarinKino-redis/$stamp.rdb" "${common[@]}"
        rm -rf -- "$redis_stage"
        redis_stage=''
    else
        echo 'Redis is not running; no new Redis snapshot was created.'
    fi
fi
# Preserve replaced/deleted destination files outside the mirror itself.
# --links stores certificate symlinks without following them.
rclone sync "$project" gdrive:MarinKino \
    --exclude-from "$project/scripts/rclone/rclone-ignore.txt" \
    --links --metadata --backup-dir "gdrive:MarinKino-history/$stamp" \
    --max-delete 500 --modify-window 5s "${common[@]}"
find "$logs" -maxdepth 1 -type f -name 'rclone_sync_*.log' -mtime +14 -delete

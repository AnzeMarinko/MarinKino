#!/usr/bin/env bash
# Root-owned installed copy is invoked by /etc/cron.d/marinkino-security.
set -Eeuo pipefail
PATH=/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin
export PATH
umask 077
project=''
certificates_only=0
while (($#)); do
    case "$1" in
        --project) project=$2; shift 2 ;;
        --certificates-only) certificates_only=1; shift ;;
        *) echo "Unknown option: $1" >&2; exit 2 ;;
    esac
done
[[ $EUID == 0 && -n "$project" ]] || { echo 'Run as root with --project /absolute/project/path' >&2; exit 2; }
project=$(realpath -- "$project")
[[ -f "$project/docker-compose.yml" && -f "$project/.env" ]] || exit 2
helper_dir=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)
config="$helper_dir/security_config.py"
runtime="$helper_dir/security_runtime.py"
state=/var/lib/marinkino-security
install -d -m 700 "$state" /var/backups/marinkino /etc/marinkino-security
exec 9>/run/lock/marinkino-security.lock
flock -n 9 || { echo 'Security maintenance already running'; exit 0; }
exec >>/var/log/marinkino-security.log 2>&1
chmod 600 /var/log/marinkino-security.log
printf '\n[%s] Security maintenance started\n' "$(date -Is)"
cd -- "$project"
compose=(docker compose --project-directory "$project")
value() { python3 "$config" value --project "$project" "$1"; }
publish_admin_logs() {
    if [[ -f "$helper_dir/export_admin_logs.py" ]]; then
        python3 "$helper_dir/export_admin_logs.py" --project "$project" || logger -t marinkino-security 'Admin diagnostics export failed'
    fi
}
renew_certificates() {
    "${compose[@]}" run --rm --no-deps certbot renew --non-interactive --webroot -w /var/www/certbot
    if "${compose[@]}" ps --status running --services | grep -qx nginx; then
        "${compose[@]}" exec -T nginx nginx -t
        "${compose[@]}" exec -T nginx nginx -s reload
    fi
}
if ((certificates_only)); then
    renew_certificates
    printf '[%s] Certificate check successful\n' "$(date -Is)"
    publish_admin_logs
    exit 0
fi
stamp=$(date -u +%Y%m%dT%H%M%SZ)
work=$(mktemp -d "$state/run.XXXXXXXX")
deploy_started=0
rollback_available=0
encrypted_temporary=''
cleanup() {
    result=$?
    trap - EXIT
    if ((result != 0)); then
        logger -t marinkino-security "Maintenance failed; inspect /var/log/marinkino-security.log" || true
        printf '[%s] FAILED (%s); inspect this log\n' "$(date -Is)" "$result"
        if ((deploy_started && rollback_available)); then
            # Preserve the actual failure before rollback replaces containers.
            echo 'Deployment diagnostics before rollback'
            "${compose[@]}" ps -a || true
            "${compose[@]}" logs --no-color --tail=40 app nginx || true
            if [[ -f "$project/cache/logs/nginx/error.log" && ! -L "$project/cache/logs/nginx/error.log" ]]; then
                tail -n 40 "$project/cache/logs/nginx/error.log" || true
            fi
            echo 'Restoring previous running images, environment, mounts and Nginx configuration'
            if [[ -f "$work/previous-app.conf" ]]; then
                install -m 644 "$work/previous-app.conf" "$project/configuration/nginx/conf/app.conf"
            fi
            if python3 "$runtime" verify-snapshot --input "$work/previous-compose.json"; then
                "${compose[@]}" stop app nginx redis redis-auth || true
                "${compose[@]}" rm -f app nginx redis redis-auth || true
                docker compose -f "$work/previous-compose.json" up -d --no-build || echo 'ROLLBACK FAILED: restore previous release manually'
            else
                echo 'ROLLBACK UNAVAILABLE: retaining existing containers and recovery images'
            fi
        fi
    fi
    # Retain all candidate/recovery images after a failed deployment.
    if ((result == 0)); then
        python3 "$runtime" prune --state "$state" --keep "$work/previous-compose.json" || true
    fi
    rm -rf -- "$work/backup" "$work/image.tar" "$work/nginx" "$work/trivy-tmp"
    if [[ -n "$encrypted_temporary" ]]; then rm -f -- "$encrypted_temporary"; fi
    # Keep failed snapshots (contain credentials) private for manual recovery.
    if ((result == 0)); then
        rm -rf -- "$work"
    fi
    publish_admin_logs || true
    exit "$result"
}
trap cleanup EXIT
python3 "$runtime" snapshot --project "$project" --output "$work/previous-compose.json"
if [[ -s "$work/previous-compose.json" ]]; then rollback_available=1; fi
if [[ -f configuration/nginx/conf/app.conf ]]; then
    cp -- configuration/nginx/conf/app.conf "$work/previous-app.conf"
fi
# Backup is encrypted before any package or deployment change.
identity=/etc/marinkino-security/backup.agekey
if [[ ! -f "$identity" ]]; then
    age-keygen -o "$identity"
    chmod 600 "$identity"
fi
recipient=$(age-keygen -y "$identity")
python3 "$config" backup --project "$project" --destination "$work/backup"
encrypted_temporary=$(mktemp "/var/backups/marinkino/.$stamp.XXXXXXXX.tmp")
tar -C "$work/backup" -cf - . | age -r "$recipient" >"$encrypted_temporary"
mv -- "$encrypted_temporary" "/var/backups/marinkino/$stamp.tar.age"
encrypted_temporary=''
rm -rf -- "$work/backup"
find /var/backups/marinkino -maxdepth 1 -type f -name '*.tar.age' -mtime +14 -delete
export DEBIAN_FRONTEND=noninteractive NEEDRESTART_MODE=a
apt-get -o DPkg::Lock::Timeout=300 update
apt-get -o DPkg::Lock::Timeout=300 -o Dpkg::Options::=--force-confold upgrade --with-new-pkgs -y
uid=$(value MARINKINO_UID)
gid=$(value MARINKINO_GID)
[[ "$uid" =~ ^[1-9][0-9]*$ && "$gid" =~ ^[1-9][0-9]*$ ]] || { echo 'Invalid runtime UID/GID; run setup.sh'; exit 2; }
python3 "$runtime" check-uid --project "$project" --uid "$uid" --gid "$gid"
python3 "$config" prepare --project "$project" --uid "$uid" --gid "$gid"
python3 "$config" firewall --project "$project" --apply
python3 "$helper_dir/vendor_assets.py" --project "$project" --refresh
"${compose[@]}" pull nginx
docker pull aquasec/trivy:latest
candidate="marinkino-app:security-$stamp"
redis_candidate="marinkino-redis:security-$stamp"
certbot_candidate="marinkino-certbot:security-$stamp"
docker build --pull --no-cache --tag "$redis_candidate" "$project/configuration/redis"
docker build --pull --no-cache --tag "$certbot_candidate" "$project/configuration/certbot-image"
export MARINKINO_REDIS_IMAGE="$redis_candidate"
export MARINKINO_CERTBOT_IMAGE="$certbot_candidate"
export MARINKINO_APP_IMAGE="$candidate" UPDATE_DEPENDENCIES=1 SECURITY_REFRESH="$stamp"
"${compose[@]}" build --pull app
python3 "$runtime" audit --image "$candidate"
# Scan images from a read-only tar file; scanner never receives Docker socket.
# Database downloads and layer extraction exceed a small tmpfs. Use private
# disk scratch space, removed by cleanup on success/failure, instead of RAM.
install -d -m 700 "$state/trivy" "$work/trivy-tmp"
for image in "$candidate" nginx:stable-alpine "$redis_candidate" "$certbot_candidate"; do
    printf '\nScanning image: %s\n' "$image"
    docker image save -o "$work/image.tar" "$image"
    docker run --rm --read-only --cap-drop ALL --security-opt no-new-privileges \
        --memory 1024m --cpus 1 \
        -v "$work/trivy-tmp:/tmp" \
        -v "$work/image.tar:/scan/image.tar:ro" -v "$state/trivy:/root/.cache/trivy" \
        aquasec/trivy:latest image --input /scan/image.tar --scanners vuln \
        --severity HIGH,CRITICAL --ignore-unfixed --exit-code 1 --parallel 1 --timeout 15m
    rm -f -- "$work/image.tar"
done
# Verify the packaged CLI before touching the existing certificate tree.
# Certbot initializes a temporary log even when only reporting its version.
docker run --rm --read-only --network none --cap-drop ALL --security-opt no-new-privileges \
    --tmpfs /tmp:size=16m,mode=1777,nosuid,nodev,noexec \
    "$certbot_candidate" --version
renew_certificates
python3 "$runtime" smoke --image "$candidate" --uid "$uid" --gid "$gid"
install -d -m 700 "$work/nginx"
python3 "$config" render-nginx --project "$project" --output "$work/nginx/app.conf"
# nginx -t initializes/chowns its temporary paths; mirror runtime capabilities.
docker run --rm --read-only --cap-drop ALL \
    --cap-add NET_BIND_SERVICE --cap-add CHOWN --cap-add SETUID --cap-add SETGID --cap-add DAC_OVERRIDE \
    --security-opt no-new-privileges \
    --tmpfs /var/cache/nginx --tmpfs /run \
    -v "$work/nginx:/etc/nginx/conf.d:ro" \
    -v "$project/configuration/certbot/conf:/etc/letsencrypt:ro" \
    nginx:stable-alpine nginx -t
# The old containers keep serving throughout all downloads, builds and tests.
if ((rollback_available)); then
    python3 "$runtime" verify-snapshot --input "$work/previous-compose.json"
fi
deploy_started=1
python3 "$runtime" migrate-redis --project "$project"
unset MARINKINO_REDIS_VOLUME
install -m 644 "$work/nginx/app.conf" configuration/nginx/conf/app.conf
"${compose[@]}" up -d --no-build --wait --wait-timeout 180 redis redis-auth app nginx
"${compose[@]}" exec -T nginx sh -ec 'test -S /run/marinkino/app.sock || { echo "Nginx cannot see the shared application socket" >&2; exit 1; }'
python3 "$runtime" expire-legacy-stats --project "$project"
"${compose[@]}" exec -T nginx nginx -t
"${compose[@]}" exec -T nginx nginx -s reload
www=$(value WWW_DOMAIN)
curl --fail --silent --show-error --connect-timeout 5 --max-time 15 --retry 3 --retry-delay 2 \
    --resolve "$www:443:127.0.0.1" "https://$www/healthz"
docker tag "$candidate" marinkino-app:current
docker tag "$redis_candidate" marinkino-redis:current
docker tag "$certbot_candidate" marinkino-certbot:current
# Persist the last successful runtime inventory and a rollback snapshot.
python3 "$runtime" snapshot --project "$project" --output "$state/current-compose.json"
if [[ -f "$work/previous-compose.json" ]]; then
    install -m 600 "$work/previous-compose.json" "$state/previous-compose.json"
fi
if [[ -f "$work/previous-app.conf" ]]; then
    install -m 600 "$work/previous-app.conf" "$state/previous-app.conf"
fi
deploy_started=0
python3 "$config" firewall --project "$project" --apply
# Only untagged image layers are pruned; current and rollback images survive.
# Retention is explicit: never prune volumes or operator-owned images.
find "$state" -maxdepth 1 -type d -name 'run.*' -mtime +14 -exec rm -rf -- {} +
printf '{"last_success":"%s","image":"%s","reboot_required":%s}\n' \
    "$(date -u +%FT%TZ)" "$candidate" "$([[ -f /var/run/reboot-required ]] && echo true || echo false)" >"$state/status.json"
printf '\n[%s] Security maintenance successful. Reboot is never automatic.\n' "$(date -Is)"

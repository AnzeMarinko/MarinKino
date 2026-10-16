#!/usr/bin/env bash
# Idempotent Raspberry Pi / Debian installation. Run from the project checkout.
# run with: sudo --preserve-env=SSH_CONNECTION bash scripts/setup.sh
set -Eeuo pipefail
PATH=/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin
export PATH
umask 077
project=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)
[[ $(uname -s) == Linux ]] || { echo 'setup.sh runs on the Linux server, not the development Mac.' >&2; exit 2; }
[[ $EUID == 0 ]] || { echo 'Run: sudo bash scripts/setup.sh' >&2; exit 2; }
[[ -f "$project/.env" ]] || { echo 'Create .env from .env.example first.' >&2; exit 2; }
command -v docker >/dev/null && docker compose version >/dev/null || { echo 'Docker Engine + Docker Compose v2 must already be installed.' >&2; exit 2; }
cd -- "$project"
export DEBIAN_FRONTEND=noninteractive NEEDRESTART_MODE=a
apt-get -o DPkg::Lock::Timeout=300 update
apt-get -o DPkg::Lock::Timeout=300 install -y --no-install-recommends \
    python3 ca-certificates curl cron logrotate fail2ban nftables iptables iproute2 age rclone
runtime_uid=$(python3 scripts/security_config.py value --project "$project" MARINKINO_UID)
runtime_gid=$(python3 scripts/security_config.py value --project "$project" MARINKINO_GID)
runtime_uid=${runtime_uid:-${SUDO_UID:-$(stat -c %u .env)}}
runtime_gid=${runtime_gid:-${SUDO_GID:-$(stat -c %g .env)}}
if [[ "$runtime_uid" == 0 || "$runtime_gid" == 0 ]]; then runtime_uid=10001; runtime_gid=10001; fi
python3 scripts/security_config.py prepare --project "$project" --uid "$runtime_uid" --gid "$runtime_gid"
# Cron and systemd execute root-owned snapshots, not user-writable scripts.
install -d -o root -g root -m 755 /usr/local/lib/marinkino
for helper in security_config.py security_runtime.py vendor_assets.py secure_backup.py; do
    install -o root -g root -m 644 "scripts/$helper" "/usr/local/lib/marinkino/$helper"
done
install -o root -g root -m 644 src/admin_log_reader.py /usr/local/lib/marinkino/admin_log_reader.py
install -o root -g root -m 644 scripts/export_admin_logs.py /usr/local/lib/marinkino/export_admin_logs.py
install -o root -g root -m 755 scripts/security-update.sh /usr/local/lib/marinkino/security-update.sh
install -o root -g root -m 755 scripts/duckdns_refresh.sh /usr/local/lib/marinkino/duckdns_refresh.sh
install -o root -g root -m 755 scripts/rclone/rclone-sync-gdrive.sh /usr/local/lib/marinkino/rclone-sync-gdrive.sh
if [[ -f /etc/marinkino-security/rclone.conf ]]; then
    python3 /usr/local/lib/marinkino/secure_backup.py init
fi
value() { python3 /usr/local/lib/marinkino/security_config.py value --project "$project" "$1"; }
main=$(value MAIN_DOMAIN)
www=$(value WWW_DOMAIN)
email=$(value GMAIL_USERNAME)
duck=$(value DUCKDNS_DOMAIN)
bootstrap_id=''
cleanup_bootstrap() {
    if [[ -n "$bootstrap_id" ]]; then docker rm -f "$bootstrap_id" >/dev/null 2>&1 || true; fi
}
trap cleanup_bootstrap EXIT
if [[ ! -s "configuration/certbot/conf/live/$main/fullchain.pem" ]]; then
    [[ -n "$email" ]] || { echo 'GMAIL_USERNAME required for certificate registration.' >&2; exit 2; }
    install -d -m 755 configuration/nginx/conf configuration/certbot/www configuration/certbot/conf
    python3 scripts/security_config.py render-nginx --project "$project" --bootstrap
    docker pull nginx:stable-alpine
    docker build --pull --no-cache --tag marinkino-certbot:bootstrap "$project/configuration/certbot-image"
    # No app socket volume is mounted before the unprivileged app initializes it.
    bootstrap_id=$(docker run -d --name marinkino-bootstrap --read-only \
        --cap-drop ALL --cap-add NET_BIND_SERVICE --cap-add CHOWN --cap-add SETUID --cap-add SETGID \
        --tmpfs /var/cache/nginx --tmpfs /run -p 80:80 \
        -v "$project/configuration/nginx/conf:/etc/nginx/conf.d:ro" \
        -v "$project/configuration/certbot/www:/var/www/certbot:ro" nginx:stable-alpine)
    domains=(-d "$main")
    [[ "$www" == "$main" ]] || domains+=(-d "$www")
    if [[ -n "$duck" && "$duck" != "$main" && "$duck" != "$www" ]]; then domains+=(-d "$duck"); fi
    if [[ -n "$duck" ]]; then /usr/local/lib/marinkino/duckdns_refresh.sh --project "$project"; fi
    MARINKINO_CERTBOT_IMAGE=marinkino-certbot:bootstrap docker compose run --rm --no-deps certbot certonly --non-interactive \
        --webroot -w /var/www/certbot --cert-name "$main" "${domains[@]}" \
        --email "$email" --agree-tos
    cleanup_bootstrap
    bootstrap_id=''
fi
# Remove the old infinite Certbot loop if it exists. Renewal is now one-shot.
if docker inspect marinkino-certbot >/dev/null 2>&1; then
    docker stop marinkino-certbot
    docker rm marinkino-certbot
fi
# Create the read-only diagnostics mount before Compose starts the new app.
python3 /usr/local/lib/marinkino/export_admin_logs.py --project "$project"
/usr/local/lib/marinkino/security-update.sh --project "$project"
# Preserve SSH_CONNECTION with sudo -E if connecting through public SSH/VPN.
python3 /usr/local/lib/marinkino/security_config.py install-host --project "$project"
fail2ban-client -t
systemctl enable --now cron fail2ban
systemctl restart fail2ban
# Write managed system cron; escape paths and cron's special percent character.
python3 - "$project" <<'PY'
import os
import shlex
import sys
from pathlib import Path
project = shlex.quote(sys.argv[1]).replace('%', r'\%')
script = '/usr/local/lib/marinkino/security-update.sh --project ' + project
lines = [
    'SHELL=/bin/bash',
    'PATH=/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin',
    '17 3 * * * root ' + script,
    '11 5,17 * * * root ' + script + ' --certificates-only',
    '*/5 * * * * root /usr/bin/python3 /usr/local/lib/marinkino/security_config.py firewall --project ' + project + ' --apply || /usr/bin/logger -t marinkino-security "Firewall refresh failed"',
    '*/10 * * * * root /usr/local/lib/marinkino/duckdns_refresh.sh --project ' + project + ' >/dev/null 2>&1',
    '* * * * * root /usr/bin/python3 /usr/local/lib/marinkino/export_admin_logs.py --project ' + project + ' >/dev/null 2>&1 || /usr/bin/logger -t marinkino-security "Admin diagnostics export failed"',
]
path = Path('/etc/cron.d/marinkino-security')
if Path('/etc/marinkino-security/rclone.conf').is_file():
    lines.append('0 7 * * * root /usr/local/lib/marinkino/rclone-sync-gdrive.sh --project ' + project + ' || /usr/bin/logger -t marinkino-security "Google Drive backup failed"')
path.write_text('\n'.join(lines) + '\n')
os.chown(path, 0, 0)
path.chmod(0o644)
PY
cat >/etc/logrotate.d/marinkino-security <<'EOF'
/var/log/marinkino-security.log {
    daily
    rotate 14
    compress
    delaycompress
    missingok
    notifempty
    copytruncate
    create 0600 root root
}
EOF
chmod 644 /etc/logrotate.d/marinkino-security
# Remove only legacy cron entries created by this repository's previous setup.
python3 - "$project" "${SUDO_USER:-root}" <<'PY'
import subprocess
import sys
from pathlib import Path
for user in dict.fromkeys(['root', sys.argv[2]]):
    result = subprocess.run(['crontab', '-u', user, '-l'], capture_output=True, text=True)
    if result.returncode:
        continue
    retained = [line for line in result.stdout.splitlines() if not (
        sys.argv[1] in line and (
            'scripts/duckdns_refresh.sh' in line or 'docker compose run --rm certbot renew' in line
            or (Path('/etc/marinkino-security/rclone.conf').is_file() and 'scripts/rclone/rclone-sync-gdrive.sh' in line)
        )
    )]
    if retained != result.stdout.splitlines():
        subprocess.run(['crontab', '-u', user, '-'], input='\n'.join(retained) + '\n', text=True, check=True)
PY
python3 /usr/local/lib/marinkino/export_admin_logs.py --project "$project"
printf 'Ready: https://%s\nCron: /etc/cron.d/marinkino-security\nLog: /var/log/marinkino-security.log\nBackup key: /etc/marinkino-security/backup.agekey (copy off server)\n' "$www"

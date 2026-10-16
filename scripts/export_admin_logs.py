#!/usr/bin/env python3
"""Publish bounded host diagnostics without granting Flask host access."""

from __future__ import annotations

import argparse
import fcntl
import json
import os
import selectors
import stat
import subprocess
import time
from datetime import datetime, timezone
from pathlib import Path

import security_config as config

from admin_log_reader import (
    MAX_LOG_BYTES,
    MAX_SNAPSHOT_BYTES,
    file_entry,
    redact,
    secret_values,
    tail_text,
)

DESTINATION = Path("/var/lib/marinkino-observability/overview.json")


def command_output(command, timeout=5):
    """Bound runtime and output even when a single log line is enormous."""
    payload = bytearray()
    deadline = time.monotonic() + timeout
    with subprocess.Popen(
        command,
        stdin=subprocess.DEVNULL,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        env={"PATH": "/usr/sbin:/usr/bin:/sbin:/bin", "LC_ALL": "C.UTF-8"},
    ) as process:
        try:
            with selectors.DefaultSelector() as selector:
                selector.register(process.stdout, selectors.EVENT_READ)
                while True:
                    remaining = deadline - time.monotonic()
                    if remaining <= 0 or not selector.select(remaining):
                        raise subprocess.TimeoutExpired(command, timeout)
                    chunk = os.read(
                        process.stdout.fileno(),
                        min(8192, MAX_LOG_BYTES + 1 - len(payload)),
                    )
                    if not chunk:
                        break
                    payload.extend(chunk)
                    if len(payload) > MAX_LOG_BYTES:
                        raise ValueError("Izpis presega omejitev 64 KiB.")
            process.wait(timeout=max(0.01, deadline - time.monotonic()))
            return tail_text(payload), process.returncode == 0
        except (subprocess.TimeoutExpired, ValueError):
            process.kill()
            process.wait()
            return tail_text(
                payload[:MAX_LOG_BYTES]
            ) + "\n[Izpis omejen ali čas preizkusa potekel.]", False
        except BaseException:
            process.kill()
            process.wait()
            raise


def latest_files(directory, pattern, count):
    """Pin the directory, ignore symlinks and cap directory listings."""
    found = []
    try:
        with config.directory_descriptor(directory) as descriptor:
            with os.scandir(descriptor) as listing:
                for index, item in enumerate(listing):
                    if index >= 4096:
                        break
                    if not Path(item.name).match(pattern):
                        continue
                    info = item.stat(follow_symlinks=False)
                    if stat.S_ISREG(info.st_mode):
                        found.append((info.st_mtime_ns, item.name))
    except (OSError, ValueError):
        return []
    return [
        directory / name for _, name in sorted(found, reverse=True)[:count]
    ]


def collect(project, values, run=command_output):
    secrets = secret_values(values)
    logs = project / "cache/logs"
    entries = [
        file_entry(
            "updates",
            "Posodobitve in certifikati",
            Path("/var/log/marinkino-security.log"),
            secrets,
        ),
        file_entry(
            "maintenance",
            "Zadnja uspešna nadgradnja",
            Path("/var/lib/marinkino-security/status.json"),
            secrets,
        ),
        file_entry(
            "nginx-error", "Nginx · napake", logs / "nginx/error.log", secrets
        ),
        file_entry(
            "nginx-access",
            "Nginx · dostopi",
            logs / "nginx/access.log",
            secrets,
        ),
    ]
    rclone_logs = latest_files(logs / "rclone", "rclone_sync_*.log", 3)
    for index, path in enumerate(rclone_logs, 1):
        entries.append(
            file_entry(
                f"rclone-{index}",
                f"Rclone · zadnji zagon {index}",
                path,
                secrets,
            )
        )
    if not rclone_logs:
        entries.append(
            dict(
                id="rclone-1",
                title="Rclone",
                available=False,
                text="Dnevnik trenutno ni na voljo.",
            )
        )
    commands = [
        (
            "cloud-encryption",
            "Oblačne kopije · šifriranje",
            ["python3", "/usr/local/lib/marinkino/secure_backup.py", "check"],
        ),
        (
            "containers",
            "Vsebniki · stanje",
            [
                "docker",
                "ps",
                "--all",
                "--filter",
                "name=^/marinkino-",
                "--format",
                "table {{.Names}}\t{{.Status}}\t{{.Image}}",
            ],
        ),
        (
            "host",
            "SSH, Fail2Ban in požarni zid",
            [
                "journalctl",
                "--no-pager",
                "-o",
                "short-iso",
                "--since=-24h",
                "-n",
                "200",
                "-u",
                "ssh.service",
                "-u",
                "sshd.service",
                "-u",
                "fail2ban.service",
                "-u",
                "marinkino-firewall.service",
            ],
        ),
        ("fail2ban", "Fail2Ban · stanje", ["fail2ban-client", "status"]),
        (
            "fail2ban-ssh",
            "Fail2Ban · SSH",
            ["fail2ban-client", "status", "sshd"],
        ),
        (
            "fail2ban-app",
            "Fail2Ban · prijave",
            ["fail2ban-client", "status", "marinkino-auth"],
        ),
        (
            "redis",
            "Redis · dogodki",
            [
                "docker",
                "logs",
                "--tail",
                "200",
                "--since",
                "24h",
                "marinkino-redis",
            ],
        ),
        (
            "redis-auth",
            "Redis prijav · dogodki",
            [
                "docker",
                "logs",
                "--tail",
                "200",
                "--since",
                "24h",
                "marinkino-redis-auth",
            ],
        ),
    ]
    for identifier, title, command in commands:
        try:
            text, available = run(command)
            text = redact(text, secrets) or "Brez dogodkov."
        except OSError:
            text, available = "Pregled trenutno ni na voljo.", False
        entries.append(
            dict(id=identifier, title=title, available=available, text=text)
        )
    backups = latest_files(Path("/var/backups/marinkino"), "*.tar.age", 5)
    entries.append(
        dict(
            id="backups",
            title="Šifrirane varnostne kopije",
            available=bool(backups),
            text="\n".join(path.name for path in backups)
            or "Varnostne kopije še niso na voljo.",
        )
    )
    return dict(
        generated_at=datetime.now(timezone.utc).isoformat(), entries=entries
    )


def publish(project, destination=DESTINATION):
    values = config.read_env(project)
    gid = int(values["MARINKINO_GID"])
    if not 0 < gid < 2**31:
        raise ValueError("Invalid runtime group")
    config.ensure_directory(destination.parent, 0o750, os.geteuid(), gid)
    document = collect(project, values)
    payload = (json.dumps(document, ensure_ascii=False) + "\n").encode()
    if len(payload) > MAX_SNAPSHOT_BYTES:
        raise ValueError("Diagnostics exceed the snapshot limit")
    config.atomic_write(destination, payload, 0o640)
    config.set_permissions(destination, 0o640, os.geteuid(), gid)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--project", required=True)
    args = parser.parse_args()
    if os.geteuid() != 0:
        parser.error("Run the installed exporter as root")
    descriptor = os.open(
        "/run/lock/marinkino-admin-logs.lock",
        os.O_WRONLY | os.O_CREAT | os.O_NOFOLLOW | os.O_CLOEXEC,
        0o600,
    )
    try:
        try:
            fcntl.flock(descriptor, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            return
        publish(config.project_path(args.project))
    finally:
        os.close(descriptor)


if __name__ == "__main__":
    main()

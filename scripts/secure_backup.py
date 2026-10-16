#!/usr/bin/env python3
"""Create and validate the dedicated encrypted cloud backup destination."""

from __future__ import annotations

import argparse
import configparser
import fcntl
import hashlib
import io
import os
import re
import secrets
import stat
import subprocess
import sys
from pathlib import Path

from security_config import atomic_write, directory_descriptor, safe_descriptor

REMOTE = "marinkino_secure"
DESTINATION = "gdrive:MarinKino-encrypted"
DEFAULT_CONFIG = Path("/etc/marinkino-security/rclone.conf")
MAX_CONFIG_BYTES = 1024 * 1024


def clean_environment():
    return {
        name: value
        for name, value in os.environ.items()
        if not name.upper().startswith("RCLONE_")
    }


def read_configuration(path):
    with safe_descriptor(path, regular=True) as descriptor:
        info = os.fstat(descriptor)
        if info.st_uid != os.geteuid() or stat.S_IMODE(info.st_mode) & 0o077:
            raise ValueError(
                "Backup config must be owned by its caller and mode 0600"
            )
        payload = os.read(descriptor, MAX_CONFIG_BYTES + 1)
    if len(payload) > MAX_CONFIG_BYTES:
        raise ValueError("Backup config exceeds size limit")
    parser = configparser.ConfigParser(interpolation=None)
    parser.read_string(payload.decode("utf-8"))
    if (
        parser.defaults()
        or parser.get("gdrive", "type", fallback="") != "drive"
    ):
        raise ValueError("A dedicated gdrive remote of type drive is required")
    return parser, payload


def validate(parser):
    required = {
        "type": "crypt",
        "remote": DESTINATION,
        "filename_encryption": "standard",
        "directory_name_encryption": "true",
        "no_data_encryption": "false",
    }
    if not parser.has_section(REMOTE):
        raise ValueError(
            "Encrypted remote missing; run secure_backup.py init first"
        )
    section = parser[REMOTE]
    if any(section.get(name, "") != value for name, value in required.items()):
        raise ValueError(
            "Encrypted backup settings changed; refusing an unsafe destination"
        )
    for name in ("password", "password2"):
        if not re.fullmatch(r"[A-Za-z0-9_-]{40,2048}", section.get(name, "")):
            raise ValueError("Encrypted backup keys are missing or invalid")


def obscure(password):
    # Secrets go through stdin, never argv, environment or application logs.
    result = subprocess.run(
        ["rclone", "--config", "/dev/null", "obscure", "-"],
        input=password + "\n",
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.DEVNULL,
        timeout=15,
        check=True,
        env=clean_environment(),
    )
    value = result.stdout.strip()
    if not re.fullmatch(r"[A-Za-z0-9_-]{40,2048}", value):
        raise ValueError("Failed to prepare the encrypted backup key")
    return value


def pin_path(path):
    return path.with_name(f".{path.name}.crypt-sha256")


def fingerprint(parser):
    section = parser[REMOTE]
    payload = "\n".join(f"{key}={section[key]}" for key in sorted(section))
    return hashlib.sha256(payload.encode()).hexdigest()


def verify_pin(path, parser):
    with safe_descriptor(pin_path(path), regular=True) as descriptor:
        info = os.fstat(descriptor)
        if info.st_uid != os.geteuid() or stat.S_IMODE(info.st_mode) & 0o077:
            raise ValueError("Unsafe encryption fingerprint permissions")
        recorded = os.read(descriptor, 256).decode().strip()
    if not secrets.compare_digest(recorded, fingerprint(parser)):
        raise ValueError(
            "Backup keys changed; restore the saved configuration"
        )


def initialize(path):
    # Parallel setup must never generate two independent backup keys.
    with directory_descriptor(path.parent) as parent:
        descriptor = os.open(
            f".{path.name}.init.lock",
            os.O_RDWR | os.O_CREAT | os.O_NOFOLLOW | os.O_NONBLOCK,
            0o600,
            dir_fd=parent,
        )
        try:
            if not stat.S_ISREG(os.fstat(descriptor).st_mode):
                raise ValueError("Unsafe config lock")
            fcntl.flock(descriptor, fcntl.LOCK_EX)
            return initialize_locked(path)
        finally:
            os.close(descriptor)


def initialize_locked(path):
    parser, _ = read_configuration(path)
    if parser.has_section(REMOTE):
        validate(parser)
        if pin_path(path).exists():
            verify_pin(path, parser)
        else:
            atomic_write(pin_path(path), fingerprint(parser) + "\n")
        return False  # Never rotate keys implicitly on a repeated setup.
    if pin_path(path).exists():
        raise ValueError("Backup keys were removed; restore rclone.conf")
    parser[REMOTE] = {
        "type": "crypt",
        "remote": DESTINATION,
        "filename_encryption": "standard",
        "directory_name_encryption": "true",
        "no_data_encryption": "false",
        "password": obscure(secrets.token_urlsafe(48)),
        "password2": obscure(secrets.token_urlsafe(48)),
    }
    validate(parser)
    output = io.StringIO()
    parser.write(output)
    atomic_write(path, output.getvalue(), 0o600)
    atomic_write(pin_path(path), fingerprint(parser) + "\n")
    return True


def snapshot(source, destination):
    parser, payload = read_configuration(source)
    validate(parser)
    verify_pin(source, parser)
    # Each transfer uses this immutable private copy, avoiding config races.
    atomic_write(destination, payload, 0o600)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=("init", "check", "snapshot"))
    parser.add_argument("--config", type=Path, default=DEFAULT_CONFIG)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args(argv)
    try:
        if args.action == "init":
            initialize(args.config)
            print("Encrypted backup configured; save rclone.conf off the Pi.")
        elif args.action == "snapshot":
            if (
                args.output is None
                or args.output.absolute() == args.config.absolute()
            ):
                raise ValueError(
                    "A separate private config snapshot is required"
                )
            snapshot(args.config, args.output)
        else:
            config, _ = read_configuration(args.config)
            validate(config)
            verify_pin(args.config, config)
            print("Encrypted backup destination verified.")
        return 0
    except (
        OSError,
        ValueError,
        configparser.Error,
        subprocess.SubprocessError,
    ):
        # Never echo a config parser error: it can contain credential values.
        print(
            "Secure backup config invalid. Check mode 0600 and run "
            "secure_backup.py init. If keys changed, restore the saved "
            "rclone.conf; no upload allowed.",
            file=sys.stderr,
        )
        return 2


if __name__ == "__main__":
    raise SystemExit(main())

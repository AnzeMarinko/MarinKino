"""Encryption policy, key persistence and real local rclone round trips."""

import importlib.util
import os
import shutil
import subprocess
import sys
from pathlib import Path
from unittest.mock import patch

import pytest
from test_security_config import security

SOURCE = Path(__file__).resolve().parents[1] / "scripts/secure_backup.py"
spec = importlib.util.spec_from_file_location("secure_backup_test", SOURCE)
secure = importlib.util.module_from_spec(spec)
with patch.dict(sys.modules, {"security_config": security}):
    spec.loader.exec_module(secure)


@pytest.fixture
def config(tmp_path):
    path = tmp_path / "rclone.conf"
    path.write_text(
        '[gdrive]\ntype=drive\ntoken={"access_token":"SENTINEL"}\n'
    )
    path.chmod(0o600)
    return path


def test_init_preserves_existing_keys_and_credentials(config, monkeypatch):
    generated = []

    def obscure(value):
        generated.append(value)
        return "A" * 64 if len(generated) == 1 else "B" * 64

    monkeypatch.setattr(secure, "obscure", obscure)
    assert secure.initialize(config)
    before = config.read_bytes()
    assert not secure.initialize(config)
    assert config.read_bytes() == before
    assert len(generated) == 2 and generated[0] != generated[1]
    assert min(map(len, generated)) >= 64
    assert b"SENTINEL" in before
    assert config.stat().st_mode & 0o777 == 0o600


@pytest.mark.parametrize(
    "name,value",
    [
        ("type", "drive"),
        ("remote", "gdrive:MarinKino"),
        ("no_data_encryption", "true"),
        ("filename_encryption", "off"),
        ("directory_name_encryption", "false"),
        ("password", ""),
    ],
)
def test_unsafe_settings_fail_closed_without_rotating_keys(
    config, monkeypatch, name, value
):
    monkeypatch.setattr(secure, "obscure", lambda _: "A" * 64)
    secure.initialize(config)
    parser, _ = secure.read_configuration(config)
    parser[secure.REMOTE][name] = value
    with config.open("w") as stream:
        parser.write(stream)
    before = config.read_bytes()
    with pytest.raises(ValueError):
        secure.initialize(config)
    assert config.read_bytes() == before


def test_snapshot_is_private_and_independent_of_future_config_changes(
    config, monkeypatch, tmp_path
):
    monkeypatch.setattr(secure, "obscure", lambda _: "A" * 64)
    secure.initialize(config)
    destination = tmp_path / "snapshot.conf"
    secure.snapshot(config, destination)
    config.write_text("BROKEN_CONFIG")
    parser, _ = secure.read_configuration(destination)
    secure.validate(parser)
    assert destination.stat().st_mode & 0o777 == 0o600


def test_world_readable_and_symlink_configs_are_rejected(config, tmp_path):
    config.chmod(0o644)
    with pytest.raises(ValueError):
        secure.read_configuration(config)
    config.chmod(0o600)
    link = tmp_path / "link.conf"
    link.symlink_to(config)
    with pytest.raises((OSError, ValueError)):
        secure.read_configuration(link)


def test_config_parse_errors_do_not_print_secrets(config, capsys):
    config.write_text("[gdrive]\nUNEXPECTED-SUPER-SECRET-LINE\n")
    assert secure.main(["check", "--config", str(config)]) == 2
    assert "UNEXPECTED-SUPER-SECRET-LINE" not in capsys.readouterr().err


def test_replaced_or_removed_keys_require_recovery(config, monkeypatch):
    monkeypatch.setattr(secure, "obscure", lambda _: "A" * 64)
    secure.initialize(config)
    original = config.read_bytes()
    config.write_text("[gdrive]\ntype=drive\n")
    with pytest.raises(ValueError):
        secure.initialize(config)
    config.write_bytes(original.replace(b"A" * 64, b"B" * 64))
    with pytest.raises(ValueError):
        secure.initialize(config)
    config.write_bytes(original)
    assert not secure.initialize(config)


def test_real_rclone_encrypts_content_names_and_restores_keys(
    config, tmp_path
):
    if not shutil.which("rclone"):
        pytest.skip("Optional real local rclone binary unavailable")
    assert secure.initialize(config)
    parser, _ = secure.read_configuration(config)
    # Exercise the real cipher against a disposable local backend, no Drive.
    storage = tmp_path / "ciphertext"
    parser[secure.REMOTE]["remote"] = str(storage)
    local = tmp_path / "local.conf"
    with local.open("w") as stream:
        parser.write(stream)
    local.chmod(0o600)
    original = tmp_path / "original"
    original.mkdir()
    (original / ".env").write_text("SMTP_PASSWORD=CONFIDENTIAL_SENTINEL\n")
    (original / "readme.txt").write_text("Restorable content\n")
    (original / "link").symlink_to("readme.txt")
    (original / "rclone.conf").write_text("NEVER-UPLOAD-DECRYPTION-KEYS")
    (original / "backup.agekey").write_text("NEVER-UPLOAD-AGE-IDENTITY")
    nested = original / "nested"
    nested.mkdir()
    (nested / "rclone.conf").write_text("NEVER-UPLOAD-NESTED-KEYS")
    (nested / "backup.agekey").write_text("NEVER-UPLOAD-NESTED-AGE")
    restored = tmp_path / "restored"
    filters = [
        "--exclude-from",
        str(SOURCE.parent / "rclone/rclone-ignore.txt"),
    ]

    def run(*args):
        return subprocess.run(
            ["rclone", "--config", str(local), *args],
            check=True,
            capture_output=True,
            timeout=30,
            env=secure.clean_environment(),
        )

    run("copy", str(original), f"{secure.REMOTE}:project", "--links", *filters)
    encrypted_files = [path for path in storage.rglob("*") if path.is_file()]
    assert encrypted_files
    assert not any(
        path.name in {".env", "readme.txt", "link.rclonelink"}
        for path in encrypted_files
    )
    assert all(
        b"CONFIDENTIAL_SENTINEL" not in path.read_bytes()
        for path in encrypted_files
    )
    run(
        "cryptcheck",
        str(original),
        f"{secure.REMOTE}:project",
        "--links",
        "--one-way",
        *filters,
    )
    run("copy", f"{secure.REMOTE}:project", str(restored), "--links")
    assert (restored / ".env").read_bytes() == (original / ".env").read_bytes()
    assert os.readlink(restored / "link") == "readme.txt"
    assert not (restored / "rclone.conf").exists()
    assert not (restored / "backup.agekey").exists()
    assert not (restored / "nested/rclone.conf").exists()
    assert not (restored / "nested/backup.agekey").exists()
    target = encrypted_files[0]
    payload = bytearray(target.read_bytes())
    payload[-1] ^= 1
    target.write_bytes(payload)
    with pytest.raises(subprocess.CalledProcessError):
        run(
            "cryptcheck",
            str(original),
            f"{secure.REMOTE}:project",
            "--links",
            *filters,
        )

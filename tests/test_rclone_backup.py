"""Exercise backup orchestration with fake commands and private temp paths."""

import json
import os
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "scripts/rclone/rclone-sync-gdrive.sh"


@pytest.fixture
def backup(tmp_path):
    project = tmp_path / "Project with spaces"
    filters = project / "scripts/rclone/rclone-ignore.txt"
    filters.parent.mkdir(parents=True)
    filters.write_text((ROOT / "scripts/rclone/rclone-ignore.txt").read_text())
    (project / ".env").write_text("PRIVATE_SETTING=not-for-logs\n")
    config = tmp_path / "private rclone.conf"
    config.write_text("[gdrive]\ntype=drive\n")
    archives = tmp_path / "archives"
    archives.mkdir()
    (archives / "finished.tar.age").write_bytes(b"encrypted")
    cache = tmp_path / "cache"
    calls = tmp_path / "calls.jsonl"
    # Simulate root/Linux without privileges, writes to /var, network or Drive.
    fake_bin = tmp_path / "bin"
    fake_bin.mkdir()
    fake_rclone = fake_bin / "rclone"
    fake_rclone.write_text(
        "#!/usr/bin/env python3\n"
        "import json, os, sys\n"
        "with open(os.environ['TEST_BACKUP_CALLS'], 'a') as out:\n"
        "    out.write(json.dumps(sys.argv[1:]) + '\\n')\n"
        "sys.exit(int(os.environ.get('TEST_BACKUP_FAILURE', '0')))\n"
    )
    fake_rclone.chmod(0o755)
    fake_flock = fake_bin / "flock"
    fake_flock.write_text("#!/bin/sh\nexit 0\n")
    fake_flock.chmod(0o755)
    fake_docker = fake_bin / "docker"
    fake_docker.write_text(
        "#!/usr/bin/env python3\n"
        "import os, sys\n"
        "from pathlib import Path\n"
        "if sys.argv[1] == 'inspect':\n"
        "    print(os.environ.get('TEST_REDIS_RUNNING', 'false'))\n"
        "elif sys.argv[1] == 'cp':\n"
        "    Path(sys.argv[-1]).write_bytes(b'CONSISTENT-REDIS-RDB')\n"
    )
    fake_docker.chmod(0o755)
    fake_timeout = fake_bin / "timeout"
    fake_timeout.write_text('#!/bin/sh\nshift\nexec "$@"\n')
    fake_timeout.chmod(0o755)
    harness = tmp_path / "backup.sh"
    code = SOURCE.read_text()
    code = code.replace(
        "PATH=/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin",
        f"PATH='{fake_bin}':" + os.environ["PATH"],
    ).replace("[[ $EUID == 0 ]]", "[[ 1 == 1 ]]")
    code = code.replace(
        "cache=/var/cache/marinkino-rclone", f"cache='{cache}'"
    ).replace("/var/backups/marinkino", str(archives))
    harness.write_text(code)

    def run(*extra, failure=0, redis_running=False):
        result = subprocess.run(
            [
                "bash",
                str(harness),
                "--project",
                str(project),
                "--config",
                str(config),
                *extra,
            ],
            env={
                **os.environ,
                "TEST_BACKUP_CALLS": str(calls),
                "TEST_BACKUP_FAILURE": str(failure),
                "TEST_REDIS_RUNNING": str(redis_running).lower(),
            },
            capture_output=True,
            text=True,
            timeout=5,
        )
        return result, [
            json.loads(line) for line in calls.read_text().splitlines()
        ]

    return project, run


def test_archives_copy_first_and_mirror_preserves_history_and_symlinks(backup):
    project, run = backup
    result, calls = run()
    assert result.returncode == 0, result.stderr
    assert [call[0] for call in calls] == ["copy", "sync"]
    assert calls[0][2] == "gdrive:MarinKino-backups"
    assert calls[0][calls[0].index("--include") + 1] == "*.tar.age"
    assert calls[1][1:3] == [str(project), "gdrive:MarinKino"]
    assert "--links" in calls[1] and "--copy-links" not in calls[1]
    assert calls[1][calls[1].index("--backup-dir") + 1].startswith(
        "gdrive:MarinKino-history/"
    )
    log = next((project / "cache/logs/rclone").glob("*.log"))
    assert "exit=0" in log.read_text()
    assert "not-for-logs" not in log.read_text()


def test_dry_run_applies_to_both_transfers(backup):
    _, run = backup
    result, calls = run("--dry-run")
    assert result.returncode == 0
    assert len(calls) == 2 and all("--dry-run=true" in call for call in calls)


def test_redis_snapshot_is_dated_uploaded_and_private_staging_removed(backup):
    _, run = backup
    result, calls = run(redis_running=True)
    assert result.returncode == 0, result.stderr
    assert [call[0] for call in calls] == ["copy", "copyto", "sync"]
    assert calls[1][2].startswith("gdrive:MarinKino-redis/")
    assert calls[1][2].endswith(".rdb")
    assert not Path(calls[1][1]).exists()


def test_failure_is_logged_and_stops_following_transfers(backup):
    project, run = backup
    result, calls = run(failure=7)
    assert result.returncode == 7
    assert len(calls) == 1 and calls[0][0] == "copy"
    log = next((project / "cache/logs/rclone").glob("*.log"))
    assert "exit=7" in log.read_text()


def test_full_backup_requires_privileges_before_reading_private_files():
    if os.geteuid() == 0:
        pytest.skip("Checks the unprivileged invocation")
    result = subprocess.run(
        ["bash", str(SOURCE)], capture_output=True, text=True, timeout=5
    )
    assert result.returncode == 2
    assert "Run with sudo" in result.stderr


@pytest.mark.parametrize("failure", [0, 7])
def test_archive_becomes_uploadable_only_after_encryption_success(
    tmp_path, failure
):
    backup = tmp_path / "work/backup"
    backup.mkdir(parents=True)
    (backup / ".env").write_text("DISPOSABLE_TEST_DATA=yes\n")
    archives = tmp_path / "archives"
    archives.mkdir()
    binaries = tmp_path / "bin"
    binaries.mkdir()
    age = binaries / "age"
    age.write_text(f"#!/bin/sh\ncat\nexit {failure}\n")
    age.chmod(0o755)
    source = (ROOT / "scripts/security-update.sh").read_text()
    fragment = source.split("encrypted_temporary=$(mktemp", 1)[1].split(
        'rm -rf -- "$work/backup"', 1
    )[0]
    fragment = "encrypted_temporary=$(mktemp" + fragment
    fragment = fragment.replace("/var/backups/marinkino", str(archives))
    result = subprocess.run(
        ["bash", "-c", "set -Eeuo pipefail\n" + fragment],
        env={
            **os.environ,
            "PATH": str(binaries) + ":" + os.environ["PATH"],
            "work": str(backup.parent),
            "stamp": "test-run",
            "recipient": "fake",
        },
        capture_output=True,
        timeout=5,
    )
    assert result.returncode == failure
    assert bool(list(archives.glob("*.tar.age"))) == (failure == 0)

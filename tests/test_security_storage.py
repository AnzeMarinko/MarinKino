"""Regression coverage for path confinement and shared JSON transactions."""

import json
import os
import subprocess
import sys
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import pytest

from security_storage import (
    atomic_write_json,
    locked_path,
    read_json,
    safe_resolved_path,
    serialized_json,
)


def test_paths_reject_prefix_siblings_and_symlink_escapes(tmp_path):
    base = tmp_path / "music"
    sibling = tmp_path / "music-private"
    base.mkdir()
    sibling.mkdir()
    (base / "outside").symlink_to(sibling, target_is_directory=True)
    (base / "song.mp3").touch()

    assert safe_resolved_path(base, "song.mp3") == str(base / "song.mp3")
    for name in (
        "../music-private/passwords.json",
        "outside/passwords.json",
        str(sibling / "passwords.json"),
        ".",
        "bad\x00path",
        "",
    ):
        with pytest.raises(ValueError):
            safe_resolved_path(base, name)


def test_atomic_encoding_failure_preserves_existing_file(tmp_path):
    target = tmp_path / "users.json"
    atomic_write_json(target, {"users": ["original"]})
    original = target.read_bytes()

    with pytest.raises(TypeError):
        atomic_write_json(target, {"users": ["new", object()]})

    assert target.read_bytes() == original
    assert not list(tmp_path.glob("*.tmp"))
    assert target.stat().st_mode & 0o777 == 0o600


def test_atomic_write_does_not_follow_destination_symlink(tmp_path):
    secret = tmp_path / "secret.json"
    secret.write_text('{"secret": true}')
    destination = tmp_path / "users.json"
    destination.symlink_to(secret)

    atomic_write_json(destination, {"new": True})

    assert json.loads(secret.read_text()) == {"secret": True}
    assert not destination.is_symlink()
    assert read_json(destination, {}) == {"new": True}


def test_lock_refuses_symlinks_and_creates_private_directories(tmp_path):
    target = tmp_path / "new" / "private" / "users.json"
    atomic_write_json(target, [])
    assert target.parent.stat().st_mode & 0o777 == 0o700
    assert target.parent.parent.stat().st_mode & 0o777 == 0o700
    lock = target.with_name(".users.json.lock")
    assert lock.stat().st_mode & 0o777 == 0o600
    lock.unlink()
    lock.symlink_to(target)
    with pytest.raises(OSError):
        with locked_path(target):
            pytest.fail("Symlink lock was accepted")


def test_corrupt_json_is_not_replaced_by_default(tmp_path):
    target = tmp_path / "users.json"
    assert read_json(target, []) == []
    target.write_text("corrupt")
    with pytest.raises(json.JSONDecodeError):
        read_json(target, [])


def test_nested_lock_and_serialized_views_preserve_thread_updates(tmp_path):
    target = tmp_path / "counter.json"

    @serialized_json(lambda: target)
    def increment():
        with locked_path(target):
            data = read_json(target, {"count": 0})
            data["count"] += 1
            atomic_write_json(target, data)

    with ThreadPoolExecutor(max_workers=8) as pool:
        list(pool.map(lambda _: increment(), range(80)))

    assert read_json(target, {}) == {"count": 80}


def test_cross_process_read_modify_write_preserves_updates(tmp_path):
    target = tmp_path / "counter.json"
    source = str(Path(__file__).resolve().parents[1] / "src")
    program = """
import sys
from security_storage import atomic_write_json, locked_path, read_json
for _ in range(20):
    with locked_path(sys.argv[1]):
        data = read_json(sys.argv[1], {"count": 0})
        data["count"] += 1
        atomic_write_json(sys.argv[1], data)
"""
    environment = dict(os.environ, PYTHONPATH=source)
    workers = [
        subprocess.Popen(
            [sys.executable, "-c", program, str(target)],
            env=environment,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
        )
        for _ in range(4)
    ]
    try:
        for worker in workers:
            _, error = worker.communicate(timeout=20)
            assert worker.returncode == 0, error
    finally:
        for worker in workers:
            if worker.poll() is None:
                worker.kill()
                worker.wait()

    assert read_json(target, {}) == {"count": 80}

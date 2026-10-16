"""Admin log access, credential redaction and bounded host diagnostics."""

import importlib.util
import json
import os
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import patch
from urllib.parse import quote

import pytest
from test_admin_memes_ui import browser as browser_fixture
from test_blog_images import ui as ui_fixture
from test_security_config import security

import admin_log_reader as reader

ui = ui_fixture
browser = browser_fixture
ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location(
    "admin_log_exporter", ROOT / "scripts/export_admin_logs.py"
)
exporter = importlib.util.module_from_spec(spec)
with patch.dict(sys.modules, {"security_config": security}):
    spec.loader.exec_module(exporter)


def snapshot(path, text="Rclone finished", generated=None):
    document = {
        "generated_at": (generated or datetime.now(timezone.utc)).isoformat(),
        "entries": [
            dict(
                id="rclone-1",
                title="Rclone",
                filename="rclone.log",
                available=True,
                text=text,
            )
        ],
    }
    path.write_text(json.dumps(document))
    return document


@pytest.fixture
def logs(ui, tmp_path, monkeypatch):
    path = tmp_path / "server.log"
    path.write_text("Application event\n")
    host = tmp_path / "overview.json"
    snapshot(host)
    monkeypatch.setattr(ui.module, "LOG_FILENAME", str(path))
    monkeypatch.setattr(ui.module, "HOST_SNAPSHOT", host)
    ui.host = host
    ui.log = path
    return ui


def test_admin_selects_read_only_log_and_html_is_escaped(logs):
    snapshot(logs.host, '<script>alert("xss")</script>\nRclone finished')
    response = logs.client.get("/admin/logs?source=rclone-1")
    assert response.status_code == 200
    assert "Rclone finished" in response.text
    assert "&lt;script&gt;" in response.text
    assert '<script>alert("xss")' not in response.text
    assert "Application event" not in response.text
    assert "private, no-store" == response.headers["Cache-Control"]
    assert "noindex" in response.headers["X-Robots-Tag"]
    assert 'value="rclone-1" selected' in response.text


@pytest.mark.parametrize(
    "source", ["../../.env", "/etc/shadow", "unknown", "rclone-9"]
)
def test_query_cannot_select_arbitrary_host_files(logs, source):
    assert (
        logs.client.get(
            "/admin/logs", query_string={"source": source}
        ).status_code
        == 400
    )


@pytest.mark.parametrize("mode", ["member", "anonymous", "preview"])
def test_rejected_users_cannot_trigger_file_reads(logs, monkeypatch, mode):
    if mode == "member":
        logs.app.config["ADMIN"] = False
    elif mode == "anonymous":
        logs.app.config["AUTHENTICATED"] = False
    else:
        with logs.client.session_transaction() as session:
            session["view_as"] = "user"

    def forbidden_read(*args):
        raise AssertionError("Unauthorized log read")

    monkeypatch.setattr(logs.module, "host_snapshot", forbidden_read)
    monkeypatch.setattr(logs.module, "file_entry", forbidden_read)
    assert logs.client.get("/admin/logs?source=rclone-1").status_code in {
        302,
        401,
    }


def test_app_log_and_stale_snapshot_have_clear_fallbacks(logs):
    snapshot(
        logs.host, generated=datetime.now(timezone.utc) - timedelta(minutes=5)
    )
    response = logs.client.get("/admin/logs")
    assert "starejši od treh minut" in response.text
    logs.host.unlink()
    assert "Application event" in logs.client.get("/admin/logs").text
    logs.log.unlink()
    assert (
        "Dnevnik trenutno ni na voljo." in logs.client.get("/admin/logs").text
    )


def test_browser_selects_and_refreshes_logs_on_mobile(logs, browser):
    page = browser.page
    for width in [320, 1440]:
        page.set_viewport_size({"width": width, "height": 900})
        page.goto(browser.base + "/admin/logs")
        page.get_by_label("Izberi dnevnik").select_option("rclone-1")
        page.get_by_role("button", name="Prikaži", exact=True).click()
        assert "Rclone finished" in page.locator(".admin-log").inner_text()
        assert page.get_by_label("Izberi dnevnik").input_value() == "rclone-1"
        snapshot(logs.host, "Rclone refreshed")
        page.get_by_role("link", name="Osveži dnevnik").click()
        assert "Rclone refreshed" in page.locator(".admin-log").inner_text()
        assert page.evaluate(
            "document.documentElement.scrollWidth <= innerWidth + 1"
        )
        snapshot(logs.host)


def test_redacts_configured_credentials_and_recognizable_secrets():
    secret = "literal value/$+private"
    text = (
        f"{secret}\n{quote(secret, safe='')}\n"
        'GMAIL_TOKEN="mail password with spaces"\n'
        '{"refresh_token": "oauth-value", "password": "password-value"}\n'
        "Authorization: Bearer bearer-value\n"
        "GET /login?token=query-value&key=key-value&code=code-value\n"
        "GET /password/reset/reset-value\n"
        "GET /blog/subscribe/confirm/confirm-value\n"
        "https://user:userinfo-value@example.test/path\n"
        "AGE-SECRET-KEY-1ABC\n"
        "-----BEGIN PRIVATE KEY-----\nkey-value\n-----END PRIVATE KEY-----\n"
        "Ordinary error stays visible"
    )
    sanitized = reader.redact(text, [secret])
    for value in [
        secret,
        quote(secret, safe=""),
        "mail password with spaces",
        "oauth-value",
        "password-value",
        "bearer-value",
        "query-value",
        "key-value",
        "code-value",
        "reset-value",
        "confirm-value",
        "userinfo-value",
        "AGE-SECRET-KEY-1ABC",
    ]:
        assert value not in sanitized
    assert "Ordinary error stays visible" in sanitized


def test_tail_bounds_work_and_never_modifies_file(tmp_path):
    path = tmp_path / "app.log"
    path.write_text(
        "x" * (reader.MAX_LOG_BYTES * 4)
        + "\n"
        + "".join(f"LOG-{index:03}\n" for index in range(300))
    )
    before = path.read_bytes()
    entry = reader.file_entry("app", "App", path)
    assert entry["available"]
    assert "LOG-099" not in entry["text"]
    assert "LOG-100" in entry["text"] and "LOG-299" in entry["text"]
    assert len(entry["text"]) <= reader.MAX_LOG_BYTES
    assert path.read_bytes() == before


def test_files_and_parents_cannot_be_symlinks_or_pipes(tmp_path):
    target = tmp_path / "secret.log"
    target.write_text("DO NOT READ")
    link = tmp_path / "link.log"
    link.symlink_to(target)
    parent = tmp_path / "linked"
    parent.symlink_to(tmp_path, target_is_directory=True)
    pipe = tmp_path / "pipe.log"
    os.mkfifo(pipe)
    for path in [link, parent / "secret.log", pipe]:
        entry = reader.file_entry("app", "App", path)
        assert not entry["available"]
        assert "DO NOT READ" not in entry["text"]


@pytest.mark.parametrize(
    "invalid",
    [
        "[]",
        "not json",
        '{"generated_at":"2026-01-01"}',
        "x" * (reader.MAX_SNAPSHOT_BYTES + 1),
    ],
)
def test_invalid_snapshot_fails_closed(tmp_path, invalid):
    path = tmp_path / "overview.json"
    path.write_text(invalid)
    assert not reader.host_snapshot(path)["entries"]


def test_export_uses_latest_three_rclone_runs_and_hides_credentials(tmp_path):
    directory = tmp_path / "cache/logs/rclone"
    directory.mkdir(parents=True)
    secret = "private-mail-token"
    for index in range(5):
        path = directory / f"rclone_sync_{index}.log"
        path.write_text(f"RUN-{index}\nGMAIL_TOKEN={secret}\n")
        os.utime(path, (100 + index, 100 + index))
    (directory / "rclone_sync_symlink.log").symlink_to(tmp_path / ".env")
    (directory / "other.log").write_text("UNRELATED-SECRET")
    commands = []

    def run(command):
        commands.append(command)
        return f"Host event {secret}", True

    document = exporter.collect(tmp_path, {"GMAIL_TOKEN": secret}, run=run)
    entries = [
        entry
        for entry in document["entries"]
        if entry["id"].startswith("rclone-")
    ]
    assert [entry["filename"] for entry in entries] == [
        f"rclone_sync_{index}.log" for index in [4, 3, 2]
    ]
    assert secret not in json.dumps(document)
    assert "UNRELATED-SECRET" not in json.dumps(document)
    assert all("shell" not in command for command in commands)
    assert any(command[:2] == ["docker", "ps"] for command in commands)
    assert not any("inspect" in command for command in commands)


def test_published_document_is_atomic_and_group_read_only(
    tmp_path, monkeypatch
):
    project = tmp_path / "project"
    project.mkdir()
    (project / ".env").write_text(f"MARINKINO_GID={os.getgid()}\n")
    destination = tmp_path / "host-status/overview.json"
    document = dict(
        generated_at=datetime.now(timezone.utc).isoformat(), entries=[]
    )
    monkeypatch.setattr(exporter, "collect", lambda *args: document)
    exporter.publish(project, destination)
    assert json.loads(destination.read_text()) == document
    assert destination.stat().st_mode & 0o777 == 0o640
    assert destination.parent.stat().st_mode & 0o777 == 0o750


def test_command_output_has_byte_and_time_limits():
    text, success = exporter.command_output(
        [sys.executable, "-c", "print('ok')"]
    )
    assert success and text == "ok"
    text, success = exporter.command_output(
        [sys.executable, "-c", "print('x' * 1000000)"]
    )
    assert not success and len(text) < reader.MAX_LOG_BYTES + 100
    text, success = exporter.command_output(
        [sys.executable, "-c", "import time; time.sleep(10)"], timeout=0.1
    )
    assert not success and "potekel" in text

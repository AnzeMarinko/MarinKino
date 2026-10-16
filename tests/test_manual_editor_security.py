"""Exercise the editor's real request guards without media services or data."""

import importlib.util
import sys
from pathlib import Path
from types import ModuleType, SimpleNamespace
from unittest.mock import Mock, patch

import pytest
from flask import jsonify
from flask_wtf.csrf import generate_csrf


@pytest.fixture
def editor(tmp_path, monkeypatch):
    dependencies = {
        "yt_dlp": {},
        "ffmpeg_normalize": {"FFmpegNormalize": Mock()},
        "flask_compress": {"Compress": Mock()},
        "mutagen.easyid3": {"EasyID3": Mock()},
        "mutagen.mp3": {"MP3": Mock(), "HeaderNotFoundError": ValueError},
        "content_preparation.audio_preparation": {
            "convert_mp3_to_hls": Mock(),
        },
        "content_preparation.get_movie_metadata": {"MovieMetadata": Mock()},
        "content_preparation.subtitles.download_subtitles": {
            "get_subtitles": Mock(),
        },
        "content_preparation.subtitles.translate_subtitles": {
            "translate": Mock(),
        },
        "content_preparation.video_converter": {
            "convert_to_m3u8": Mock(), "convert_videos": Mock(),
        },
        "utils": {"safe_path": Mock()},
    }
    stubs = {}
    for name, members in dependencies.items():
        stub = ModuleType(name)
        stub.__dict__.update(members)
        stubs[name] = stub
    monkeypatch.delenv("FLASK_KEY", raising=False)
    monkeypatch.chdir(tmp_path)
    source = Path(__file__).resolve().parents[1] / "src" / "manual_editor.py"
    spec = importlib.util.spec_from_file_location(
        "secure_manual_editor", source,
    )
    module = importlib.util.module_from_spec(spec)
    with patch.dict(sys.modules, stubs):
        spec.loader.exec_module(module)

    module.app.config.update(TESTING=True)
    mutation = Mock(return_value={"status": "ok"})
    prepare = Mock()
    monkeypatch.setattr(module, "process_incoming_music_folder", prepare)
    monkeypatch.setattr(module, "list_incoming_music_tracks", lambda: [])
    monkeypatch.setattr(
        module,
        "render_template",
        lambda *_args, **_kwargs: jsonify({"csrf_token": generate_csrf()}),
    )

    @module.app.post("/test-mutation")
    def protected_mutation():
        # Force parsing so Flask enforces the request-size limit.
        module.request.get_json()
        return mutation()

    return SimpleNamespace(
        app=module.app, client=module.app.test_client(),
        prepare=prepare, mutation=mutation,
    )


def test_editor_get_does_not_prepare_media(editor):
    response = editor.client.get("/")
    assert response.status_code == 200
    assert response.json["csrf_token"]
    assert len(editor.app.secret_key) == 64
    editor.prepare.assert_not_called()


@pytest.mark.parametrize("host", ["localhost", "127.0.0.1"])
def test_editor_accepts_only_local_hosts(editor, host):
    response = editor.client.get("/", base_url=f"http://{host}:8080")
    assert response.status_code == 200


@pytest.mark.parametrize("host", ["evil.example", "localhost.evil.example"])
def test_editor_rejects_dns_rebinding_host(editor, host):
    response = editor.client.get("/", base_url=f"http://{host}:8080")
    assert response.status_code == 400


@pytest.mark.parametrize("address", ["192.168.1.15", "203.0.113.7", "", "bad"])
def test_editor_does_not_trust_forwarded_loopback(editor, address):
    response = editor.client.get(
        "/", environ_overrides={"REMOTE_ADDR": address},
        headers={"X-Forwarded-For": "127.0.0.1"},
    )
    assert response.status_code == 403


def test_editor_accepts_ipv6_loopback(editor):
    response = editor.client.get(
        "/", environ_overrides={"REMOTE_ADDR": "::1"},
    )
    assert response.status_code == 200


@pytest.mark.parametrize("headers", [
    {"Origin": "https://evil.example"},
    {"Origin": "null"},
    {"Origin": "http://localhost:9000"},
    {"Sec-Fetch-Site": "cross-site"},
])
def test_editor_rejects_cross_site_reads(editor, headers):
    assert editor.client.get("/", headers=headers).status_code == 403


def test_editor_mutation_requires_valid_csrf_token(editor):
    token = editor.client.get("/").json["csrf_token"]
    assert editor.client.post("/test-mutation", json={}).status_code == 400
    assert editor.client.post(
        "/test-mutation", json={}, headers={"X-CSRFToken": "forged"},
    ).status_code == 400
    editor.mutation.assert_not_called()
    response = editor.client.post(
        "/test-mutation", json={},
        headers={"X-CSRFToken": token, "Origin": "http://localhost"},
    )
    assert response.status_code == 200
    editor.mutation.assert_called_once()


def test_editor_rejects_cross_origin_even_with_valid_csrf(editor):
    token = editor.client.get("/").json["csrf_token"]
    response = editor.client.post(
        "/test-mutation", json={},
        headers={"X-CSRFToken": token, "Origin": "https://evil.example"},
    )
    assert response.status_code == 403
    editor.mutation.assert_not_called()


def test_editor_bounds_request_size(editor):
    token = editor.client.get("/").json["csrf_token"]
    response = editor.client.post(
        "/test-mutation", json={"payload": "x" * (1024 * 1024)},
        headers={"X-CSRFToken": token},
    )
    assert response.status_code == 413
    editor.mutation.assert_not_called()

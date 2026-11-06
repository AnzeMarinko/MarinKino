"""Local editor actions preserve user work and report actual outcomes."""

import json
from unittest.mock import Mock

from test_manual_editor_security import editor as editor_fixture

from security_storage import safe_resolved_path

editor = editor_fixture


def post(editor, path, data):
    token = editor.client.get("/").json["csrf_token"]
    return editor.client.post(path, json=data, headers={"X-CSRFToken": token})


def test_saved_music_metadata_keeps_recommendation_fields(
    editor, tmp_path, monkeypatch
):
    module = editor.module
    monkeypatch.setattr(module, "MUSIC_FOLDER", str(tmp_path))
    monkeypatch.setattr(module, "safe_path", safe_resolved_path)
    track = tmp_path / "song"
    track.mkdir()
    (track / "index.m3u8").write_text("#EXTM3U")
    (track / "metadata.json").write_text(
        json.dumps(
            {
                "title": "Before",
                "duration": 90,
                "audio_analysis": {"tempo": 120},
                "custom": "keep",
            }
        )
    )
    module.update_values("song", "After", "Artist", "Album")
    saved = json.loads((track / "metadata.json").read_text())
    assert saved["title"] == "After"
    assert saved["audio_analysis"] == {"tempo": 120}
    assert saved["custom"] == "keep"
    assert saved["duration"] == 90


def test_movie_preview_uses_movie_directory(editor, tmp_path, monkeypatch):
    monkeypatch.setattr(editor.module, "INCOMING_MOVIE_FOLDER_ABS", tmp_path)
    monkeypatch.setattr(editor.module, "safe_path", safe_resolved_path)
    movie = tmp_path / "Film.2026"
    movie.mkdir()
    (movie / "part.mp4").write_bytes(b"movie-preview")
    response = editor.client.get("/movie/file/Film.2026/part.mp4")
    assert response.status_code == 200
    assert response.data == b"movie-preview"


def test_failed_conversion_never_reports_success(
    editor, tmp_path, monkeypatch
):
    monkeypatch.setattr(editor.module, "_movie_folder", lambda _name: tmp_path)
    monkeypatch.setattr(
        editor.module, "convert_videos", lambda *args, **kwargs: []
    )
    response = post(
        editor,
        "/api/movies/process",
        {
            "folder": "Film",
            "mode": "merge",
            "metadata": {"title": "Film"},
            "subtitles": [],
        },
    )
    assert response.status_code == 500
    assert response.json["status"] == "error"
    assert "Ni videov" in response.json["message"]


def test_omitted_subtitles_are_archived(editor, tmp_path, monkeypatch):
    monkeypatch.setattr(editor.module, "_movie_folder", lambda _name: tmp_path)
    monkeypatch.setattr(
        editor.module, "convert_videos", lambda *args, **kwargs: []
    )
    subtitle = tmp_path / "sub.srt"
    subtitle.write_text("original subtitle")
    post(
        editor,
        "/api/movies/process",
        {
            "folder": "Film",
            "mode": "merge",
            "metadata": {"title": "Film"},
            "subtitles": [],
        },
    )
    assert (
        tmp_path / ".originals/sub.srt.source"
    ).read_text() == "original subtitle"


def test_busy_editor_rejects_second_mutation(editor):
    token = editor.client.get("/").json["csrf_token"]
    with editor.module._preparation_lock:
        response = editor.client.post(
            "/api/music/prepare", json={}, headers={"X-CSRFToken": token}
        )
    assert response.status_code == 409
    editor.prepare.assert_not_called()
    editor.prepare.return_value = []
    assert post(editor, "/api/music/prepare", {}).status_code == 200


def test_download_rejects_other_hosts_before_network(editor, monkeypatch):
    download = Mock()
    monkeypatch.setattr(editor.module, "download_playlist", download)
    response = post(
        editor, "/api/music/download-yt", {"url": "https://localhost/private"}
    )
    assert response.status_code == 400
    download.assert_not_called()

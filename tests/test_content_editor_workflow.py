"""Local editor actions preserve user work and report actual outcomes."""

import json
from unittest.mock import Mock

import pytest
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


def test_subtitle_download_normalizes_and_requests_only_missing_language(
    editor, tmp_path, monkeypatch
):
    monkeypatch.setattr(editor.module, "_movie_folder", lambda _name: tmp_path)
    download = Mock(return_value=True)
    monkeypatch.setattr(editor.module, "get_subtitles", download)
    extract = Mock()
    monkeypatch.setattr(editor.module, "extract_audio", extract)
    (tmp_path / "film.mp4").write_bytes(b"video")
    (tmp_path / "Film.slv.srt").write_text("slovenian")
    response = post(
        editor,
        "/api/movies/subtitles/download",
        {"folder": "Film", "metadata": {"imdb_id": "tt1234567"}},
    )
    assert response.status_code == 200
    assert response.json["renames"] == {
        "Film.slv.srt": "subtitles-SloSubs.srt"
    }
    assert download.call_args.kwargs["languages"] == ["en"]
    extract.assert_called_once_with(str(tmp_path), str(tmp_path / "film.mp4"))


def test_subtitle_download_asks_before_archiving_duplicates(
    editor, tmp_path, monkeypatch
):
    monkeypatch.setattr(editor.module, "_movie_folder", lambda _name: tmp_path)
    download = Mock(return_value=True)
    monkeypatch.setattr(editor.module, "get_subtitles", download)
    monkeypatch.setattr(editor.module, "extract_audio", Mock())
    (tmp_path / "film.mp4").write_bytes(b"video")
    (tmp_path / "one.eng.srt").write_text("first")
    (tmp_path / "two.en.srt").write_text("second")
    payload = {"folder": "Film", "metadata": {"imdb_id": "tt1234567"}}
    response = post(editor, "/api/movies/subtitles/download", payload)
    assert response.json["status"] == "selection_required"
    assert response.json["groups"] == {"en": ["one.eng.srt", "two.en.srt"]}
    download.assert_not_called()
    assert not (tmp_path / ".originals").exists()
    payload["subtitle_selection"] = {"en": "two.en.srt"}
    response = post(editor, "/api/movies/subtitles/download", payload)
    assert response.json["status"] == "ok"
    assert (tmp_path / ".originals/one.eng.srt.source").read_text() == "first"
    assert download.call_args.kwargs["languages"] == ["sl"]


def test_subtitle_download_reports_renames_even_if_request_fails(
    editor, tmp_path, monkeypatch
):
    monkeypatch.setattr(editor.module, "_movie_folder", lambda _name: tmp_path)
    (tmp_path / "film.mp4").write_bytes(b"video")
    (tmp_path / "Film.en.srt").write_text("english")
    response = post(
        editor,
        "/api/movies/subtitles/download",
        {"folder": "Film", "metadata": {"imdb_id": "invalid"}},
    )
    assert response.status_code == 400
    assert response.json["renames"] == {
        "Film.en.srt": "subtitles-enSubs.srt"
    }
    assert (tmp_path / "subtitles-enSubs.srt").exists()


@pytest.mark.parametrize(
    ("mode", "video_count"), [("collection", 1), ("merge", 2)]
)
def test_subtitle_download_skips_collections_and_split_movies(
    editor, tmp_path, monkeypatch, mode, video_count
):
    monkeypatch.setattr(editor.module, "_movie_folder", lambda _name: tmp_path)
    download = Mock()
    extract = Mock()
    monkeypatch.setattr(editor.module, "get_subtitles", download)
    monkeypatch.setattr(editor.module, "extract_audio", extract)
    for index in range(video_count):
        (tmp_path / f"{index}.mp4").write_bytes(b"video")
    response = post(
        editor, "/api/movies/subtitles/download",
        {"folder": "Film", "mode": mode, "metadata": {"imdb_id": "tt1234567"}},
    )
    assert response.status_code == 200
    assert not response.json["downloaded"]
    assert response.json["message"]
    download.assert_not_called()
    extract.assert_not_called()

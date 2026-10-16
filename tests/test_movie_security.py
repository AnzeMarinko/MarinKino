"""Movie responses and downloads must keep private metadata on the server."""

import importlib.util
import json
import shutil
import subprocess
import sys
import threading
import zipfile
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from types import ModuleType, SimpleNamespace
from unittest.mock import Mock, patch

import fakeredis
import pytest
from flask import Flask
from flask_login import LoginManager, UserMixin
from jinja2 import DictLoader

import movie_downloads
from security_storage import safe_resolved_path

SECRET_EMAIL = "private-note-owner@example.invalid"
SECRET_NOTE = "PRIVATE-NOTE-MUST-NEVER-LEAVE-SERVER"


class Member(UserMixin):
    id = "member"
    is_admin = False


@pytest.fixture
def movies(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    root = tmp_path / "data/movies"
    for index in range(45):
        directory = root / "group" / f"film-{index:02d}"
        directory.mkdir(parents=True)
        (directory / "film.mp4").write_bytes(b"video")
        (directory / "readme.json").write_text(
            json.dumps(
                {
                    "Title": f"Film {index:02d}",
                    "Runtimes": "90",
                    "RuntimesByFiles": {"film": 90},
                    "Genres": ["Drama"],
                    "user_notes": {
                        "private-note-id": {
                            "username": "Private author",
                            "email": SECRET_EMAIL,
                            "comment": SECRET_NOTE,
                            "admin_response": "PRIVATE-REPLY",
                        }
                    },
                    "ratings": {
                        "violence": [{"user": SECRET_EMAIL, "value": 2}]
                    },
                }
            )
        )
    store = fakeredis.FakeRedis(decode_responses=True)
    utilities = ModuleType("utils")
    utilities.FLASK_ENV = "production"
    utilities.is_current_admin_view = lambda user: getattr(
        user, "is_admin", False
    )
    utilities.redis_client = store
    utilities.safe_path = safe_resolved_path
    utilities.send_mail = Mock()
    utilities.users = {"member": {"emails": ["member@example.invalid"]}}
    source = (
        Path(__file__).resolve().parents[1] / "src/blueprints/movies_bp.py"
    )
    spec = importlib.util.spec_from_file_location(
        "movie_security_routes", source
    )
    module = importlib.util.module_from_spec(spec)
    with patch.dict(sys.modules, {"utils": utilities}):
        spec.loader.exec_module(module)
    app = Flask(__name__)
    app.config.update(TESTING=True, SECRET_KEY="isolated-movie-tests")
    app.jinja_loader = DictLoader(
        {
            "movies.html": (
                "{{ {'movies': movies, 'has_more': has_more}|tojson }}"
            ),
        }
    )
    manager = LoginManager(app)
    manager.user_loader(lambda _identifier: Member())
    app.register_blueprint(module.movies_bp)
    client = app.test_client()
    with client.session_transaction() as session:
        session["_user_id"] = "member"
        session["_fresh"] = True
    return SimpleNamespace(
        module=module,
        app=app,
        client=client,
        redis=store,
        root=root,
    )


def assert_public_catalog(payload):
    serialized = json.dumps(payload)
    for secret in (
        SECRET_EMAIL,
        SECRET_NOTE,
        "PRIVATE-REPLY",
        "private-note-id",
    ):
        assert secret not in serialized
    assert payload["movies"]
    for movie in payload["movies"]:
        assert "user_notes" not in movie
        assert "ratings" not in movie
        assert movie["title"] and movie["folder"]
        assert movie["is_admin"] is False


def test_initial_and_paginated_catalog_do_not_leak_private_data(movies):
    first = movies.client.get("/movies?sort=title_asc")
    assert first.status_code == 200
    initial = json.loads(first.get_data(as_text=True))
    assert_public_catalog(initial)
    assert len(initial["movies"]) == 40
    following = movies.client.get("/movies/page?page=1")
    assert following.status_code == 200
    assert_public_catalog(following.json)
    assert len(following.json["movies"]) == 5
    assert not following.json["has_more"]
    # Publishing a safe projection must not destroy stored private comments.
    assert SECRET_NOTE in json.dumps(movies.module.all_films)


@pytest.mark.parametrize("filename", ["readme.json", ".env", "secret.lock"])
def test_private_metadata_cannot_be_requested_as_media(movies, filename):
    target = movies.root / "group/film-00" / filename
    target.write_text(SECRET_NOTE)
    response = movies.client.get("/movies/file/group/film-00/" + filename)
    assert response.status_code == 404
    assert SECRET_NOTE.encode() not in response.data
    assert "X-Accel-Redirect" not in response.headers


def test_media_path_cannot_escape_to_prefix_sibling_or_symlink(movies):
    sibling = movies.root.with_name("movies-private")
    sibling.mkdir()
    secret = sibling / "secret.mp4"
    secret.write_bytes(SECRET_NOTE.encode())
    (movies.root / "group/escape.mp4").symlink_to(secret)
    for suffix in (
        "%2e%2e/movies-private/secret.mp4",
        "group/escape.mp4",
    ):
        response = movies.client.get("/movies/file/" + suffix)
        assert response.status_code == 404
        assert "X-Accel-Redirect" not in response.headers
    valid = movies.client.get("/movies/file/group/film-00/film.mp4")
    assert valid.status_code == 200
    assert valid.headers["X-Accel-Redirect"].endswith(
        "/group/film-00/film.mp4"
    )


@pytest.fixture
def archive(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    root = tmp_path / "movies"
    directory = root / "group/film"
    directory.mkdir(parents=True)
    (directory / "film.mp4").write_bytes(b"video bytes")
    (directory / "subtitles.vtt").write_text("WEBVTT\n")
    (directory / "readme.json").write_text(SECRET_NOTE)
    film = {
        "title": "Film",
        "video_files": ["film.mp4"],
        "subtitles": ["subtitles.vtt"],
        "video_files_m3u8": [],
        "user_notes": {SECRET_EMAIL: SECRET_NOTE},
        "ratings": {"user": SECRET_EMAIL},
    }
    monkeypatch.setattr(
        movie_downloads.shutil,
        "disk_usage",
        lambda _path: SimpleNamespace(free=1024**4),
    )
    app = Flask(__name__)
    app.config["TESTING"] = True

    @app.get("/download")
    def download():
        return movie_downloads.archive_response(
            film,
            root,
            "group",
            "film",
            production=True,
        )

    return SimpleNamespace(
        app=app,
        client=app.test_client(),
        film=film,
        root=root,
        directory=directory,
        cache=tmp_path / "cache/downloads",
    )


def test_archive_is_disk_backed_and_contains_only_public_metadata(archive):
    response = archive.client.get("/download")
    assert response.status_code == 200
    assert response.data == b""
    assert "no-store" in response.headers["Cache-Control"]
    assert response.headers["X-Accel-Redirect"].startswith(
        "/protected_downloads/"
    )
    target = (
        archive.cache / response.headers["X-Accel-Redirect"].rsplit("/", 1)[1]
    )
    assert target.is_file()
    with zipfile.ZipFile(target) as downloaded:
        assert set(downloaded.namelist()) == {
            "film.mp4",
            "subtitles.vtt",
            "metadata.json",
        }
        metadata = downloaded.read("metadata.json")
        assert SECRET_NOTE.encode() not in metadata
        assert SECRET_EMAIL.encode() not in metadata
        assert json.loads(metadata)["title"] == "Film"
    assert not list(archive.cache.glob("build-*"))


def test_oversized_source_and_insufficient_disk_fail_without_archive(
    archive, monkeypatch
):
    monkeypatch.setattr(movie_downloads, "MAX_ARCHIVE_BYTES", 4)
    assert archive.client.get("/download").status_code == 413
    assert not list(archive.cache.glob("*.zip"))
    monkeypatch.setattr(movie_downloads, "MAX_ARCHIVE_BYTES", 1024)
    monkeypatch.setattr(
        movie_downloads.shutil,
        "disk_usage",
        lambda _path: SimpleNamespace(free=0),
    )
    assert archive.client.get("/download").status_code == 503
    assert not list(archive.cache.glob("*.zip"))


def use_hls(archive, uri="segment.ts"):
    archive.film["video_files"] = []
    archive.film["video_files_m3u8"] = ["hls"]
    stream = archive.directory / "hls"
    stream.mkdir()
    (stream / "master.m3u8").write_text(
        "#EXTM3U\n#EXT-X-VERSION:3\n#EXT-X-TARGETDURATION:6\n"
        f"#EXT-X-MEDIA-SEQUENCE:0\n#EXTINF:6.0,\n{uri}\n#EXT-X-ENDLIST\n",
    )


def test_ffmpeg_times_out_cleanly_and_releases_preparation_slot(
    archive, monkeypatch
):
    use_hls(archive)
    observed = []

    def timeout(command, **options):
        observed.append(options["timeout"])
        raise subprocess.TimeoutExpired(command, options["timeout"])

    monkeypatch.setattr(movie_downloads.subprocess, "run", timeout)
    for _ in range(2):
        assert archive.client.get("/download").status_code == 503
    assert all(0 < bound <= 1800 for bound in observed)
    assert not list(archive.cache.glob("*.zip"))
    assert not list(archive.cache.glob("build-*"))


def test_parallel_preparation_is_rejected_until_current_job_finishes(
    archive, monkeypatch
):
    use_hls(archive)
    started, release = threading.Event(), threading.Event()

    def convert(command, **_options):
        started.set()
        assert release.wait(5)
        Path(command[-1]).write_bytes(b"converted video")

    monkeypatch.setattr(movie_downloads.subprocess, "run", convert)

    def first_download():
        with archive.app.test_client() as client:
            return client.get("/download").status_code

    with ThreadPoolExecutor(max_workers=1) as executor:
        first = executor.submit(first_download)
        try:
            assert started.wait(5)
            assert archive.client.get("/download").status_code == 429
        finally:
            release.set()
        assert first.result(timeout=5) == 200
    assert archive.client.get("/download").status_code == 200


@pytest.mark.skipif(not shutil.which("ffmpeg"), reason="FFmpeg not installed")
@pytest.mark.parametrize("protocol", ["http", "https"])
def test_actual_ffmpeg_refuses_network_playlist_protocols(
    archive, monkeypatch, protocol
):
    use_hls(archive, f"{protocol}://127.0.0.1:9/segment.ts")
    original_run = subprocess.run
    errors = []

    def bounded_run(command, **options):
        assert 0 < options["timeout"] <= 1800
        options.update(timeout=8, stderr=subprocess.PIPE)
        try:
            return original_run(command, **options)
        except subprocess.CalledProcessError as error:
            errors.append(error.stderr)
            raise

    monkeypatch.setattr(movie_downloads.subprocess, "run", bounded_run)
    assert archive.client.get("/download").status_code == 503
    assert b"not on whitelist" in b"\n".join(errors).lower()
    assert not list(archive.cache.glob("*.zip"))


def test_progress_rejects_invented_files_without_growing_redis(movies):
    for index in range(12):
        response = movies.client.post(
            "/movies/video-progress",
            json={
                "filename": f"/movies/file/group/film-00/unknown-{index}.mp4",
                "duration": 120,
                "currentTime": 30,
            },
        )
        assert response.status_code == 404
    assert movies.redis.hlen("prog:member") == 0
    assert (
        movies.client.post(
            "/movies/video-progress",
            json={
                "filename": "/movies/file/group/film-00/film.mp4",
                "duration": 120,
                "currentTime": 30,
            },
        ).status_code
        == 204
    )
    assert movies.redis.hlen("prog:member") == 1


@pytest.mark.parametrize("value", [float("nan"), float("inf"), -1, 999999999])
def test_progress_rejects_invalid_timing(movies, value):
    response = movies.client.post(
        "/movies/video-progress",
        json={
            "filename": "/movies/file/group/film-00/film.mp4",
            "duration": value,
            "currentTime": 30,
        },
    )
    assert response.status_code == 400
    assert movies.redis.hlen("prog:member") == 0

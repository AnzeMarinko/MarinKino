"""Collection archives include every episode and publish only complete ZIPs."""

import hashlib
import json
import shutil
import subprocess
import zipfile
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock

import pytest

import movie_downloads


@pytest.fixture
def collection(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    directory = tmp_path / "movies/group/Show.Collection"
    directory.mkdir(parents=True)
    film = {
        "title": "Show",
        "video_files": [],
        "video_files_m3u8": [],
        "subtitles": [],
    }
    monkeypatch.setattr(
        movie_downloads.shutil,
        "disk_usage",
        lambda _path: SimpleNamespace(free=1024**4),
    )
    return SimpleNamespace(
        film=film,
        directory=directory,
        root=tmp_path / "movies",
        cache=tmp_path / "cache/downloads",
    )


def add_hls(collection, name, size=50):
    folder = collection.directory / name
    folder.mkdir(parents=True)
    (folder / "master.m3u8").write_text(
        "#EXTM3U\n#EXTINF:1,\nvideo.ts\n#EXT-X-ENDLIST\n"
    )
    (folder / "video.ts").write_bytes(b"v" * size)
    collection.film["video_files_m3u8"].append(name)
    return folder


def add_mp4(collection, name, content=b"original video"):
    (collection.directory / name).write_bytes(content)
    collection.film["video_files"].append(name)


def prepare(collection):
    return movie_downloads.prepare_archive(
        collection.film, collection.root, "group", "Show.Collection"
    )


def test_every_hls_episode_is_remuxed_sequentially_and_named(
    collection, monkeypatch
):
    add_hls(collection, "01 First")
    add_hls(collection, "02 Second")
    calls = []

    def remux(command, **options):
        playlist = Path(command[command.index("-i") + 1])
        calls.append((playlist, options["timeout"]))
        assert command[command.index("-c") + 1] == "copy"
        Path(command[-1]).write_bytes(playlist.parent.name.encode())

    monkeypatch.setattr(movie_downloads.subprocess, "run", remux)
    target = prepare(collection)
    assert [path.parent.name for path, _ in calls] == ["01 First", "02 Second"]
    assert 0 < calls[1][1] <= calls[0][1] <= 1800
    with zipfile.ZipFile(target) as archive:
        assert set(archive.namelist()) == {
            "01 First.mp4",
            "02 Second.mp4",
            "metadata.json",
        }
        assert archive.read("01 First.mp4") == b"01 First"
        assert archive.read("02 Second.mp4") == b"02 Second"
    assert not list(collection.cache.glob("build-*"))


def test_mixed_collection_deduplicates_mp4_and_hls_of_same_episode(
    collection, monkeypatch
):
    add_mp4(collection, "01.mp4", b"old MP4 copy")
    add_mp4(collection, "02.mp4", b"second episode")
    add_hls(collection, "01")
    add_hls(collection, "03")
    observed = []

    def remux(command, **_options):
        name = Path(command[command.index("-i") + 1]).parent.name
        observed.append(name)
        Path(command[-1]).write_bytes((name + " from HLS").encode())

    monkeypatch.setattr(movie_downloads.subprocess, "run", remux)
    with zipfile.ZipFile(prepare(collection)) as archive:
        assert observed == ["01", "03"]
        assert len(archive.namelist()) == 4
        assert archive.read("01.mp4") == b"01 from HLS"
        assert archive.read("02.mp4") == b"second episode"
        assert archive.read("03.mp4") == b"03 from HLS"


def test_nested_episode_names_do_not_collide_in_archive(
    collection, monkeypatch
):
    add_hls(collection, "Season 1/Episode")
    add_hls(collection, "Season 2/Episode")

    def remux(command, **_options):
        playlist = Path(command[command.index("-i") + 1])
        Path(command[-1]).write_bytes(playlist.parent.parent.name.encode())

    monkeypatch.setattr(movie_downloads.subprocess, "run", remux)
    with zipfile.ZipFile(prepare(collection)) as archive:
        assert archive.read("Season 1/Episode.mp4") == b"Season 1"
        assert archive.read("Season 2/Episode.mp4") == b"Season 2"


def test_missing_episode_never_returns_an_incomplete_collection(
    collection, monkeypatch
):
    add_mp4(collection, "01.mp4")
    collection.film["video_files"].append("02.mp4")
    remux = Mock()
    monkeypatch.setattr(movie_downloads.subprocess, "run", remux)
    with pytest.raises(movie_downloads.ArchivePreparationError) as error:
        prepare(collection)
    assert error.value.status == 503
    remux.assert_not_called()
    assert not list(collection.cache.glob("*.zip"))


@pytest.mark.parametrize("constraint", ["source", "disk"])
def test_preflight_accounts_for_all_episodes(
    collection, monkeypatch, constraint
):
    add_hls(collection, "01", size=400)
    add_hls(collection, "02", size=400)
    remux = Mock()
    monkeypatch.setattr(movie_downloads.subprocess, "run", remux)
    if constraint == "source":
        monkeypatch.setattr(movie_downloads, "MAX_ARCHIVE_BYTES", 700)
        expected = 413
    else:
        monkeypatch.setattr(
            movie_downloads.shutil,
            "disk_usage",
            lambda _path: SimpleNamespace(free=256 * 1024**2 + 2000),
        )
        expected = 503
    with pytest.raises(movie_downloads.ArchivePreparationError) as error:
        prepare(collection)
    assert error.value.status == expected
    remux.assert_not_called()
    assert not list(collection.cache.glob("*.zip"))


def test_cumulative_remux_output_is_bounded(collection, monkeypatch):
    add_hls(collection, "01")
    add_hls(collection, "02")
    monkeypatch.setattr(movie_downloads, "MAX_ARCHIVE_BYTES", 1000)

    def remux(command, **_options):
        Path(command[-1]).write_bytes(b"v" * 600)

    monkeypatch.setattr(movie_downloads.subprocess, "run", remux)
    with pytest.raises(movie_downloads.ArchivePreparationError) as error:
        prepare(collection)
    assert error.value.status == 413
    assert not list(collection.cache.glob("*.zip"))
    assert not list(collection.cache.glob("build-*"))


def test_second_episode_failure_never_publishes_partial_archive(
    collection, monkeypatch
):
    first = add_hls(collection, "01")
    second = add_hls(collection, "02")
    calls = []

    def remux(command, **_options):
        calls.append(command)
        if len(calls) == 2:
            raise subprocess.CalledProcessError(1, command)
        Path(command[-1]).write_bytes(b"first")

    monkeypatch.setattr(movie_downloads.subprocess, "run", remux)
    with pytest.raises(movie_downloads.ArchivePreparationError) as error:
        prepare(collection)
    assert error.value.status == 503
    assert not list(collection.cache.glob("*.zip"))
    assert not list(collection.cache.glob("build-*"))
    assert (first / "video.ts").read_bytes() == b"v" * 50
    assert (second / "video.ts").read_bytes() == b"v" * 50


def test_old_first_episode_only_cache_is_not_reused(collection):
    collection.cache.mkdir(parents=True)
    digest = hashlib.sha256(str(collection.directory).encode()).hexdigest()
    (collection.cache / (digest + ".zip")).write_bytes(b"old incomplete ZIP")
    assert (
        movie_downloads.ready_archive(
            collection.root, "group", "Show.Collection"
        )
        is None
    )


@pytest.mark.skipif(
    not shutil.which("ffmpeg") or not shutil.which("ffprobe"),
    reason="FFmpeg/FFprobe required for tiny real media fixtures",
)
def test_real_two_hls_episodes_download_as_playable_mp4_files(collection):
    for name, color in [("01", "red"), ("02", "blue")]:
        folder = collection.directory / name
        folder.mkdir()
        subprocess.run(
            [
                "ffmpeg",
                "-nostdin",
                "-v",
                "error",
                "-f",
                "lavfi",
                "-i",
                f"color=c={color}:s=32x32:r=5:d=1",
                "-f",
                "lavfi",
                "-i",
                "sine=frequency=440:duration=1",
                "-c:v",
                "libx264",
                "-threads",
                "1",
                "-pix_fmt",
                "yuv420p",
                "-c:a",
                "aac",
                "-f",
                "hls",
                "-hls_time",
                "1",
                "-hls_playlist_type",
                "vod",
                str(folder / "master.m3u8"),
            ],
            check=True,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.PIPE,
            timeout=20,
        )
        collection.film["video_files_m3u8"].append(name)
    with zipfile.ZipFile(prepare(collection)) as archive:
        for name in ("01", "02"):
            exported = collection.directory / ("export-" + name + ".mp4")
            exported.write_bytes(archive.read(name + ".mp4"))
            result = subprocess.run(
                [
                    "ffprobe",
                    "-v",
                    "error",
                    "-show_entries",
                    "stream=codec_type:format=duration",
                    "-of",
                    "json",
                    str(exported),
                ],
                check=True,
                capture_output=True,
                text=True,
                timeout=10,
            )
            metadata = json.loads(result.stdout)
            assert {
                stream["codec_type"] for stream in metadata["streams"]
            } == {"video", "audio"}
            assert float(metadata["format"]["duration"]) >= 1

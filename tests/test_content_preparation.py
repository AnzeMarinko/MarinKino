"""Source retention, complete publication and cheap preparation previews."""

import importlib
import json
import shutil
import subprocess
import sys
from pathlib import Path
from types import ModuleType, SimpleNamespace
from unittest.mock import Mock

import pytest

import prepare_content


@pytest.fixture
def media(monkeypatch):
    # Local preparation config can load .env and create log directories.
    # These tests intentionally avoid credentials and host logging entirely.
    config = ModuleType("content_preparation.config")
    config.FILMS_ROOT = "data/movies"
    monkeypatch.setitem(sys.modules, "content_preparation.config", config)
    audio = importlib.import_module("content_preparation.audio_preparation")
    video = importlib.import_module("content_preparation.video_converter")
    helpers = importlib.import_module("content_preparation.media_tools")
    return SimpleNamespace(audio=audio, video=video, helpers=helpers)


def make_hls(folder, *, complete=True):
    folder.mkdir(exist_ok=True)
    (folder / "metadata.json").write_text('{"title":"Saved title"}')
    (folder / "stream.m4s").write_bytes(b"hls bytes")
    playlist = (
        '#EXTM3U\n#EXT-X-MAP:URI="stream.m4s",BYTERANGE="12@0"\nstream.m4s\n'
    )
    if complete:
        playlist += "#EXT-X-ENDLIST\n"
    (folder / "index.m3u8").write_text(playlist)


def test_dry_run_does_not_import_preparation_or_write(
    tmp_path, monkeypatch, capsys
):
    monkeypatch.setattr(prepare_content, "REPO_ROOT", tmp_path)
    monkeypatch.setattr(prepare_content.shutil, "which", lambda _name: None)
    folder = tmp_path / "data/music"
    folder.mkdir(parents=True)
    (folder / "song.mp3").write_bytes(b"original")
    before = set(tmp_path.rglob("*"))
    assert prepare_content.main(["--kind", "music", "--dry-run"]) == 0
    assert set(tmp_path.rglob("*")) == before
    output = capsys.readouterr().out
    assert "song.mp3" in output
    assert "ffmpeg: MANJKA" in output
    assert "packager" not in output


def test_check_fails_for_missing_movie_packager(monkeypatch):
    monkeypatch.setattr(
        prepare_content.shutil,
        "which",
        lambda name: None if name == "packager" else name,
    )
    assert prepare_content.main(["--kind", "movies", "--check"]) == 1
    assert prepare_content.main(["--kind", "music", "--check"]) == 0


def test_folder_cannot_escape_selected_library(tmp_path, monkeypatch):
    monkeypatch.setattr(prepare_content, "REPO_ROOT", tmp_path / "repo")
    with pytest.raises(SystemExit) as result:
        prepare_content.main(
            ["--kind", "music", "--folder", str(tmp_path), "--dry-run"]
        )
    assert result.value.code == 2


def test_audio_existing_hls_keeps_original(media, tmp_path, monkeypatch):
    source = tmp_path / "song.mp3"
    source.write_bytes(b"original")
    output = tmp_path / "song"
    make_hls(output)
    ffmpeg = Mock()
    monkeypatch.setattr(media.audio, "run_ffmpeg", ffmpeg)
    assert media.audio.convert_mp3_to_hls(str(source), str(output))
    assert source.read_bytes() == b"original"
    ffmpeg.assert_not_called()


def test_incomplete_audio_does_not_destroy_source_or_old_metadata(
    media, tmp_path, monkeypatch
):
    source = tmp_path / "song.mp3"
    source.write_bytes(b"original")
    output = tmp_path / "song"
    make_hls(output, complete=False)
    monkeypatch.setattr(media.audio, "run_ffmpeg", lambda _cmd: False)
    assert not media.audio.convert_mp3_to_hls(str(source), str(output))
    assert source.read_bytes() == b"original"
    assert (
        json.loads((output / "metadata.json").read_text())["title"]
        == "Saved title"
    )
    assert not list(output.glob(".hls-*"))


def test_audio_default_avoids_expensive_analysis(media, tmp_path, monkeypatch):
    mp3 = tmp_path / "song.mp3"
    mp3.write_bytes(b"test")
    for name in ("analyze_audio_file", "analyze_song_semantics"):
        monkeypatch.setattr(
            media.audio,
            name,
            Mock(side_effect=AssertionError("expensive analysis")),
        )
    media.audio.save_hls_metadata(mp3, tmp_path)
    assert (
        json.loads((tmp_path / "metadata.json").read_text())["title"] == "song"
    )


@pytest.mark.skipif(
    shutil.which("ffmpeg") is None,
    reason="FFmpeg required for tiny synthetic fixture",
)
def test_real_single_file_audio_hls_is_ready_and_reusable(
    media, tmp_path, monkeypatch
):
    source = tmp_path / "tone.mp3"
    subprocess.run(
        [
            "ffmpeg",
            "-nostdin",
            "-v",
            "error",
            "-f",
            "lavfi",
            "-i",
            "sine=frequency=440:duration=1",
            str(source),
        ],
        check=True,
    )
    original = source.read_bytes()
    output = tmp_path / "tone"
    assert media.audio.convert_mp3_to_hls(str(source), str(output))
    assert media.helpers.audio_hls_ready(output)
    assert source.read_bytes() == original
    ffmpeg = Mock(side_effect=AssertionError("must reuse HLS"))
    monkeypatch.setattr(media.audio, "run_ffmpeg", ffmpeg)
    assert media.audio.convert_mp3_to_hls(str(source), str(output))


def test_archive_never_overwrites_an_earlier_original(media, tmp_path):
    source = tmp_path / "film.mp4"
    source.write_bytes(b"first")
    first = media.helpers.archive_original(source)
    source.write_bytes(b"second")
    second = media.helpers.archive_original(source)
    assert first != second
    assert first.read_bytes() == b"first"
    assert second.read_bytes() == b"second"
    assert not source.exists()
    assert not media.video.get_videos_list(tmp_path)


def test_failed_movie_packaging_preserves_source_and_existing_subtitles(
    media, tmp_path, monkeypatch
):
    source = tmp_path / "film.mp4"
    source.write_bytes(b"original")
    output = tmp_path / "film"
    output.mkdir()
    subtitle = output / "sl.srt"
    subtitle.write_text("subtitle")

    def process(cmd, **_kwargs):
        if cmd[0] == "ffprobe":
            return SimpleNamespace(stdout="h264")
        raise subprocess.CalledProcessError(1, cmd)

    monkeypatch.setattr(media.video.subprocess, "run", process)
    assert not media.video.convert_to_m3u8(source)
    assert source.read_bytes() == b"original"
    assert subtitle.read_text() == "subtitle"
    assert not list(output.glob(".hls-*"))


def test_movie_packaging_publishes_then_archives_source(
    media, tmp_path, monkeypatch
):
    source = tmp_path / "film.mp4"
    source.write_bytes(b"original")

    def process(cmd, **_kwargs):
        if cmd[0] == "ffprobe":
            return SimpleNamespace(stdout="h264")
        if cmd[0] == "ffmpeg":
            Path(cmd[-1]).write_bytes(b"intermediate")
        if cmd[0] == "packager":
            output = Path(cmd[cmd.index("--hls_master_playlist_output") + 1])
            (output.parent / "video.ts").write_bytes(b"video")
            (output.parent / "audio.ts").write_bytes(b"audio")
            output.write_text(f"#EXTM3U\n{output.parent}/video.m3u8\n")
            (output.parent / "video.m3u8").write_text("#EXTM3U\nvideo.ts\n")
        return SimpleNamespace(stdout="")

    monkeypatch.setattr(media.video.subprocess, "run", process)
    assert media.video.convert_to_m3u8(source)
    assert not source.exists()
    assert (
        tmp_path / ".originals/film.mp4.source"
    ).read_bytes() == b"original"
    assert ".hls-" not in (tmp_path / "film/master.m3u8").read_text()
    assert (tmp_path / "film/video.m3u8").is_file()


def test_merge_failure_keeps_every_input_and_subtitles(
    media, tmp_path, monkeypatch
):
    for name in ("01.mp4", "02.mp4"):
        (tmp_path / name).write_bytes(name.encode())
    extraction = Mock()
    monkeypatch.setattr(media.video, "extract_subtitles_to_srt", extraction)

    def convert(_source, target):
        target.write_bytes(b"converted")
        return "part-0" in str(target)

    monkeypatch.setattr(media.video, "convert_to_mp4", convert)
    with pytest.raises(RuntimeError, match="Pretvorba dela"):
        media.video.convert_videos(tmp_path, merge=True)
    assert (tmp_path / "01.mp4").read_bytes() == b"01.mp4"
    assert (tmp_path / "02.mp4").read_bytes() == b"02.mp4"
    assert not list(tmp_path.glob(".merge-*"))
    assert all(
        call.args[1].parent == tmp_path for call in extraction.call_args_list
    )


def test_mp4_failure_does_not_rename_original(media, tmp_path, monkeypatch):
    source = tmp_path / "input.mp4"
    source.write_bytes(b"original")
    monkeypatch.setattr(media.video, "ensure_aac_audio", lambda _path: False)
    assert not media.video.convert_to_mp4(source, tmp_path / "final.mp4")
    assert source.exists()
    assert not (tmp_path / "final.mp4").exists()


@pytest.mark.skipif(
    shutil.which("ffmpeg") is None or shutil.which("ffprobe") is None,
    reason="FFmpeg/FFprobe required for tiny embedded-subtitle fixture",
)
def test_real_mkv_preserves_embedded_subtitles_outside_staging(
    media, tmp_path
):
    subtitle = tmp_path / "input.srt"
    subtitle.write_text("1\n00:00:00,000 --> 00:00:00,800\nPozdravljen svet\n")
    source = tmp_path / "input.mkv"
    subprocess.run(
        [
            "ffmpeg",
            "-nostdin",
            "-v",
            "error",
            "-f",
            "lavfi",
            "-i",
            "color=c=black:s=160x90:d=1",
            "-f",
            "lavfi",
            "-i",
            "sine=frequency=440:duration=1",
            "-i",
            str(subtitle),
            "-map",
            "0:v",
            "-map",
            "1:a",
            "-map",
            "2:s",
            "-c:v",
            "libx264",
            "-preset",
            "ultrafast",
            "-c:a",
            "aac",
            "-c:s",
            "srt",
            "-metadata:s:s:0",
            "language=slv",
            str(source),
        ],
        check=True,
    )
    destination = tmp_path / "film.mp4"
    assert media.video.convert_to_mp4(source, destination)
    assert destination.is_file()
    assert "Pozdravljen svet" in (tmp_path / "film.slv.srt").read_text()
    assert (tmp_path / ".originals/input.mkv.source").is_file()

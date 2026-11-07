"""Real collection packaging and remuxing; optional local media tools."""

import importlib
import json
import shutil
import subprocess
import sys
from types import ModuleType

import pytest

from movie_catalog import check_folder
from movie_media import movie_sources


def run(command):
    return subprocess.run(
        command,
        check=True,
        capture_output=True,
        text=True,
        timeout=20,
    )


@pytest.mark.skipif(
    not all(shutil.which(tool) for tool in ("ffmpeg", "ffprobe", "packager")),
    reason="Real packaging requires FFmpeg, FFprobe and Shaka Packager",
)
def test_real_collection_hls_survives_publication_and_remux(
    tmp_path, monkeypatch
):
    # Importing local preparation must not read credentials or set up logs.
    config = ModuleType("content_preparation.config")
    config.FILMS_ROOT = str(tmp_path)
    monkeypatch.setitem(sys.modules, "content_preparation.config", config)
    video = importlib.import_module("content_preparation.video_converter")
    monkeypatch.setenv("MARINKINO_PREP_THREADS", "1")

    root = tmp_path / "movies"
    collection = root / "01-series" / "Tiny.Collection"
    collection.mkdir(parents=True)
    (collection / "readme.json").write_text(
        json.dumps({"Title": "Tiny collection", "Year": "2026"})
    )
    originals = {}
    for index, name in enumerate(("01 First.mp4", "02 Second.mp4")):
        source = collection / name
        run(
            [
                "ffmpeg",
                "-nostdin",
                "-v",
                "error",
                "-f",
                "lavfi",
                "-i",
                "testsrc2=size=160x90:rate=24:duration=1",
                "-f",
                "lavfi",
                "-i",
                f"sine=frequency={440 + index * 110}:duration=1",
                "-c:v",
                "libx264",
                "-threads",
                "1",
                "-pix_fmt",
                "yuv420p",
                "-c:a",
                "aac",
                "-movflags",
                "+faststart",
                "-shortest",
                str(source),
            ]
        )
        originals[name] = source.read_bytes()

    prepared = video.convert_videos(collection, collection=True)
    assert {path.name for path in prepared} == set(originals)
    for source in prepared:
        assert video.convert_to_m3u8(source)

    films = check_folder(root)
    assert len(films) == 1
    assert films[0].video_files == []
    sources = movie_sources(vars(films[0]))
    assert [source["id"] for source in sources] == sorted(originals)
    assert all(source["is_hls"] for source in sources)

    for index, source in enumerate(sources):
        playlist = collection / source["path"]
        assert playlist.is_file()
        for manifest in playlist.parent.glob("*.m3u8"):
            content = manifest.read_text()
            assert ".hls-" not in content
            assert str(tmp_path) not in content
        probe = json.loads(
            run(
                [
                    "ffprobe",
                    "-v",
                    "error",
                    "-protocol_whitelist",
                    "file,crypto,data",
                    "-show_entries",
                    "stream=codec_type,codec_name",
                    "-of",
                    "json",
                    str(playlist),
                ]
            ).stdout
        )
        assert {
            (stream["codec_type"], stream["codec_name"])
            for stream in probe["streams"]
        } == {("video", "h264"), ("audio", "aac")}
        output = tmp_path / f"roundtrip-{index}.mp4"
        run(
            [
                "ffmpeg",
                "-nostdin",
                "-v",
                "error",
                "-protocol_whitelist",
                "file,crypto,data",
                "-i",
                str(playlist),
                "-map",
                "0:v?",
                "-map",
                "0:a?",
                "-c",
                "copy",
                "-movflags",
                "+faststart",
                str(output),
            ]
        )
        assert output.stat().st_size > 0

    archived = [
        path.read_bytes() for path in (collection / ".originals").iterdir()
    ]
    assert all(original in archived for original in originals.values())
    assert not list(collection.rglob(".hls-*"))
    assert not list(collection.rglob(".merge-*"))

"""SRT conversion preserves source files and publishes complete UTF-8 VTT."""

import ast
import html
import os
from pathlib import Path

import pytest
import pysrt

from content_preparation import subtitle_encoding


@pytest.mark.parametrize("encoding", ["utf-8", "utf-8-sig", "cp1250"])
def test_srt_conversion_preserves_characters_and_source(
    tmp_path, monkeypatch, encoding
):
    source = tmp_path / "subtitles.srt"
    original = (
        "1\r\n00:00:01,000 --> 00:00:02,500\r\nŽivjo, še čaj.\r\n"
    ).encode(encoding)
    source.write_bytes(original)
    monkeypatch.setattr(
        subtitle_encoding.chardet,
        "detect",
        lambda _data: {"encoding": "Windows-1250"},
    )

    target = subtitle_encoding.convert_srt_to_vtt(source)

    assert target == str(source.with_suffix(".vtt"))
    assert source.with_suffix(".vtt").read_bytes() == (
        "WEBVTT\n\n1\n00:00:01.000 --> 00:00:02.500\nŽivjo, še čaj.\n"
    ).encode("utf-8")
    assert source.read_bytes() == original


@pytest.mark.parametrize("partial", [b"", b"WEBVTT\n\n"])
def test_incomplete_legacy_vtt_is_repaired(tmp_path, partial):
    source = tmp_path / "subtitles.srt"
    source.write_text("1\n00:00:01,000 --> 00:00:02,000\nHello\n")
    target = source.with_suffix(".vtt")
    target.write_bytes(partial)

    subtitle_encoding.convert_srt_to_vtt(source)

    assert target.read_text() == (
        "WEBVTT\n\n1\n00:00:01.000 --> 00:00:02.000\nHello\n"
    )


def test_independent_existing_vtt_is_preserved(tmp_path):
    source = tmp_path / "subtitles.srt"
    source.write_text("1\n00:00:01,000 --> 00:00:02,000\nHello\n")
    target = source.with_suffix(".vtt")
    target.write_text("WEBVTT\n\nDifferent subtitles\n")

    subtitle_encoding.convert_srt_to_vtt(source)

    assert target.read_text() == "WEBVTT\n\nDifferent subtitles\n"


def test_unknown_encoding_fails_without_creating_vtt(tmp_path, monkeypatch):
    source = tmp_path / "subtitles.srt"
    source.write_bytes(b"\x9e")
    monkeypatch.setattr(
        subtitle_encoding.chardet, "detect", lambda _data: {"encoding": None}
    )

    with pytest.raises(ValueError, match="Kodiranja podnapisa"):
        subtitle_encoding.convert_srt_to_vtt(source)

    assert not source.with_suffix(".vtt").exists()


def test_failed_publish_preserves_existing_vtt_and_cleans_temp(
    tmp_path, monkeypatch
):
    source = tmp_path / "subtitles.srt"
    source.write_text("1\n00:00:01,000 --> 00:00:02,000\nHello\n")
    target = source.with_suffix(".vtt")
    target.write_text("WEBVTT\n\n")

    def fail_replace(_source, _target):
        raise OSError("publish failed")

    monkeypatch.setattr(os, "replace", fail_replace)
    with pytest.raises(OSError, match="publish failed"):
        subtitle_encoding.convert_srt_to_vtt(source)

    assert target.read_text() == "WEBVTT\n\n"
    assert sorted(p.name for p in tmp_path.iterdir()) == [
        "subtitles.srt",
        "subtitles.vtt",
    ]


def _load_definition(relative_path, name, namespace):
    source = Path(__file__).resolve().parents[1] / relative_path
    tree = ast.parse(source.read_text())
    node = next(
        node for node in tree.body if getattr(node, "name", None) == name
    )
    exec(
        compile(ast.Module(body=[node], type_ignores=[]), source, "exec"),
        namespace,
    )
    return namespace[name]


def test_movie_metadata_repairs_incomplete_vtt_and_lists_it_once(tmp_path):
    source = tmp_path / "subtitles.srt"
    source.write_text("1\n00:00:01,000 --> 00:00:02,000\nHello\n")
    target = source.with_suffix(".vtt")
    target.write_text("WEBVTT\n\n")
    metadata_class = _load_definition(
        "src/content_preparation/get_movie_metadata.py",
        "MovieMetadata",
        {
            "Path": Path,
            "html": html,
            "convert_srt_to_vtt": subtitle_encoding.convert_srt_to_vtt,
            "get_movie_metadata": lambda *_args: ({}, "cover.jpg"),
            "create_thumbnail": lambda cover: cover,
        },
    )

    metadata = metadata_class(str(tmp_path))

    assert metadata.subtitles == ["subtitles.vtt"]
    assert "Hello" in target.read_text()


def test_subtitle_preview_reads_windows_1250(tmp_path, monkeypatch):
    source = tmp_path / "subtitles.srt"
    source.write_bytes(
        "1\n00:00:01,000 --> 00:00:02,000\nŽivjo, še čaj.\n".encode(
            "cp1250"
        )
    )
    monkeypatch.setattr(
        subtitle_encoding.chardet,
        "detect",
        lambda _data: {"encoding": "Windows-1250"},
    )
    extract = _load_definition(
        "src/content_preparation/subtitles/rescale_captions.py",
        "extract_subtitles",
        {
            "pysrt": pysrt,
            "read_subtitle": subtitle_encoding.read_subtitle,
            "time_to_timestamp": lambda value: (
                value.hour * 3600
                + value.minute * 60
                + value.second
                + value.microsecond / 1_000_000
            ),
        },
    )

    assert extract(str(source)) == [(1.0, 2.0, "Živjo, še čaj.")]

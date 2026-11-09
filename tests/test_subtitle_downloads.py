"""Normalize local subtitles before requesting only missing languages."""

import io
import zipfile
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock

import pytest

from content_preparation import subtitle_inventory as inventory
from content_preparation import subtitles
from content_preparation.subtitles import download_subtitles as download


def put(folder, name, text="subtitle"):
    path = folder / name
    path.write_text(text, encoding="utf-8")
    return path


def test_normalizes_filename_codes_and_pairs_without_losing_backups(tmp_path):
    put(tmp_path, "Film.slv.srt")
    put(tmp_path, "Film.slv.vtt", "WEBVTT\n\nsubtitle")
    put(tmp_path, ".Film.slv.srt.original", "backup")
    put(tmp_path, "Film.eng.srt")
    present, renames = inventory.normalize_subtitles(tmp_path)
    assert present == {"sl", "en"}
    assert renames == {
        "Film.eng.srt": "subtitles-enSubs.srt",
        "Film.slv.srt": "subtitles-SloSubs.srt",
        "Film.slv.vtt": "subtitles-SloSubs.vtt",
    }
    assert (
        tmp_path / ".subtitles-SloSubs.srt.original"
    ).read_text() == "backup"
    assert inventory.normalize_subtitles(tmp_path) == ({"sl", "en"}, {})


def test_detects_language_from_text_when_name_is_unknown(tmp_path):
    put(
        tmp_path,
        "Film.srt",
        "1\n00:00:01,000 --> 00:00:05,000\n"
        "This is a very long English sentence about our family and the world. "
        "I know that you have been waiting for us to come home.\n",
    )
    present, _renames = inventory.normalize_subtitles(tmp_path)
    assert present == {"en"}
    assert (tmp_path / "subtitles-enSubs.srt").exists()


def test_standardized_other_language_is_not_redetected(tmp_path, monkeypatch):
    put(tmp_path, "subtitles-ruSubs.srt", "short")
    detect = Mock(side_effect=AssertionError("known language"))
    monkeypatch.setattr(inventory, "_detect_language", detect)
    assert inventory.normalize_subtitles(tmp_path) == ({"ru"}, {})
    detect.assert_not_called()


def test_terminal_selection_keeps_chosen_and_archives_other(
    tmp_path, monkeypatch
):
    put(tmp_path, "first.en.srt", "first")
    put(tmp_path, "second.en.srt", "second")
    monkeypatch.setattr("builtins.input", lambda _prompt: "2")
    assert inventory.normalize_subtitles_interactive(tmp_path)[0] == {"en"}
    assert (tmp_path / "subtitles-enSubs.srt").read_text() == "second"
    assert (tmp_path / ".originals/first.en.srt.source").read_text() == "first"


def test_unknown_language_stops_without_changing_files(tmp_path):
    put(tmp_path, "unknown.srt", "Hi")
    put(tmp_path, "Film.eng.srt")
    with pytest.raises(ValueError, match="zanesljivo določiti"):
        inventory.normalize_subtitles(tmp_path)
    assert sorted(p.name for p in tmp_path.iterdir()) == [
        "Film.eng.srt",
        "unknown.srt",
    ]


def test_conflicting_target_stops_before_archiving(tmp_path):
    put(tmp_path, "subtitles-SloSubs.srt", "existing")
    put(tmp_path, "Film.sl.srt", "chosen")
    put(tmp_path, ".subtitles-SloSubs.srt.original", "old backup")
    put(tmp_path, ".Film.sl.srt.original", "chosen backup")
    with pytest.raises(ValueError, match="varnostne kopije"):
        inventory.normalize_subtitles(tmp_path, {"sl": "Film.sl.srt"})
    assert (tmp_path / "subtitles-SloSubs.srt").read_text() == "existing"
    assert (tmp_path / "Film.sl.srt").read_text() == "chosen"
    assert not (tmp_path / ".originals").exists()


def test_duplicate_selection_required_and_unselected_pair_archived(tmp_path):
    put(tmp_path, "first.eng.srt", "first")
    put(tmp_path, "first.eng.vtt", "first vtt")
    put(tmp_path, "second.en.srt", "second")
    put(tmp_path, "second.en.vtt", "second vtt")
    with pytest.raises(inventory.SubtitleSelectionRequiredError) as error:
        inventory.normalize_subtitles(tmp_path)
    assert error.value.groups == {"en": ["first.eng.srt", "second.en.srt"]}
    assert not (tmp_path / ".originals").exists()
    present, _renames = inventory.normalize_subtitles(
        tmp_path, {"en": "second.en.srt"}
    )
    assert present == {"en"}
    assert (tmp_path / "subtitles-enSubs.srt").read_text() == "second"
    assert (tmp_path / "subtitles-enSubs.vtt").read_text() == "second vtt"
    assert (
        tmp_path / ".originals/first.eng.srt.source"
    ).read_text() == "first"
    assert (
        tmp_path / ".originals/first.eng.vtt.source"
    ).read_text() == "first vtt"


def test_no_network_if_languages_already_exist(tmp_path, monkeypatch):
    put(tmp_path, "Film.SLV.srt")
    put(tmp_path, "Film.EN.vtt")
    search = Mock(side_effect=AssertionError("network must not be used"))
    monkeypatch.setattr(download, "search_opensubtitles", search)
    assert not download.get_subtitles("Film", "2025", "tt1234567", tmp_path)
    search.assert_not_called()
    assert (tmp_path / "subtitles-SloSubs.srt").exists()
    assert (tmp_path / "subtitles-enSubs.vtt").exists()


def test_duplicate_or_unknown_stops_before_network(tmp_path, monkeypatch):
    put(tmp_path, "first.en.srt")
    put(tmp_path, "second.en.srt")
    search = Mock()
    monkeypatch.setattr(download, "search_opensubtitles", search)
    with pytest.raises(inventory.SubtitleSelectionRequiredError):
        download.get_subtitles("Film", "2025", "tt1234567", tmp_path)
    search.assert_not_called()


def test_only_missing_languages_searched_and_fallback_uses_remaining(
    tmp_path, monkeypatch
):
    put(tmp_path, "Film.sl.srt")
    search = Mock(return_value=([], None))
    fallback = Mock(return_value=[])
    monkeypatch.setattr(download, "search_opensubtitles", search)
    monkeypatch.setattr(download, "search_podnapisi_safe", fallback)
    monkeypatch.setattr(download.time, "sleep", lambda _seconds: None)
    assert not download.get_subtitles("Film", "2025", "tt1234567", tmp_path)
    search.assert_called_once_with("tt1234567", ["en"])
    fallback.assert_called_once_with("Film", "2025", ["en"])


def test_partial_primary_result_falls_back_only_for_missing_language(
    tmp_path, monkeypatch
):
    monkeypatch.setattr(
        download,
        "search_opensubtitles",
        Mock(return_value=([{"lang": "sl", "url": 1}], None)),
    )
    saved = Mock()
    fallback = Mock(return_value=[])
    monkeypatch.setattr(download, "download_opensubtitles", saved)
    monkeypatch.setattr(download, "search_podnapisi_safe", fallback)
    monkeypatch.setattr(download.time, "sleep", lambda _seconds: None)
    assert download.get_subtitles("Film", "2025", "tt1234567", tmp_path)
    fallback.assert_called_once_with("Film", "2025", ["en"])
    saved.assert_called_once()


def test_podnapisi_zip_extracts_only_subtitles_without_overwriting(
    tmp_path, monkeypatch
):
    data = io.BytesIO()
    with zipfile.ZipFile(data, "w") as archive:
        archive.writestr("../outside.srt", "subtitle")
        archive.writestr("readme.json", "do not extract")
    response = SimpleNamespace(
        content=data.getvalue(), raise_for_status=Mock()
    )
    monkeypatch.setattr(download.session, "get", lambda *_a, **_kw: response)
    result = download.download_podnapisi_safe(
        {"url": "https://example.invalid", "lang": "en"}, 0, str(tmp_path)
    )
    assert Path(result[0]).read_text() == "subtitle"
    assert not (tmp_path.parent / "outside.srt").exists()
    assert not (tmp_path / "readme.json").exists()
    with pytest.raises(FileExistsError):
        download.download_podnapisi_safe(
            {"url": "https://example.invalid", "lang": "en"}, 0, str(tmp_path)
        )


def test_legacy_translation_preserves_downloaded_marker_and_vtt_pair(
    tmp_path, monkeypatch
):
    source = put(tmp_path, "film.en-Downloaded.srt", "english")
    put(tmp_path, "film.en-Downloaded.vtt", "english vtt")
    monkeypatch.setattr(subtitles, "extract_audio", Mock())
    network = Mock()
    monkeypatch.setattr(subtitles, "get_subtitles", network)
    monkeypatch.setattr(subtitles, "rescale_subtitles", Mock())

    def translate(path):
        source_path = Path(path)
        source_path.rename(tmp_path / "subtitles-enSubs.srt")
        put(tmp_path, "subtitles-SloSubs-auto.srt", "slovenian")
        return {"input_language": "en"}

    monkeypatch.setattr(subtitles, "translate", translate)
    subtitles.prepare_subtitles(
        tmp_path, tmp_path / "movie.mp4",
        SimpleNamespace(title="Film", year="2025", imdb_id="tt1234567"),
    )
    assert not source.exists()
    assert (tmp_path / "subtitles-enSubs-Downloaded.srt").read_text() == (
        "english"
    )
    assert (tmp_path / "subtitles-enSubs-Downloaded.vtt").read_text() == (
        "english vtt"
    )
    assert (tmp_path / "subtitles-SloSubs-auto.srt").exists()
    subtitles.rescale_subtitles.assert_called_once()
    network.assert_not_called()

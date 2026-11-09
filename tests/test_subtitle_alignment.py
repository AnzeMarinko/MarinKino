"""Downloaded subtitles are finalized only after successful alignment."""

from types import SimpleNamespace
from unittest.mock import Mock

import pytest

from content_preparation import interactive_pipeline as pipeline
from content_preparation import subtitle_alignment as alignment
from content_preparation.subtitles import rescale_captions as rescale


@pytest.fixture
def proposal():
    return {
        "subtitles": [(1.0, 3.0, "Živjo"), (4.0, 5.0, "Drugi stavek")],
        "scale": 1.0,
        "shift": 2.0,
    }


@pytest.mark.parametrize(
    ("seconds", "expected"),
    [
        (3, "00:00:03,000"),
        (3.125, "00:00:03,125"),
        (90061.5, "25:01:01,500"),
        (-2, "00:00:00,000"),
    ],
)
def test_alignment_timestamps_are_valid_srt(seconds, expected):
    assert rescale.format_time(seconds) == expected


def test_confirmed_alignment_finalizes_srt_vtt_and_original(
    tmp_path, monkeypatch, proposal
):
    source = tmp_path / "subtitles1-enSubs-Downloaded.srt"
    original = b"1\n00:00:01,000 --> 00:00:03,000\nHello\n"
    source.write_bytes(original)
    old_vtt = source.with_suffix(".vtt")
    old_vtt.write_text("WEBVTT\n\nOld timings\n", encoding="utf-8")
    video = tmp_path / "video.mp4"
    monkeypatch.setattr(pipeline, "ask_yes_no", lambda *_a, **_kw: True)
    monkeypatch.setattr(pipeline, "propose_alignment", lambda *_a: proposal)
    monkeypatch.setattr(
        pipeline,
        "preview_and_confirm_alignment",
        lambda *_a: {"confirmed": True, "scale": 1.0, "shift": 2.0},
    )

    assert pipeline._needs_alignment(tmp_path)
    pipeline.step_align_subtitles(tmp_path, video)

    final = tmp_path / "subtitles-enSubs.srt"
    assert not source.exists()
    assert not old_vtt.exists()
    assert "00:00:03,000 --> 00:00:05,000" in final.read_text()
    assert "00:00:03.000 --> 00:00:05.000" in final.with_suffix(
        ".vtt"
    ).read_text()
    assert alignment.alignment_backup(final).read_bytes() == original
    assert (
        tmp_path / ".originals/subtitles1-enSubs-Downloaded.vtt.source"
    ).read_text() == "WEBVTT\n\nOld timings\n"
    assert not pipeline._needs_alignment(tmp_path)
    assert not list(tmp_path.glob(".subtitle-*-*"))


@pytest.mark.parametrize("reason", ["declined", "cancelled", "no_proposal"])
def test_unconfirmed_alignment_remains_pending(tmp_path, monkeypatch, reason):
    source = tmp_path / "subtitles-enSubs-Downloaded.srt"
    source.write_text("original")
    monkeypatch.setattr(
        pipeline, "ask_yes_no", lambda *_a, **_kw: reason != "declined"
    )
    monkeypatch.setattr(
        pipeline,
        "propose_alignment",
        lambda *_a: None if reason == "no_proposal" else {},
    )
    monkeypatch.setattr(
        pipeline,
        "preview_and_confirm_alignment",
        lambda *_a: {"confirmed": False},
    )
    pipeline.step_align_subtitles(tmp_path, tmp_path / "video.mp4")
    assert source.read_text() == "original"
    assert pipeline._needs_alignment(tmp_path)
    assert not (tmp_path / "subtitles-enSubs.srt").exists()


def test_previous_alignment_backup_recovers_without_realigning(
    tmp_path, monkeypatch
):
    source = tmp_path / "film.sl-Downloaded.srt"
    source.write_text("1\n00:00:03,000 --> 00:00:05,000\nŽivjo\n")
    alignment.alignment_backup(source).write_bytes(b"old original")
    ask = Mock(side_effect=AssertionError("alignment already completed"))
    monkeypatch.setattr(pipeline, "ask_yes_no", ask)

    pipeline.step_align_subtitles(tmp_path, tmp_path / "video.mp4")

    final = tmp_path / "subtitles-SloSubs.srt"
    assert "00:00:03,000" in final.read_text()
    assert "00:00:03.000" in final.with_suffix(".vtt").read_text()
    assert alignment.alignment_backup(final).read_bytes() == b"old original"
    assert not source.exists()
    ask.assert_not_called()


def test_alignment_refuses_existing_target_without_touching_inputs(
    tmp_path, proposal
):
    source = tmp_path / "subtitles-enSubs-Downloaded.srt"
    source.write_bytes(b"original")
    existing = tmp_path / "subtitles-enSubs.vtt"
    existing.write_bytes(b"keep")

    with pytest.raises(FileExistsError):
        rescale.apply_downloaded_alignment(proposal, str(source))

    assert source.read_bytes() == b"original"
    assert existing.read_bytes() == b"keep"
    assert not (tmp_path / "subtitles-enSubs.srt").exists()
    assert not list(tmp_path.glob(".subtitle-*-*"))


def test_failed_publish_rolls_back_without_losing_inputs(
    tmp_path, monkeypatch, proposal
):
    source = tmp_path / "subtitles-enSubs-Downloaded.srt"
    source.write_bytes(b"original")
    old_vtt = source.with_suffix(".vtt")
    old_vtt.write_bytes(b"old vtt")
    link = alignment.os.link
    calls = 0

    def fail_second_link(src, dst, **kwargs):
        nonlocal calls
        calls += 1
        if calls == 2:
            raise OSError("publication failed")
        return link(src, dst, **kwargs)

    monkeypatch.setattr(alignment.os, "link", fail_second_link)
    with pytest.raises(OSError, match="publication failed"):
        rescale.apply_downloaded_alignment(proposal, str(source))
    assert source.read_bytes() == b"original"
    assert old_vtt.read_bytes() == b"old vtt"
    assert not (tmp_path / "subtitles-enSubs.srt").exists()
    assert not list(tmp_path.glob(".subtitle-*-*"))


def test_legacy_rescale_finalizes_and_rejects_unreliable_proposal(
    tmp_path, monkeypatch, proposal
):
    source = tmp_path / "subtitles-enSubs-Downloaded.srt"
    source.write_text("original")
    monkeypatch.setattr(rescale, "propose_alignment", lambda *_a: proposal)
    proposal["shift"] = 100
    assert rescale.rescale_subtitles(tmp_path, str(source), "video") is None
    assert source.exists()
    proposal["shift"] = 2
    target = rescale.rescale_subtitles(tmp_path, str(source), "video")
    assert target == tmp_path / "subtitles-enSubs.srt"
    assert alignment.alignment_backup(target).read_text() == "original"


@pytest.mark.parametrize("downloaded", [True, False])
def test_speech_analysis_runs_at_successful_download(
    tmp_path, monkeypatch, downloaded
):
    download = Mock(return_value=downloaded)
    extract = Mock()
    monkeypatch.setattr(pipeline, "get_subtitles", download)
    monkeypatch.setattr(pipeline, "extract_audio", extract)
    monkeypatch.setattr(pipeline, "ask_yes_no", lambda *_a, **_kw: True)
    metadata = SimpleNamespace(title="Film", year="2025", imdb_id="tt1234567")
    video = tmp_path / "film.mp4"
    pipeline.step_check_download_subtitles(tmp_path, metadata, video)
    download.assert_called_once()
    if downloaded:
        extract.assert_called_once_with(str(tmp_path), str(video))
    else:
        extract.assert_not_called()


def test_split_movie_skips_automatic_subtitles_after_merge(
    tmp_path, monkeypatch, caplog
):
    first = tmp_path / "part1.mp4"
    second = tmp_path / "part2.mp4"
    movie = tmp_path / "merged.mp4"
    metadata = SimpleNamespace(video_files_m3u8=[], imdb_id="tt1234567")
    monkeypatch.setattr(
        pipeline,
        "get_videos_list",
        Mock(side_effect=[[first, second], [movie], [movie]]),
    )
    monkeypatch.setattr(
        pipeline, "step_convert_videos", lambda _folder: (tmp_path, False)
    )
    monkeypatch.setattr(
        pipeline, "step_fetch_metadata", lambda _folder: metadata
    )
    download = Mock()
    monkeypatch.setattr(pipeline, "step_check_download_subtitles", download)
    monkeypatch.setattr(pipeline, "convert_to_m3u8", lambda _video: True)
    pipeline.process_single_movie(tmp_path)
    download.assert_not_called()
    assert pipeline._load_readme(tmp_path)["subtitles_manual_required"] is True
    assert "podnapise uredi ročno" in caplog.text

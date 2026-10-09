"""Exercise background playback playlists without application services."""

import importlib.util
import shutil
import subprocess
import sys
from pathlib import Path
from types import ModuleType, SimpleNamespace
from unittest.mock import Mock, patch
from urllib.parse import quote

import pytest
from flask import Flask
from flask_login import LoginManager, UserMixin


class User(UserMixin):
    def __init__(self, username):
        self.id = username


@pytest.fixture
def music(tmp_path, monkeypatch):
    utilities = ModuleType("utils")
    utilities.FLASK_ENV = "testing"
    utilities.is_current_admin_view = Mock(return_value=False)
    utilities.safe_path = Mock()
    source = Path(__file__).resolve().parents[1] / "src"
    spec = importlib.util.spec_from_file_location(
        "session_test_music", source / "blueprints" / "music_bp.py"
    )
    module = importlib.util.module_from_spec(spec)
    # Keep discovery away from the user's runtime media library.
    with (
        patch.dict(sys.modules, {"utils": utilities}),
        patch.object(Path, "glob", return_value=[]),
    ):
        spec.loader.exec_module(module)
    monkeypatch.setattr(module, "MUSIC_ROOT", tmp_path)
    tracks = [f"Album/track {index:02d} č" for index in range(12)]
    metadata = {}
    for track in tracks:
        directory = tmp_path / track
        directory.mkdir(parents=True)
        playlist = directory / "index.m3u8"
        playlist.write_text(
            '#EXTM3U\n#EXT-X-VERSION:7\n#EXT-X-TARGETDURATION:6\n'
            '#EXT-X-MEDIA-SEQUENCE:0\n#EXT-X-PLAYLIST-TYPE:VOD\n'
            '#EXT-X-MAP:URI="stream.m4s",BYTERANGE="320@0"\n'
            '#EXTINF:6.0,\n#EXT-X-BYTERANGE:512@320\nstream.m4s\n'
            '#EXTINF:3.5,\n#EXT-X-BYTERANGE:256@832\nstream.m4s\n'
            '#EXT-X-ENDLIST\n',
            encoding="utf-8",
        )
        metadata[track] = {"hls_path": f"{track}/index.m3u8"}
    module.music_metadata = metadata
    module.music_albums = [{"name": "Vse", "songs": tracks}]
    app = Flask(__name__)
    app.config.update(TESTING=True, SECRET_KEY="music-session-tests-only")
    manager = LoginManager(app)
    manager.user_loader(User)
    app.register_blueprint(module.music_bp)
    client = app.test_client()
    with client.session_transaction() as session:
        session["_user_id"] = "listener"
        session["_fresh"] = True
    return SimpleNamespace(
        app=app, client=client, module=module, tracks=tracks, root=tmp_path,
    )


@pytest.mark.parametrize("mode", ["sequential", "random", "similar"])
def test_session_contains_all_candidates_and_preserves_hls_maps(music, mode):
    response = music.client.post(
        "/music/session-playlist",
        json={"track_ids": music.tracks, "mode": mode},
    )
    assert response.status_code == 200
    payload = response.get_json()
    assert payload["tracks"][0]["id"] == music.tracks[0]
    assert len(payload["tracks"]) == 12
    assert {track["id"] for track in payload["tracks"]} == set(music.tracks)
    assert all(track["duration"] == 9.5 for track in payload["tracks"])
    if mode == "sequential":
        assert [track["id"] for track in payload["tracks"]] == music.tracks

    response = music.client.get(payload["url"])
    assert response.status_code == 200
    assert response.mimetype == "application/vnd.apple.mpegurl"
    assert response.headers["Cache-Control"] == "no-store"
    playlist = response.get_data(as_text=True)
    assert playlist.count("#EXT-X-DISCONTINUITY\n") == 11
    assert playlist.count("#EXT-X-MAP:") == 12
    assert playlist.count("#EXT-X-ENDLIST\n") == 1
    assert playlist.count("#EXT-X-TARGETDURATION:") == 1
    assert playlist.count('#EXT-X-BYTERANGE:512@320\n') == 12
    for track in music.tracks:
        uri = "/music/hls/" + quote(f"{track}/stream.m4s", safe="/")
        assert f'#EXT-X-MAP:URI="{uri}",BYTERANGE="320@0"' in playlist


def test_sequential_session_stops_before_file_only_track(music):
    music.module.music_metadata[music.tracks[2]] = {"file_path": "raw.mp3"}
    response = music.client.post(
        "/music/session-playlist", json={"track_ids": music.tracks},
    )
    assert response.status_code == 200
    returned_ids = [track["id"] for track in response.json["tracks"]]
    assert returned_ids == music.tracks[:2]


def test_similar_session_excludes_tracks_outside_seed_style(music):
    for index, track in enumerate(music.tracks):
        feature = 0.2 + index * 0.01 if index < 3 else 0.8
        music.module.music_metadata[track]["audio_features"] = dict.fromkeys(
            ("tempo", "energy", "mood", "instruments"), feature,
        )
    response = music.client.post(
        "/music/session-playlist",
        json={"track_ids": music.tracks, "mode": "similar"},
    )
    assert response.status_code == 200
    assert {track["id"] for track in response.json["tracks"]} == set(
        music.tracks[:3]
    )


def test_similar_searches_beyond_first_two_hundred_candidates(music):
    feature_keys = ("tempo", "energy", "mood", "instruments")
    seed = music.tracks[0]
    source = music.module.music_metadata[seed]["hls_path"]
    music.module.music_metadata[seed]["audio_features"] = dict.fromkeys(
        feature_keys, 0.2,
    )
    tracks = [seed]
    for index in range(300):
        track = f"extra-{index}"
        tracks.append(track)
        music.module.music_metadata[track] = {
            "hls_path": source,
            "audio_features": dict.fromkeys(
                feature_keys, 0.201 if index == 299 else 0.8,
            ),
        }
    response = music.client.post(
        "/music/session-playlist",
        json={"track_ids": tracks, "mode": "similar"},
    )
    assert response.status_code == 200
    returned = [track["id"] for track in response.json["tracks"]]
    assert returned == [seed, "extra-299"]


def test_recommendation_and_native_session_share_strict_similar_policy(music):
    for index, track in enumerate(music.tracks):
        music.module.music_metadata[track]["audio_features"] = dict.fromkeys(
            ("tempo", "energy", "mood", "instruments"),
            0.2 if index < 2 else 0.8,
        )
    selector = Mock(wraps=music.module.select_next_song)
    music.module.select_next_song = selector
    response = music.client.post(
        "/music/recommendation/next",
        json={
            "current_song_id": music.tracks[0], "playlist": music.tracks,
            "mode": "similar",
        },
    )
    assert response.status_code == 200
    assert response.json["song"]["id"] == music.tracks[1]
    assert selector.call_args.kwargs["randomness_weight"] == 0.025
    response = music.client.post(
        "/music/session-playlist",
        json={"track_ids": music.tracks, "mode": "similar"},
    )
    assert response.status_code == 200
    returned = [track["id"] for track in response.json["tracks"]]
    assert returned == music.tracks[:2]
    assert selector.call_args.kwargs["randomness_weight"] == 0.025


@pytest.mark.parametrize("invalid", ["oversized", "unknown", "hidden"])
def test_invalid_session_candidates_are_rejected(music, invalid):
    tracks = music.tracks[:]
    if invalid == "oversized":
        tracks = [tracks[0]] * 202
    elif invalid == "unknown":
        tracks.append("missing")
    else:
        music.module.music_metadata[tracks[0]]["only_admin"] = True
    response = music.client.post(
        "/music/session-playlist", json={"track_ids": tracks},
    )
    assert response.status_code == 400


def test_session_playlist_is_scoped_to_authenticated_owner_and_expires(music):
    response = music.client.post(
        "/music/session-playlist", json={"track_ids": music.tracks},
    )
    url = response.json["url"]
    with music.client.session_transaction() as session:
        session["_user_id"] = "another-listener"
    assert music.client.get(url).status_code == 404
    with music.client.session_transaction() as session:
        session["_user_id"] = "listener"
    assert music.client.get(url).status_code == 200
    next(iter(music.module.hls_sessions.values()))["expires_at"] = 0
    assert music.client.get(url).status_code == 404
    with music.client.session_transaction() as session:
        session.clear()
    assert music.client.get(url).status_code == 401


@pytest.mark.skipif(not shutil.which("ffmpeg"), reason="FFmpeg unavailable")
def test_session_preserves_decodable_fmp4_byte_ranges_for_each_track(music):
    paths = []
    for index, frequency in enumerate((440, 880)):
        directory = music.root / f"real{index}"
        directory.mkdir()
        playlist = directory / "index.m3u8"
        subprocess.run(
            [
                "ffmpeg", "-v", "error", "-f", "lavfi", "-i",
                f"sine=frequency={frequency}:duration=2", "-c:a", "aac",
                "-f", "hls", "-hls_time", "1", "-hls_playlist_type", "vod",
                "-hls_segment_type", "fmp4", "-hls_flags", "single_file",
                "-hls_segment_filename", str(directory / "stream.m4s"),
                str(playlist),
            ],
            check=True, capture_output=True,
        )
        paths.append(playlist.relative_to(music.root).as_posix())
    session = music.module._make_hls_session_playlist(paths)
    session = session.replace("/music/hls/", music.root.as_posix() + "/")
    # FFmpeg's HLS demuxer ignores EXT-X-DISCONTINUITY and reuses its MOV
    # parser. Decode each discontinuity section to check rewritten ranges.
    header = session.split("#EXT-X-MAP:", 1)[0]
    decoded_seconds = 0
    for index, section in enumerate(session.split("#EXT-X-DISCONTINUITY\n")):
        if index:
            section = header + section
        if "#EXT-X-ENDLIST" not in section:
            section += "#EXT-X-ENDLIST\n"
        playlist = music.root / f"section{index}.m3u8"
        playlist.write_text(section, encoding="utf-8")
        decoded = subprocess.run(
            [
                "ffmpeg", "-v", "error", "-allowed_extensions", "ALL", "-i",
                str(playlist), "-ar", "16000", "-ac", "1", "-f", "s16le",
                "-",
            ],
            check=True, capture_output=True,
        )
        decoded_seconds += len(decoded.stdout) / (16000 * 2)
    expected = sum(
        music.module._get_hls_playlist_duration(path) for path in paths
    )
    assert decoded_seconds == pytest.approx(expected, abs=0.1)

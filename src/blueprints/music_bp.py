import json
import logging
import os
import shutil
from pathlib import Path
from urllib.parse import quote

from flask import (
    Blueprint,
    abort,
    make_response,
    render_template,
    send_from_directory,
)
from flask_login import current_user, login_required
from mutagen.easyid3 import EasyID3
from mutagen.mp3 import MP3, HeaderNotFoundError

from utils import FLASK_ENV, is_current_admin_view, safe_path

log = logging.getLogger(__name__)

music_bp = Blueprint("music", __name__)

REPO_ROOT = Path(__file__).resolve().parents[2]
MUSIC_ROOT = REPO_ROOT / "data" / "music"
RADIO_STORIES_ROOT = REPO_ROOT / "data" / "radio-stories"

PLAYABLE_AUDIO_EXTENSIONS = (".mp3", ".m4a", ".wav")
HLS_PLAYLIST_NAMES = ("index.m3u8", "master.m3u8")


def _track_id_from_audio_path(relative_path):
    return os.path.splitext(relative_path)[0]


def _track_id_from_hls_path(relative_path):
    playlist_name = os.path.basename(relative_path)
    parent_dir = os.path.dirname(relative_path)
    if playlist_name in HLS_PLAYLIST_NAMES and parent_dir:
        return parent_dir
    return os.path.splitext(relative_path)[0]


def _find_hls_playlist(root_dir, track_id):
    for playlist_name in HLS_PLAYLIST_NAMES:
        candidate = os.path.join(track_id, playlist_name)
        if os.path.exists(os.path.join(root_dir, candidate)):
            return candidate
    return None


def _read_hls_json_metadata(hls_dir_path: Path):
    """Prebere metadata.json datoteko znotraj HLS mape, če obstaja."""
    json_path = hls_dir_path / "metadata.json"
    if json_path.exists():
        try:
            with open(json_path, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception as e:
            log.error(f"❌ Napaka pri branju {json_path}: {e}")
    return None


def _guess_media_mimetype(filename):
    lower_name = filename.lower()
    if lower_name.endswith(".mp3"):
        return "audio/mpeg"
    if lower_name.endswith(".m4a"):
        return "audio/mp4"
    if lower_name.endswith(".wav"):
        return "audio/wav"
    if lower_name.endswith(".m3u8"):
        return "application/vnd.apple.mpegurl"
    if lower_name.endswith(".m4s"):
        return "video/iso.segment"
    if lower_name.endswith(".ts"):
        return "video/mp2t"
    if lower_name.endswith(".mp4"):
        return "video/mp4"
    return None


def _build_internal_media_response(data_root, protected_root, filename):
    try:
        _ = safe_path(data_root, filename)
        if not os.path.exists(os.path.join(data_root, filename)):
            abort(404)
    except ValueError:
        abort(404)

    if FLASK_ENV == "production":
        response = make_response()
        safe_filename = quote(filename, safe="/")
        if not safe_filename.startswith("/"):
            safe_filename = "/" + safe_filename
        response.headers["X-Accel-Redirect"] = (
            f"/{protected_root}{safe_filename}"
        )
    else:
        response = send_from_directory(data_root, filename, conditional=True)
        response.headers["Accept-Ranges"] = "bytes"

    mimetype = _guess_media_mimetype(filename)
    if mimetype:
        response.headers["Content-Type"] = mimetype
    return response


def _read_audio_metadata(full_path, fallback_title, default_album):
    metadata = {
        "title": fallback_title,
        "artist": "",
        "album": default_album,
        "duration": 0,
    }

    if not full_path.lower().endswith(".mp3"):
        return metadata

    try:
        audio = MP3(full_path, ID3=EasyID3)
    except HeaderNotFoundError:
        return metadata
    except Exception as e:
        log.error(f"❌ Napaka pri {full_path}: {e}")
        return metadata

    title_tags = audio.get("title") or [fallback_title]
    artist_tags = audio.get("artist") or []
    album_tags = audio.get("album") or [default_album]

    metadata["title"] = ", ".join(title_tags)
    metadata["artist"] = " - ".join(artist_tags)
    metadata["album"] = " - ".join(album_tags)
    metadata["duration"] = int(
        getattr(getattr(audio, "info", None), "length", 0)
        if hasattr(audio, "info")
        else 0
    )
    return metadata


def _discover_media_library(root_dir, default_album, include_genre=False):
    root_path = Path(root_dir)
    tracks = {}

    # 1. Najprej preiščemo obstoječe MP3 / M4A / WAV datoteke
    for extension in PLAYABLE_AUDIO_EXTENSIONS:
        pattern = f"**/*{extension}"
        for audio_path in root_path.glob(pattern):
            relative_path = audio_path.relative_to(root_path).as_posix()
            track_id = _track_id_from_audio_path(relative_path)
            fallback_title = audio_path.stem
            metadata = _read_audio_metadata(
                str(audio_path), fallback_title, default_album
            )
            genre = (
                relative_path.split("/")[0].strip() if include_genre else ""
            )

            item = tracks.setdefault(
                track_id,
                {
                    "title": metadata["title"],
                    "artist": metadata["artist"],
                    "album": metadata["album"],
                    "duration": metadata["duration"],
                    "file_path": None,
                    "hls_path": None,
                    "delete_path": relative_path,
                },
            )
            item["file_path"] = relative_path
            item["delete_path"] = relative_path
            if metadata["title"]:
                item["title"] = metadata["title"]
            if metadata["artist"]:
                item["artist"] = metadata["artist"]
            if metadata["album"]:
                item["album"] = metadata["album"]
            if metadata["duration"]:
                item["duration"] = metadata["duration"]
            if include_genre:
                item["genre"] = genre
                item["only_admin"] = "Neurejena-glasba/" in relative_path

            hls_playlist = _find_hls_playlist(root_dir, track_id)
            if hls_playlist:
                item["hls_path"] = hls_playlist

    # 2. Poiščemo vse HLS predvajalne sezname
    # (tudi tiste, ki nimajo več .mp3 datoteke)
    for playlist_name in HLS_PLAYLIST_NAMES:
        for playlist_path in root_path.glob(f"**/{playlist_name}"):
            relative_path = playlist_path.relative_to(root_path).as_posix()
            track_id = _track_id_from_hls_path(relative_path)
            parent_dir = playlist_path.parent

            # Poskusimo prebrati json z metapodatki
            json_meta = _read_hls_json_metadata(parent_dir) or {}

            fallback_title = (
                json_meta.get("title") or parent_dir.name or playlist_path.stem
            )
            artist = json_meta.get("artist", "")
            album = json_meta.get("album") or default_album
            duration = json_meta.get("duration", 0)

            genre = track_id.split("/")[0].strip() if include_genre else ""

            item = tracks.setdefault(
                track_id,
                {
                    "title": fallback_title,
                    "artist": artist,
                    "album": album,
                    "duration": duration,
                    "file_path": None,
                    "hls_path": relative_path,
                    "delete_path": relative_path,
                },
            )
            item["hls_path"] = relative_path

            # Če MP3 ne obstaja, napolnimo metapodatke iz JSON-a
            if json_meta.get("title"):
                item["title"] = json_meta["title"]
            if json_meta.get("artist"):
                item["artist"] = json_meta["artist"]
            if json_meta.get("album"):
                item["album"] = json_meta["album"]
            if json_meta.get("duration"):
                item["duration"] = json_meta["duration"]

            if include_genre:
                item["genre"] = genre
                item["only_admin"] = "Neurejena-glasba/" in track_id

    return tracks


def _build_music_albums_and_metadata(root_dir):
    tracks = _discover_media_library(
        root_dir,
        default_album="",
        include_genre=True,
    )
    music_albums = {}

    for track_id, item in tracks.items():
        parts = track_id.split("/")[:-1]
        music_albums.setdefault("Vse", []).append(track_id)
        for i in range(len(parts)):
            album_name = " - ".join(parts[: i + 1]).title()
            if "-" in album_name or "Drugo" not in album_name:
                music_albums.setdefault(album_name, []).append(track_id)

        if not item.get("album"):
            genre = item.get("genre", "")
            item["album"] = genre or "Glasba"

    sorted_metadata = {
        key: value
        for key, value in sorted(
            tracks.items(),
            key=lambda entry: (
                entry[1].get("genre", ""),
                entry[1].get("artist", ""),
                entry[1].get("album", ""),
                entry[1].get("title", ""),
            ),
        )
    }

    album_entries = [
        {
            "name": name,
            "songs": sorted(
                songs,
                key=lambda track_id: (
                    sorted_metadata[track_id].get("genre", "").lower(),
                    sorted_metadata[track_id].get("artist", "").lower(),
                    sorted_metadata[track_id].get("album", "").lower(),
                    sorted_metadata[track_id].get("title", "").lower(),
                ),
            ),
        }
        for name, songs in music_albums.items()
    ]
    album_entries.sort(
        key=lambda album: (album["name"] != "Vse", album["name"])
    )

    return album_entries, sorted_metadata


def _build_radio_stories_metadata(root_dir):
    tracks = _discover_media_library(
        root_dir,
        default_album="Radijska zgodba",
        include_genre=False,
    )
    return {
        key: value
        for key, value in sorted(
            tracks.items(),
            key=lambda entry: (
                entry[1].get("artist", ""),
                entry[1].get("title", ""),
            ),
        )
    }


# Initialize music
music_albums, music_metadata = _build_music_albums_and_metadata(
    str(MUSIC_ROOT)
)
MUSIC_COUNT = len(music_metadata)


# Initialize radio stories
radio_stories_metadata = _build_radio_stories_metadata(str(RADIO_STORIES_ROOT))
radio_stories_files = list(radio_stories_metadata.keys())
STORIES_COUNT = len(radio_stories_files)


@music_bp.route("/music")
@login_required
def music():
    if not is_current_admin_view(current_user):
        return render_template(
            "music_player.html",
            pagetitle="MarinKino - Glasba",
            is_music=True,
            albums=[a for a in music_albums if "Neurejen" not in a["name"]],
            music_metadata={
                k: v for k, v in music_metadata.items() if not v["only_admin"]
            },
        )
    return render_template(
        "music_player.html",
        pagetitle="MarinKino - Glasba",
        is_music=True,
        albums=music_albums,
        music_metadata=music_metadata,
    )


@music_bp.route("/radio-stories")
@login_required
def radio_stories():
    """Separate page for radio stories (Radijske-zgodbe)."""
    return render_template(
        "radio_stories.html",
        pagetitle="MarinKino - Radijske zgodbe",
        is_music=True,
        radio_stories_files=list(radio_stories_metadata.keys()),
        radio_stories_metadata=radio_stories_metadata,
    )


@music_bp.route("/music/file/<path:filename>")
@login_required
def song(filename):
    return _build_internal_media_response(
        str(MUSIC_ROOT), "protected_music", filename
    )


@music_bp.route("/music/hls/<path:filename>")
@login_required
def song_hls(filename):
    return _build_internal_media_response(
        str(MUSIC_ROOT), "protected_music", filename
    )


def _safe_remove_media(base_folder, filename):
    """Pomožna funkcija, ki varno odstrani datoteko ali celotno HLS mapo."""
    try:
        path = Path(safe_path(base_folder, filename))
        base_path = Path(base_folder).resolve()
    except ValueError:
        return False

    if not path.exists():
        return False

    if path.is_dir():
        shutil.rmtree(path)
    else:
        # Če se briše HLS playlista, odstranimo celotno mapo tega streama.
        if path.suffix.lower() == ".m3u8":
            hls_dir = path.parent
            if (
                hls_dir.exists()
                and hls_dir.is_dir()
                and hls_dir.resolve() != base_path
            ):
                shutil.rmtree(hls_dir)
                return True

        path.unlink()
        # Če ima skladba pripadajočo HLS mapo z enakim imenom,
        # pobrišemo tudi to
        hls_dir = path.parent / path.stem
        if hls_dir.exists() and hls_dir.is_dir():
            shutil.rmtree(hls_dir)

    return True


@music_bp.route("/music/delete/<path:filename>", methods=["DELETE"])
@login_required
def song_remove(filename):
    if not is_current_admin_view(current_user):
        return "", 204
    if not _safe_remove_media("data/music", filename):
        return "", 404
    return "", 204


@music_bp.route("/radio-stories/file/<path:filename>")
@login_required
def radio_story_file(filename):
    return _build_internal_media_response(
        str(RADIO_STORIES_ROOT), "protected_radio_stories", filename
    )


@music_bp.route("/radio-stories/hls/<path:filename>")
@login_required
def radio_story_hls(filename):
    return _build_internal_media_response(
        str(RADIO_STORIES_ROOT), "protected_radio_stories", filename
    )


@music_bp.route("/radio-stories/delete/<path:filename>", methods=["DELETE"])
@login_required
def radio_story_remove(filename):
    if not is_current_admin_view(current_user):
        return "", 204
    if not _safe_remove_media("data/radio-stories", filename):
        return "", 404
    return "", 204

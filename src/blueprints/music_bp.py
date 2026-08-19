import json
import logging
import os
import shutil
from pathlib import Path
from urllib.parse import quote
from uuid import uuid4

from flask import (
    Blueprint,
    abort,
    jsonify,
    make_response,
    render_template,
    request,
    send_from_directory,
)
from flask_login import current_user, login_required
from mutagen.easyid3 import EasyID3
from mutagen.mp3 import MP3, HeaderNotFoundError

from music.recommendations import (
    calculate_transition_parameters,
    load_cached_metadata,
    select_next_song,
)
from utils import FLASK_ENV, is_current_admin_view, safe_path

log = logging.getLogger(__name__)

music_bp = Blueprint("music", __name__)

REPO_ROOT = Path(__file__).resolve().parents[2]
MUSIC_ROOT = REPO_ROOT / "data" / "music"
RADIO_STORIES_ROOT = REPO_ROOT / "data" / "radio-stories"
PRIVATE_ALBUMS_ROOT = REPO_ROOT / "data" / "users-music-albums"
MAX_PRIVATE_ALBUMS = 10

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


def _read_hls_json_metadata(hls_dir_path: Path, relative_path: Path):
    """Prebere metadata.json datoteko znotraj HLS mape, če obstaja."""
    metadata = load_cached_metadata(
        hls_dir_path, enrich=True, relative_path=relative_path
    )
    return metadata if metadata else None


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
        for playlist_path in sorted(root_path.glob(f"**/{playlist_name}")):
            relative_path = playlist_path.relative_to(root_path).as_posix()
            track_id = _track_id_from_hls_path(relative_path)
            parent_dir = playlist_path.parent

            # Poskusimo prebrati json z metapodatki
            json_meta = (
                _read_hls_json_metadata(
                    parent_dir, playlist_path.relative_to(root_path).parent
                )
                or {}
            )

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
            for key in (
                "audio_features",
                "start_chord",
                "end_chord",
                "folder_path",
                "silence_start_ms",
                "silence_end_ms",
            ):
                if key in json_meta:
                    item[key] = json_meta[key]

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


def _normalize_music_view():
    admin_view = is_current_admin_view(current_user)
    visible_metadata = (
        music_metadata
        if admin_view
        else {
            key: value
            for key, value in music_metadata.items()
            if not value.get("only_admin")
        }
    )
    visible_track_ids = set(visible_metadata.keys())
    visible_albums = []

    for album in music_albums:
        if not admin_view and "Neurejen" in album["name"]:
            continue

        songs = [
            track_id
            for track_id in album["songs"]
            if track_id in visible_track_ids
        ]
        if songs or album["name"] == "Vse":
            visible_albums.append({"name": album["name"], "songs": songs})

    return visible_albums, visible_metadata, visible_track_ids


def _normalize_private_album_name(value):
    return " ".join(str(value or "").split()).strip()


def _private_albums_file(user_id):
    safe_user_id = str(user_id).replace("/", "_").replace(os.sep, "_")
    return PRIVATE_ALBUMS_ROOT / f"{safe_user_id}.json"


def _load_private_album_store(user_id):
    path = _private_albums_file(user_id)
    if not path.exists():
        return {"albums": []}

    try:
        with open(path, "r", encoding="utf-8") as handle:
            data = json.load(handle)
    except Exception as exc:
        log.error("❌ Napaka pri branju privat albumov %s: %s", path, exc)
        return {"albums": []}

    if not isinstance(data, dict):
        return {"albums": []}

    albums = data.get("albums")
    if not isinstance(albums, list):
        albums = []
    return {"albums": albums}


def _save_private_album_store(user_id, store):
    PRIVATE_ALBUMS_ROOT.mkdir(parents=True, exist_ok=True)
    path = _private_albums_file(user_id)
    with open(path, "w", encoding="utf-8") as handle:
        json.dump(store, handle, ensure_ascii=False, indent=2)


def _filter_private_album_song_ids(song_ids, visible_track_ids):
    filtered_song_ids = []
    seen_track_ids = set()

    for track_id in song_ids or []:
        if not isinstance(track_id, str):
            continue
        if track_id not in visible_track_ids or track_id in seen_track_ids:
            continue
        filtered_song_ids.append(track_id)
        seen_track_ids.add(track_id)

    return filtered_song_ids


def _serialize_private_albums(store, visible_track_ids):
    serialized_albums = []
    normalized_store = {"albums": []}
    changed = False

    for album in store.get("albums", []):
        if not isinstance(album, dict):
            changed = True
            continue

        album_id = str(album.get("id") or uuid4().hex[:12])
        name = (
            _normalize_private_album_name(album.get("name")) or "Privat album"
        )
        songs = _filter_private_album_song_ids(
            album.get("songs", []), visible_track_ids
        )

        normalized_album = {"id": album_id, "name": name, "songs": songs}
        if normalized_album != album:
            changed = True

        normalized_store["albums"].append(normalized_album)
        serialized_albums.append({**normalized_album, "is_private": True})

    return serialized_albums, normalized_store, changed


def _find_private_album(store, album_id):
    for album in store.get("albums", []):
        if str(album.get("id")) == album_id:
            return album
    return None


def _private_albums_payload(store, visible_track_ids, album_id=None):
    albums, normalized_store, changed = _serialize_private_albums(
        store, visible_track_ids
    )
    payload = {"albums": albums, "max_albums": MAX_PRIVATE_ALBUMS}
    if album_id:
        payload["album"] = next(
            (album for album in albums if album["id"] == album_id), None
        )
    return payload, normalized_store, changed


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
    (
        visible_albums,
        visible_metadata,
        visible_track_ids,
    ) = _normalize_music_view()
    private_album_store = _load_private_album_store(current_user.id)
    private_albums, normalized_store, changed = _serialize_private_albums(
        private_album_store, visible_track_ids
    )

    if changed:
        _save_private_album_store(current_user.id, normalized_store)

    return render_template(
        "music_player.html",
        pagetitle="MarinKino - Glasba",
        is_music=True,
        albums=private_albums + visible_albums,
        private_albums=private_albums,
        max_private_albums=MAX_PRIVATE_ALBUMS,
        music_metadata=visible_metadata,
    )


@music_bp.route("/music/recommendation/next", methods=["POST"])
@login_required
def recommend_next_song():
    _, visible_metadata, visible_track_ids = _normalize_music_view()
    payload = request.get_json(silent=True) or {}
    current_id = str(payload.get("current_song_id") or "")
    if current_id not in visible_track_ids:
        return jsonify({"message": "Trenutna pesem ni veljavna."}), 400

    mode = str(payload.get("mode") or "similar")
    allowed_modes = {
        "sequential",
        "similar",
        "random",
        "uniform_random",
        "repeat",
    }
    if mode not in allowed_modes:
        return jsonify({"message": "Neveljaven način predvajanja."}), 400

    requested_ids = payload.get("playlist")
    if requested_ids is None:
        playlist_ids = list(visible_track_ids)
    elif isinstance(requested_ids, list):
        playlist_ids = [
            str(track_id)
            for track_id in requested_ids
            if str(track_id) in visible_track_ids
        ]
    else:
        return jsonify({"message": "Playlist mora biti seznam."}), 400

    if current_id not in playlist_ids:
        playlist_ids.insert(0, current_id)
    playlist = [
        {"id": track_id, **visible_metadata[track_id]}
        for track_id in dict.fromkeys(playlist_ids)
    ]
    current_song = next(song for song in playlist if song["id"] == current_id)
    try:
        randomness_weight = float(payload.get("randomness_weight", 0.1))
        crossfade_duration_ms = int(payload.get("crossfade_duration_ms", 3000))
    except (TypeError, ValueError):
        return jsonify({"message": "Časovni parametri niso veljavni."}), 400

    selected = select_next_song(
        current_song,
        playlist,
        randomness_weight=randomness_weight,
        mode=mode,
    )
    if selected is None:
        return jsonify({"message": "Ni mogoče izbrati naslednje pesmi."}), 400

    next_id = str(selected["id"])
    transition = calculate_transition_parameters(
        current_song,
        selected,
        crossfade_duration_ms,
    )
    response_song = dict(visible_metadata[next_id])
    response_song["id"] = next_id
    if response_song.get("hls_path"):
        response_song["hls_url"] = "/music/hls/" + quote(
            str(response_song["hls_path"]), safe="/"
        )
    return jsonify({"song": response_song, "transition": transition})


@music_bp.route("/music/private-albums", methods=["POST"])
@login_required
def create_private_album():
    _, _, visible_track_ids = _normalize_music_view()
    store = _load_private_album_store(current_user.id)
    _, store, changed = _private_albums_payload(store, visible_track_ids)
    if changed:
        _save_private_album_store(current_user.id, store)

    if len(store["albums"]) >= MAX_PRIVATE_ALBUMS:
        return jsonify({"message": "Dosežena meja 10 privat albumov."}), 400

    payload = request.get_json(silent=True) or {}
    album_name = _normalize_private_album_name(payload.get("name"))
    if not album_name:
        return jsonify({"message": "Ime albuma je obvezno."}), 400

    if any(
        album["name"].lower() == album_name.lower()
        for album in store["albums"]
    ):
        return jsonify({"message": "Album s tem imenom že obstaja."}), 400

    album = {"id": uuid4().hex[:12], "name": album_name, "songs": []}
    store["albums"].append(album)
    _save_private_album_store(current_user.id, store)

    response_payload, _, _ = _private_albums_payload(
        store, visible_track_ids, album["id"]
    )
    response_payload["message"] = "Privat album ustvarjen."
    return jsonify(response_payload), 201


@music_bp.route(
    "/music/private-albums/<album_id>", methods=["PATCH", "DELETE"]
)
@login_required
def mutate_private_album(album_id):
    _, _, visible_track_ids = _normalize_music_view()
    store = _load_private_album_store(current_user.id)
    _, store, changed = _private_albums_payload(store, visible_track_ids)
    if changed:
        _save_private_album_store(current_user.id, store)

    album = _find_private_album(store, album_id)
    if album is None:
        return jsonify({"message": "Privat album ne obstaja."}), 404

    if request.method == "DELETE":
        store["albums"] = [
            existing
            for existing in store["albums"]
            if existing["id"] != album_id
        ]
        _save_private_album_store(current_user.id, store)
        response_payload, _, _ = _private_albums_payload(
            store, visible_track_ids
        )
        response_payload["message"] = "Privat album odstranjen."
        return jsonify(response_payload)

    payload = request.get_json(silent=True) or {}
    album_name = _normalize_private_album_name(payload.get("name"))
    if not album_name:
        return jsonify({"message": "Ime albuma je obvezno."}), 400

    if any(
        existing["id"] != album_id
        and existing["name"].lower() == album_name.lower()
        for existing in store["albums"]
    ):
        return jsonify({"message": "Album s tem imenom že obstaja."}), 400

    album["name"] = album_name
    _save_private_album_store(current_user.id, store)

    response_payload, _, _ = _private_albums_payload(
        store, visible_track_ids, album_id
    )
    response_payload["message"] = "Ime privat albuma posodobljeno."
    return jsonify(response_payload)


@music_bp.route(
    "/music/private-albums/<album_id>/songs",
    methods=["POST", "DELETE"],
)
@login_required
def mutate_private_album_songs(album_id):
    _, _, visible_track_ids = _normalize_music_view()
    store = _load_private_album_store(current_user.id)
    _, store, changed = _private_albums_payload(store, visible_track_ids)
    if changed:
        _save_private_album_store(current_user.id, store)

    album = _find_private_album(store, album_id)
    if album is None:
        return jsonify({"message": "Privat album ne obstaja."}), 404

    payload = request.get_json(silent=True) or {}
    song_ids = _filter_private_album_song_ids(
        payload.get("song_ids", []), visible_track_ids
    )
    if not song_ids:
        return jsonify({"message": "Ni veljavnih pesmi za obdelavo."}), 400

    if request.method == "POST":
        existing_song_ids = set(album.get("songs", []))
        for song_id in song_ids:
            if song_id not in existing_song_ids:
                album.setdefault("songs", []).append(song_id)
                existing_song_ids.add(song_id)
        message = "Pesmi dodane v privat album."
    else:
        song_ids_set = set(song_ids)
        album["songs"] = [
            song_id
            for song_id in album.get("songs", [])
            if song_id not in song_ids_set
        ]
        message = "Pesmi odstranjene iz privat albuma."

    _save_private_album_store(current_user.id, store)
    response_payload, _, _ = _private_albums_payload(
        store, visible_track_ids, album_id
    )
    response_payload["message"] = message
    return jsonify(response_payload)


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
    # Some cached clients may retain a legacy HLS directory URL.
    try:
        hls_path = Path(safe_path(MUSIC_ROOT, filename))
    except ValueError:
        abort(404)
    if hls_path.is_dir():
        for playlist_name in HLS_PLAYLIST_NAMES:
            if (hls_path / playlist_name).is_file():
                filename = f"{filename.rstrip('/')}/{playlist_name}"
                break
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

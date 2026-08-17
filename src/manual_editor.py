import glob
import json
import os
import re
import secrets
import shutil
import unicodedata
from pathlib import Path
from urllib.parse import unquote

import yt_dlp
from ffmpeg_normalize import FFmpegNormalize
from flask import Flask, jsonify, render_template, request, send_from_directory
from flask_compress import Compress
from mutagen.easyid3 import EasyID3
from mutagen.mp3 import MP3, HeaderNotFoundError

from content_preparation.audio_preparation import convert_mp3_to_hls
from utils import safe_path

app = Flask(__name__, static_url_path="/static", static_folder="static")
app.secret_key = os.getenv("FLASK_KEY")
Compress(app)

MUSIC_FOLDER = "data/music"
INCOMING_MUSIC_FOLDER = f"{MUSIC_FOLDER}/Neurejena-glasba"
INCOMING_VIDEO_FOLDER = "data/memes/Neurejeni-videi"
REPO_ROOT = Path(__file__).resolve().parents[1]
MUSIC_FOLDER_ABS = REPO_ROOT / "data" / "music"
INCOMING_VIDEO_FOLDER_ABS = REPO_ROOT / "data" / "memes" / "Neurejeni-videi"


def _format_duration(total_seconds):
    total_seconds = int(total_seconds or 0)
    return f"{total_seconds // 60}:{total_seconds % 60:02d}"


def _normalize_track_id(track_ref):
    track_id = str(track_ref or "").replace("\\", "/").strip("/")
    if track_id.endswith("/index.m3u8"):
        return track_id[: -len("/index.m3u8")]
    if track_id.endswith(".mp3"):
        return track_id[:-4]
    return track_id


def _resolve_track_paths(track_ref):
    track_id = _normalize_track_id(track_ref)
    base_path = Path(safe_path(MUSIC_FOLDER, track_id))
    return {
        "track_id": track_id,
        "hls_dir": base_path,
        "hls_playlist": base_path / "index.m3u8",
        "hls_metadata": base_path / "metadata.json",
        "mp3_path": Path(safe_path(MUSIC_FOLDER, f"{track_id}.mp3")),
    }


def normalize_mp3_file(input_path):
    normalizer = FFmpegNormalize(
        target_level=-16,
        true_peak=-1.0,
        loudness_range_target=20.0,
        sample_rate=44100,
        audio_codec="libmp3lame",
        extra_output_options=[
            "-map_metadata",
            "0",
            "-id3v2_version",
            "3",
            "-b:a",
            "320k",
        ],
        print_stats=False,
    )
    output_path = f"{input_path}.normalized.mp3"
    normalizer.add_media_file(input_path, output_path)
    normalizer.run_normalization()
    os.replace(output_path, input_path)


def _slugify_part(value, fallback="track"):
    text = str(value or "").strip()
    if not text:
        text = fallback

    normalized = unicodedata.normalize("NFKD", text)
    ascii_text = normalized.encode("ascii", "ignore").decode("ascii")
    cleaned = re.sub(r"[^a-zA-Z0-9]+", "-", ascii_text).strip("-")
    return cleaned.lower() or fallback


def _is_unique_hls_dir_name(folder_name):
    pattern = r"^[a-z0-9-]+_[a-z0-9-]+[-_][0-9a-f]{6}$"
    return bool(re.match(pattern, folder_name))


def _read_hls_dir_metadata(hls_dir: Path):
    metadata_path = hls_dir / "metadata.json"
    if not metadata_path.exists():
        return {}
    try:
        with open(metadata_path, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {}


def _build_unique_hls_output_dir(mp3_file: Path):
    title = mp3_file.stem
    artist = ""

    try:
        audio = MP3(str(mp3_file), ID3=EasyID3)
        title = (audio.get("title") or [title])[0]
        artist = (audio.get("artist") or [""])[0]
    except (HeaderNotFoundError, Exception):
        pass

    base_name = "_".join(
        [
            _slugify_part(artist, fallback="artist"),
            _slugify_part(title, fallback="track"),
        ]
    )

    # Reuse existing conversion for the same source metadata. A new random
    # directory here creates duplicate HLS copies on every editor run.
    existing_hls = mp3_file.parent.glob(f"{base_name}*/*index.m3u8")
    for index_file in sorted(existing_hls):
        metadata = _read_hls_dir_metadata(index_file.parent)
        if (
            metadata.get("title") == title
            and metadata.get("artist", "") == artist
        ):
            return index_file.parent

    while True:
        token = secrets.token_hex(3)
        candidate = mp3_file.parent / f"{base_name}-{token}"
        if not candidate.exists():
            return candidate


def _build_unique_hls_dir_from_values(parent_dir: Path, title, artist):
    base_name = "_".join(
        [
            _slugify_part(artist, fallback="artist"),
            _slugify_part(title, fallback="track"),
        ]
    )

    while True:
        token = secrets.token_hex(3)
        candidate = parent_dir / f"{base_name}_{token}"
        if not candidate.exists():
            return candidate


def rename_existing_incoming_hls_dirs():
    """Ob zagonu enkratno preimenuje stare HLS mape v novo unikatno shemo."""
    root = Path(INCOMING_MUSIC_FOLDER)
    if not root.exists():
        return

    for index_file in sorted(root.rglob("index.m3u8")):
        hls_dir = index_file.parent
        if _is_unique_hls_dir_name(hls_dir.name):
            continue

        metadata = _read_hls_dir_metadata(hls_dir)
        title = metadata.get("title") or hls_dir.name
        artist = metadata.get("artist") or ""
        target_dir = _build_unique_hls_dir_from_values(
            hls_dir.parent,
            title,
            artist,
        )

        try:
            hls_dir.rename(target_dir)
            print(f"Preimenovana HLS mapa: {hls_dir} -> {target_dir}")
        except Exception as e:
            print(f"NAPAKA pri preimenovanju HLS mape {hls_dir}: {e}")


def process_incoming_music_folder(folder_path=None):
    """Normalizira MP3 in jih pretvori v HLS (index.m3u8 + metadata.json)."""
    root = Path(folder_path or INCOMING_MUSIC_FOLDER)
    if not root.exists():
        return

    for mp3_file in sorted(root.rglob("*.mp3")):
        try:
            print(f"Normaliziram: {mp3_file}")
            normalize_mp3_file(str(mp3_file))
        except Exception as e:
            print(f"NAPAKA pri normalizaciji {mp3_file}: {e}")
            continue

        try:
            output_directory = _build_unique_hls_output_dir(mp3_file)
            convert_mp3_to_hls(str(mp3_file), str(output_directory))
        except Exception as e:
            print(f"NAPAKA pri HLS pretvorbi {mp3_file}: {e}")


def download_playlist(playlist_url, get_video=False):
    if get_video:
        incoming_folder = INCOMING_VIDEO_FOLDER
    else:
        incoming_folder = INCOMING_MUSIC_FOLDER
    if not os.path.exists(incoming_folder):
        os.makedirs(incoming_folder)
    ydl_opts = {
        "ignoreerrors": True,  # Če ena pesem ne dela, nadaljuj z naslednjo
        "outtmpl": f"{incoming_folder}/%(playlist_title)s/%(title)s.%(ext)s",
        "postprocessors": [
            {
                "key": "FFmpegMetadata",
                "add_metadata": True,
            },
            {
                "key": "EmbedThumbnail",
            },
        ],
        "writethumbnail": True,
        # To prepreči, da bi yt-dlp prekinil delovanje ob opozorilih
        "quiet": False,
        "no_warnings": True,
    }
    # Konfiguracija za yt-dlp
    if get_video:
        ydl_opts["format"] = "bestvideo+bestaudio/best"
        ydl_opts["merge_output_format"] = "mp4"
    else:
        ydl_opts["format"] = "bestaudio/best"
        ydl_opts["postprocessors"] = [
            {
                "key": "FFmpegExtractAudio",
                "preferredcodec": "mp3",
                "preferredquality": "192",
            }
        ] + ydl_opts["postprocessors"]

    print(f"Začenjam analizo playliste: {playlist_url}")
    print("To lahko traja nekaj trenutkov ...")

    with yt_dlp.YoutubeDL(ydl_opts) as ydl:  # type: ignore[arg-type]
        try:
            # extract_info s download=True dejansko sproži prenos
            info = ydl.extract_info(playlist_url, download=True)

            # Pridobimo ime playliste za izpis na koncu
            playlist_title = info.get("title", "Neznana playlista")
            print(
                "\n✅ Končano! Glasba je shranjena v mapi:"
                f" {incoming_folder}/{playlist_title}"
            )

        except Exception as e:
            print(f"\n❌ Prišlo je do napake: {e}")
            return False

    if get_video:
        return True

    process_incoming_music_folder(f"{INCOMING_MUSIC_FOLDER}/{playlist_title}")
    print("\nKončano! Glasnost je urejena in HLS pripravljen.")
    return True


for url in []:
    download_playlist(url)

rename_existing_incoming_hls_dirs()


def get_current_metadata(track_ref):
    paths = _resolve_track_paths(track_ref)
    track_id = paths["track_id"]
    default_title = track_id.split("/")[-1] if track_id else ""

    metadata = {
        "title": default_title,
        "artist": "",
        "album": "",
        "filename": track_id,
        "folder": "/".join(track_id.split("/")[:-1]),
        "duration": "0:00",
        "play_path": f"{track_id}/index.m3u8",
        "delete_path": track_id,
    }

    if paths["hls_metadata"].exists():
        try:
            with open(paths["hls_metadata"], "r", encoding="utf-8") as f:
                hls_data = json.load(f)
            metadata["title"] = hls_data.get("title") or metadata["title"]
            metadata["artist"] = hls_data.get("artist") or ""
            metadata["album"] = hls_data.get("album") or ""
            metadata["duration"] = _format_duration(hls_data.get("duration"))
            return metadata
        except Exception:
            pass

    if paths["mp3_path"].exists():
        try:
            audio = MP3(str(paths["mp3_path"]), ID3=EasyID3)
            metadata["title"] = ", ".join(
                audio.get("title") or [default_title]
            )
            metadata["artist"] = ", ".join(audio.get("artist") or [])
            metadata["album"] = ", ".join(audio.get("album") or [])
            metadata["duration"] = _format_duration(
                int(getattr(getattr(audio, "info", None), "length", 0))
            )
            metadata["play_path"] = f"{track_id}.mp3"
            return metadata
        except (HeaderNotFoundError, Exception):
            pass

    return metadata


def list_incoming_music_tracks():
    incoming_root = Path(INCOMING_MUSIC_FOLDER)
    music_root = Path(MUSIC_FOLDER)
    tracks = {}

    if incoming_root.exists():
        for playlist in sorted(incoming_root.rglob("index.m3u8")):
            track_id = playlist.parent.relative_to(music_root).as_posix()
            tracks[track_id] = get_current_metadata(track_id)

        for mp3_file in sorted(incoming_root.rglob("*.mp3")):
            track_id = (
                mp3_file.relative_to(music_root).with_suffix("").as_posix()
            )
            tracks.setdefault(track_id, get_current_metadata(track_id))

    return sorted(
        tracks.values(),
        key=lambda x: (
            x.get("folder", "").lower(),
            x.get("artist", "").lower(),
            x.get("album", "").lower(),
            x.get("title", "").lower(),
        ),
    )


def update_values(music_file, title, artist, album):
    paths = _resolve_track_paths(music_file)
    track_exists = paths["mp3_path"].exists() or paths["hls_dir"].exists()
    if not track_exists:
        raise FileNotFoundError("Datoteka ne obstaja")

    if paths["mp3_path"].exists():
        audio = MP3(str(paths["mp3_path"]), ID3=EasyID3)
        audio["title"] = title.strip()
        audio["artist"] = artist.strip()
        audio["album"] = album.strip()
        audio.save()

    metadata_payload = {
        "title": title.strip(),
        "artist": artist.strip(),
        "album": album.strip(),
        "duration": 0,
    }
    current = get_current_metadata(paths["track_id"])
    try:
        mm, ss = (current.get("duration") or "0:00").split(":", 1)
        metadata_payload["duration"] = int(mm) * 60 + int(ss)
    except Exception:
        metadata_payload["duration"] = 0

    paths["hls_dir"].mkdir(parents=True, exist_ok=True)
    with open(paths["hls_metadata"], "w", encoding="utf-8") as f:
        json.dump(metadata_payload, f, ensure_ascii=False, indent=2)

    return {"status": "ok", "message": "Podatki uspešno shranjeni!"}


@app.route("/")
def index():
    process_incoming_music_folder(INCOMING_MUSIC_FOLDER)
    return render_template(
        "music_editor.html",
        music=list_incoming_music_tracks(),
    )


@app.route("/music/file/<path:filename>")
def song(filename):
    decoded_filename = unquote(filename)
    full_path = safe_path(str(MUSIC_FOLDER_ABS), decoded_filename)
    relative_path = os.path.relpath(full_path, str(MUSIC_FOLDER_ABS))
    return send_from_directory(
        str(MUSIC_FOLDER_ABS),
        relative_path,
        conditional=True,
    )


@app.route("/api/videos/list")
def list_incoming_videos():
    files = [
        os.path.relpath(f, INCOMING_VIDEO_FOLDER)
        for f in glob.iglob(f"{INCOMING_VIDEO_FOLDER}/**/*.*", recursive=True)
        if f.lower().endswith((".mp4", ".webm", ".mov", ".mkv"))
    ]
    files = sorted(files)
    return jsonify({"status": "ok", "files": files})


@app.route("/video/file/<path:filename>")
def incoming_video_file(filename):
    decoded_filename = unquote(filename)
    full_path = safe_path(str(INCOMING_VIDEO_FOLDER_ABS), decoded_filename)
    relative_path = os.path.relpath(
        full_path,
        str(INCOMING_VIDEO_FOLDER_ABS),
    )

    mimetype = None
    lower_name = decoded_filename.lower()
    if lower_name.endswith(".mp4"):
        mimetype = "video/mp4"
    elif lower_name.endswith(".webm"):
        mimetype = "video/webm"
    elif lower_name.endswith(".mov"):
        mimetype = "video/quicktime"
    elif lower_name.endswith(".mkv"):
        mimetype = "video/x-matroska"

    response = send_from_directory(
        str(INCOMING_VIDEO_FOLDER_ABS),
        relative_path,
        mimetype=mimetype,
        conditional=True,
    )
    response.headers["Accept-Ranges"] = "bytes"
    return response


@app.route("/videos/editor")
def videos_editor():
    return render_template("video_editor.html")


@app.route("/api/videos/delete", methods=["DELETE"])
def delete_incoming_video():
    try:
        data = request.json
        filename = data.get("filename")

        if not filename:
            return (
                jsonify(
                    {"status": "error", "message": "Filename is required"}
                ),
                400,
            )

        try:
            path = safe_path(INCOMING_VIDEO_FOLDER, filename)
        except ValueError:
            return (
                jsonify({"status": "error", "message": "Invalid filename"}),
                400,
            )

        if not os.path.exists(path):
            return (
                jsonify({"status": "error", "message": "File does not exist"}),
                404,
            )

        os.remove(path)
        return jsonify({"status": "ok", "message": "File removed"})
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 500


@app.route("/api/videos/accept", methods=["POST"])
def accept_incoming_video():
    try:
        data = request.json
        filename = data.get("filename")

        if not filename:
            return (
                jsonify(
                    {"status": "error", "message": "Filename is required"}
                ),
                400,
            )

        try:
            src_path = safe_path(INCOMING_VIDEO_FOLDER, filename)
        except ValueError:
            return (
                jsonify({"status": "error", "message": "Invalid filename"}),
                400,
            )

        if not os.path.exists(src_path):
            return (
                jsonify({"status": "error", "message": "File does not exist"}),
                404,
            )

        # Target folder for accepted memes
        target_folder = "data/memes"
        os.makedirs(target_folder, exist_ok=True)

        base_name = os.path.basename(filename)
        dest_path = os.path.join(target_folder, base_name)

        # Avoid overwriting existing files
        name, ext = os.path.splitext(base_name)
        counter = 1
        while os.path.exists(dest_path):
            dest_path = os.path.join(target_folder, f"{name}-{counter}{ext}")
            counter += 1

        shutil.move(src_path, dest_path)

        return jsonify(
            {
                "status": "ok",
                "message": "File accepted",
                "new_filename": os.path.relpath(dest_path, target_folder),
            }
        )
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 500


@app.route("/api/music/update", methods=["POST"])
def update_music_metadata():
    try:
        data = request.json
        music_file = data.get("filename")

        if not music_file:
            return (
                jsonify(
                    {"status": "error", "message": "Filename je obavezen"}
                ),
                400,
            )

        try:
            # Posodabljamo metapodatke
            update_values(
                music_file=music_file,
                title=data.get("title", ""),
                artist=data.get("artist", ""),
                album=data.get("album", ""),
            )
        except FileNotFoundError as e:
            return jsonify({"status": "error", "message": str(e)}), 404

        print(f"Updated: {music_file}")

        return jsonify(
            {
                "status": "ok",
                "message": "Metapodatki uspešno posodobljeni",
                "metadata": get_current_metadata(music_file),
            }
        )
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 500


@app.route("/api/music/delete", methods=["DELETE"])
def delete_music_file():
    try:
        data = request.json
        music_file = data.get("filename")

        if not music_file:
            return (
                jsonify(
                    {"status": "error", "message": "Filename je obavezen"}
                ),
                400,
            )

        try:
            paths = _resolve_track_paths(music_file)
        except ValueError:
            return (
                jsonify({"status": "error", "message": "Neveljavna datoteka"}),
                400,
            )

        removed_any = False
        if paths["hls_dir"].exists() and paths["hls_dir"].is_dir():
            shutil.rmtree(paths["hls_dir"])
            removed_any = True
        if paths["mp3_path"].exists() and paths["mp3_path"].is_file():
            os.remove(paths["mp3_path"])
            removed_any = True

        if not removed_any:
            return (
                jsonify({"status": "error", "message": "Datoteka ne obstaja"}),
                404,
            )

        print(f"Removed: {paths['track_id']}")

        return jsonify(
            {
                "status": "ok",
                "message": "Datoteka je bila uspešno izbrisana",
            }
        )
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 500


@app.route("/api/music/download-yt", methods=["POST"])
def download_yt_music():
    try:
        data = request.json
        yt_url = data.get("url")

        if not yt_url:
            return (
                jsonify({"status": "error", "message": "URL je obavezen"}),
                400,
            )

        # Preuzeми pesmi
        success = download_playlist(yt_url)

        if not success:
            return (
                jsonify(
                    {
                        "status": "error",
                        "message": (
                            "Napaka pri prenašanju. Preveri, ali "
                            "je YT-DL pravilno nameščen."
                        ),
                    }
                ),
                500,
            )

        print("Uspešno preneseno")

        return jsonify(
            {
                "status": "ok",
                "message": "Uspešno preneseno",
            }
        )
    except Exception as e:
        print(f"Napaka pri YouTube prenašanju: {e}")
        return jsonify({"status": "error", "message": str(e)}), 500


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=8080)

import glob
import logging
import os

from flask import Blueprint, render_template, send_from_directory
from flask_login import current_user, login_required
from mutagen.easyid3 import EasyID3
from mutagen.mp3 import MP3, HeaderNotFoundError

from utils import safe_path

log = logging.getLogger(__name__)

music_bp = Blueprint("music", __name__)

# Initialize music
music_albums = {}
music_files = [
    f[11:] for f in glob.iglob("data/music/**/*.mp3", recursive=True)
]
for s in music_files:
    parts = s.split("/")[:-1]
    music_albums.setdefault("Vse", []).append(s)
    for i in range(len(parts)):
        album = " - ".join(parts[: i + 1]).title()
        music_albums.setdefault(album, []).append(s)

music_metadata = {}
for file in music_albums["Vse"]:
    try:
        audio = MP3(os.path.join("data/music", file), ID3=EasyID3)
    except HeaderNotFoundError as e:
        audio = {}
    except Exception as e:
        log.error(f"❌ Napaka pri {file}: {e}")
        audio = {}

    item = {
        "title": ", ".join(
            audio.get("title", [".".join(file.split("/")[-1].split(".")[:-1])])
        ),
        "artist": " - ".join(audio.get("artist", [])),
        "album": " - ".join(audio.get("album", audio.get("genre", []))),
        "only_admin": "Neurejena-glasba/" in file,
    }
    music_metadata[file] = item
music_metadata = {
    k: v
    for k, v in sorted(
        music_metadata.items(),
        key=lambda item: (
            item[1]["album"],
            item[1]["artist"],
            item[1]["title"],
        ),
    )
}
music_albums = [
    {
        "name": k,
        "songs": sorted(
            music_albums[k],
            key=lambda x: (
                music_metadata[x]["album"].lower(),
                music_metadata[x]["artist"].lower(),
                music_metadata[x]["title"].lower(),
            ),
        ),
    }
    for k in (["Vse"] + sorted([m for m in music_albums.keys() if m != "Vse"]))
]


@music_bp.route("/music")
@login_required
def music():
    if not current_user.is_admin:
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


@music_bp.route("/music/file/<path:filename>")
@login_required
def song(filename):
    try:
        path = safe_path("../data/music", filename)
    except ValueError:
        return "", 404
    response = send_from_directory("../data/music", filename, conditional=True)
    response.headers["Accept-Ranges"] = "bytes"
    if filename.endswith(".mp3"):
        response.headers["Content-Type"] = "audio/mpeg"
    elif filename.endswith(".m4a"):
        response.headers["Content-Type"] = "audio/mp4"
    elif filename.endswith(".wav"):
        response.headers["Content-Type"] = "audio/wav"
    return response


@music_bp.route("/music/delete/<path:filename>", methods=["DELETE"])
@login_required
def song_remove(filename):
    if not current_user.is_admin:
        return "", 204
    try:
        path = safe_path("../data/music", filename)
    except ValueError:
        return "", 404
    if not os.path.exists(path):
        return "", 404
    os.remove(path)
    return "", 204

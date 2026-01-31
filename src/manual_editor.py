import glob
import os

import yt_dlp
from flask import Flask, jsonify, render_template, request, send_from_directory
from flask_compress import Compress
from mutagen.easyid3 import EasyID3
from mutagen.mp3 import MP3

app = Flask(__name__, static_url_path="/static", static_folder="static")
app.secret_key = os.getenv("FLASK_KEY")
Compress(app)

MUSIC_FOLDER = "data/music"
INCOMING_MUSIC_FOLDER = f"{MUSIC_FOLDER}/Neurejena-glasba"


def download_playlist(playlist_url):
    # Konfiguracija za yt-dlp
    ydl_opts = {
        "format": "bestaudio/best",
        "ignoreerrors": True,  # Če ena pesem ne dela, nadaljuj z naslednjo
        # Struktura map: Glasba_iz_YouTube / Ime Playliste / Izvajalec - Naslov.mp3
        "outtmpl": f"{INCOMING_MUSIC_FOLDER}/%(playlist_title)s/%(title)s.%(ext)s",
        "postprocessors": [
            {
                "key": "FFmpegExtractAudio",
                "preferredcodec": "mp3",
                "preferredquality": "192",
            },
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

    print(f"Začenjam analizo playliste: {playlist_url}")
    print("To lahko traja nekaj trenutkov ...")

    with yt_dlp.YoutubeDL(ydl_opts) as ydl:
        try:
            # extract_info s download=True dejansko sproži prenos
            info = ydl.extract_info(playlist_url, download=True)

            # Pridobimo ime playliste za izpis na koncu
            playlist_title = info.get("title", "Neznana playlista")
            print(
                f"\n✅ Končano! Glasba je shranjena v mapi: {INCOMING_MUSIC_FOLDER}/{playlist_title}"
            )
            return True

        except Exception as e:
            print(f"\n❌ Prišlo je do napake: {e}")
            return False


for url in []:
    download_playlist(url)


def get_current_metadata(music_file):
    path = os.path.join("data/music", music_file)
    audio = MP3(path, ID3=EasyID3)
    total_seconds = int(audio.info.length)
    return {
        "title": ", ".join(
            audio.get("title", [".".join(music_file.split("/")[-1].split(".")[:-1])])
        ),
        "artist": ", ".join(audio.get("artist", [])),
        "album": ", ".join(audio.get("album", [])),
        "genre": ", ".join(audio.get("genre", [])),
        "filename": music_file,
        "folder": "/".join(music_file.split("/")[:-1]),
        "duration": f"{total_seconds // 60}:{total_seconds % 60:02d}",
    }


def update_values(music_file, title, artist, album, genre):
    path = os.path.join("data/music", music_file)
    audio = MP3(path, ID3=EasyID3)
    audio["title"] = title.strip()
    audio["artist"] = artist.strip()
    audio["album"] = album.strip()
    audio["genre"] = genre.strip()
    audio.save()
    return {"status": "ok", "message": "Podatki uspešno shranjeni!"}


@app.route("/")
def index():
    music_files = [
        f[11:] for f in glob.iglob(f"{INCOMING_MUSIC_FOLDER}/**/*.mp3", recursive=True)
    ]
    return render_template(
        "music_editor.html",
        music=sorted(
            [get_current_metadata(file) for file in music_files],
            key=lambda x: (
                x.get("folder", "").lower(),
                x.get("artist", "").lower(),
                x.get("album", "").lower(),
                x.get("title", "").lower(),
            ),
        ),
    )


@app.route("/music/file/<path:filename>")
def song(filename):
    return send_from_directory("../data/music", filename, conditional=True)


@app.route("/api/music/update", methods=["POST"])
def update_music_metadata():
    try:
        data = request.json
        music_file = data.get("filename")

        if not music_file:
            return (
                jsonify({"status": "error", "message": "Filename je obavezen"}),
                400,
            )

        # Posodabljamo metapodatke
        update_values(
            music_file=music_file,
            title=data.get("title", ""),
            artist=data.get("artist", ""),
            album=data.get("album", ""),
            genre=data.get("genre", ""),
        )
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
                jsonify({"status": "error", "message": "Filename je obavezen"}),
                400,
            )

        # Preveri varnost - preverimo, da datoteka res obstaja v data/music
        file_path = os.path.join("data/music", music_file)
        if not os.path.exists(file_path):
            return (
                jsonify({"status": "error", "message": "Datoteka ne obstaja"}),
                404,
            )

        os.remove(file_path)
        print(f"Removed: {music_file}")

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
                        "message": "Napaka pri prenašanju. Preveri, ali je YT-DL pravilno nameščen.",
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

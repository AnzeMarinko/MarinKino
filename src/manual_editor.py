import json
import os

from flask import Flask, jsonify, render_template, request, send_from_directory
from flask_compress import Compress

from prepare_movies import FILMS_ROOT, check_folder

app = Flask(__name__, static_url_path="/static", static_folder="static")
app.secret_key = os.getenv("FLASK_KEY")
Compress(app)


def movie_to_dict(m):
    return {
        "cover": m.cover.replace(FILMS_ROOT, ""),
        "title": m.title,
        "original_title": m.original_title,
        "folder": m.folder,
    }


all_films = [movie_to_dict(m) for m in check_folder(FILMS_ROOT)[::-1]]


@app.route("/")
def index():
    return render_template("test.html", movies=all_films)


@app.route("/movies/file/<movies_subfolder>/<movie_folder>/<filename>")
def movie_file(movies_subfolder, movie_folder, filename):
    return send_from_directory(
        os.path.join("../" + FILMS_ROOT, movies_subfolder, movie_folder),
        filename,
        conditional=True,
    )


@app.route("/save_decision", methods=["POST"])
def save_decision():
    data = request.json
    new_metadata = data["data"]
    film_readme_file = os.path.join(data["folder"], "readme.json")
    with open(film_readme_file, "r", encoding="utf-8") as f:
        movie_metadata = json.loads(f.read())

    movie_metadata["Title"] = new_metadata["title"].strip()
    movie_metadata["OriginalTitle"] = new_metadata["original_title"].strip()

    with open(film_readme_file, "w", encoding="utf-8") as f:
        json.dump(movie_metadata, f, ensure_ascii=False, indent=4)

    return jsonify({"status": "ok"})


"""
from mutagen.mp3 import MP3
from mutagen.easyid3 import EasyID3
import os
import glob

music_files = [
    f[11:] for f in glob.iglob("data/music/**/*.mp3", recursive=True)
]

path = os.path.join("data/music", music_files[0])

# Naložimo datoteko
audio = MP3(path, ID3=EasyID3)

item = {
    "title": ", ".join(audio.get("title", [file.split("/")[-1].replace(".mp3", "")])),
    "artist": ", ".join(audio.get("artist", [""]))
    + " - "
    + ", ".join(audio.get("album", [""])),
    "album": "/" + "/".join(file.split("/")[:-1]),
    "albumartist": ", ".join(audio.get("albumartist", [""])),
    "genre": ", ".join(audio.get("genre", [""])),
    "composer": ", ".join(audio.get("composer", [""])),
}

# TODO: vmes popravi metapodatke preko flask

audio["title"] = "Moj novi naslov"
audio["artist"] = "Popravljen izvajalec"
audio["album"] = "Najboljši hiti"

# Primer z več vrednosti (npr. dva žanra) - bo mutagen sam pretvoril vse v sezname tudi če daš samo en string
audio["genre"] = ["Pop", "Rock"]

# 2. BRISANJE VREDNOSTI
# Če želite podatek popolnoma odstraniti, uporabite 'del' ali 'pop'
if "composer" in audio:
    del audio["composer"]

# 3. SHRANJEVANJE (KLJUČNO!)
# Brez tega klica spremembe ostanejo le v pomnilniku.
audio.save() 

print("Podatki uspešno shranjeni!")
"""


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=8080)

import json
import os
from pathlib import Path

import pandas as pd
from flask import Flask, jsonify, render_template, request, send_from_directory
from flask_compress import Compress

from prepare_movies import FILMS_ROOT, check_folder

app = Flask(__name__, static_url_path="/static", static_folder="static")
app.secret_key = os.getenv("FLASK_KEY")
Compress(app)


def movie_to_dict(m):
    return {
        # "cover": m.cover.replace(FILMS_ROOT, ""),
        "cover": m.cover,
        "title": m.title,
        "original_title": m.original_title,
        "year": m.year,
        "folder": m.folder,
        "description": m.plot,
        "players": m.players,
        "genres": m.genres,
        "imdb_id": m.imdb_id,
    }


all_films = [
    {"old": movie_to_dict(m), "new": movie_to_dict(m_new)}
    for m, m_new in zip(
        check_folder(FILMS_ROOT, use_new=False)[::-1],
        check_folder(FILMS_ROOT, use_new=True)[::-1],
    )
]


@app.route("/")
def index():
    return render_template("test.html", movies=all_films)


@app.route("/movies/file/<movies_subfolder>/<movie_folder>/<filename>")
def movie_file(movies_subfolder, movie_folder, filename):
    return send_from_directory(
        os.path.join(FILMS_ROOT, movies_subfolder, movie_folder),
        filename,
        conditional=True,
    )


DECISIONS_FILE = Path("cache/decisions.json")

DECISIONS = {}
if DECISIONS_FILE.exists():
    if open(DECISIONS_FILE).read():
        DECISIONS = json.load(open(DECISIONS_FILE))


@app.route("/save_decision", methods=["POST"])
def save_decision():
    data = request.json
    idx = str(data["index"])
    DECISIONS[idx] = data["fields"]

    with open(DECISIONS_FILE, "w", encoding="utf-8") as f:
        json.dump(DECISIONS, f, indent=2, ensure_ascii=False)

    return jsonify({"status": "ok"})


keeping_names = ["imdb_id", "Runtimes", "RuntimesByFiles"]
changing_names = [
    "Title",
    "OriginalTitle",
    "Year",
    "Plot",
    "Genres",
    "Players",
]


def change():
    for idx in list(DECISIONS.keys()):
        movie = all_films[int(idx)]
        new_metadata = movie["old"]
        for k, v in DECISIONS[idx].items():
            if v == "new":
                if k == "cover":
                    new_file = movie["new"][k]
                    old_file = movie["old"][k]
                    if "logo.png" not in new_file:
                        if "logo.png" not in old_file:
                            os.remove(old_file)
                            os.rename(new_file, old_file)
                        else:
                            os.rename(
                                new_file,
                                new_file.replace("new_cover", "cover"),
                            )
                else:
                    new_metadata[k] = movie["new"][k]
        film_readme_file = os.path.join(new_metadata["folder"], "readme.json")
        with open(film_readme_file, "r", encoding="utf-8") as f:
            movie_metadata = json.loads(f.read())

        new_movie_metadata = {}
        new_movie_metadata["Film"] = movie_metadata["Film"]
        new_movie_metadata["Title"] = new_metadata["title"]
        new_movie_metadata["OriginalTitle"] = new_metadata["original_title"]
        new_movie_metadata["Year"] = new_metadata["year"]
        new_movie_metadata["Plot"] = new_metadata["description"]
        new_movie_metadata["Genres"] = new_metadata["genres"]
        new_movie_metadata["Players"] = new_metadata["players"]
        new_movie_metadata["imdb_id"] = new_metadata["imdb_id"]
        new_movie_metadata["Runtimes"] = movie_metadata.get("Runtimes", "")
        new_movie_metadata["RuntimesByFiles"] = movie_metadata.get(
            "RuntimesByFiles", {}
        )

        with open(film_readme_file, "w", encoding="utf-8") as f:
            json.dump(new_movie_metadata, f, ensure_ascii=False, indent=4)

        if os.path.exists(
            os.path.join(new_metadata["folder"], "new_cover_thumb.jpg")
        ):
            os.remove(
                os.path.join(new_metadata["folder"], "new_cover_thumb.jpg")
            )
        if os.path.exists(
            os.path.join(new_metadata["folder"], "new_readme.json")
        ):
            os.remove(os.path.join(new_metadata["folder"], "new_readme.json"))
        DECISIONS.pop(idx)
        with open(DECISIONS_FILE, "w", encoding="utf-8") as f:
            json.dump(DECISIONS, f, indent=2, ensure_ascii=False)


# change()

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=8080)

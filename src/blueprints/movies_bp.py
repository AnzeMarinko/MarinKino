import difflib
import json
import logging
import os
import random
import re
import shutil
from datetime import datetime, timezone
from urllib.parse import unquote

from flask import (
    Blueprint,
    make_response,
    redirect,
    render_template,
    request,
    send_from_directory,
    url_for,
)
from flask_login import current_user, login_required

from movies_preparation import FILMS_ROOT, check_folder
from utils import redis_client, safe_path

log = logging.getLogger(__name__)

movies_bp = Blueprint("movies", __name__)

# Genre mapping
GENRES_MAPPING = {
    "Drama": "Drama",
    "Comedy": "Komedija",
    "Romance": "Romantika",
    "Romanca": "Romantika",
    "Family": "Druzinski",
    "Adventure": "Pustolovscina",
    "Pustolovski": "Pustolovscina",
    "Action": "Akcija",
    "Fantasy": "Fantazijski",
    "Domisljijski": "Fantazijski",
    "Mystery": "Misterij",
    "Western": "Vestern",
    "Musical": "Glasbeni",
    "Music": "Glasbeni",
    "Documentary": "Dokumentarni",
    "Biography": "Biografija",
    "History": "Zgodovinski",
    "War": "Vojni",
}

known_genres = []
for g in GENRES_MAPPING.values():
    if g not in known_genres:
        known_genres.append(g)

MOVIES_PER_PAGE = 40

# Initialize films
all_films = {
    m.folder.replace(FILMS_ROOT, ""): {
        "cover": m.cover.replace(FILMS_ROOT, ""),
        "thumbnail": m.thumbnail.replace(FILMS_ROOT, ""),
        "title": m.title,
        "original_title": m.original_title,
        "year": f" ({m.year})" if m.year else "",
        "folder": m.folder.replace(FILMS_ROOT, ""),
        "group_folder": m.folder.replace(FILMS_ROOT, "").split(os.sep)[1],
        "description": m.plot,
        "players": m.players.replace(";", ","),
        "runtimes": m.runtimes,
        "runtimes_by_files": m.runtimes_by_files,
        "slosinh": " Sinhronizirano" if m.slosinh else "",
        "genres": [
            GENRES_MAPPING.get(
                g,
                g.replace("č", "c")
                .replace("š", "s")
                .replace("ž", "z")
                .replace(" ", ""),
            )
            for g in m.genres
        ],
        "video_files": m.video_files,
        "subtitles": m.subtitles,
        "subtitle_buttons": [
            subtitle.replace(".vtt", "")
            .lower()
            .replace("subs", "")
            .replace("subtitles-", "")
            .replace("_", "")
            .replace("si", "slo")
            .title()
            .replace("-Auto", " - Avtomatski prevod")
            for subtitle in m.subtitles
        ],
        "movie_id": f"mov_{i}",
        "recommendation_level": m.recommendation_level,
    }
    for i, m in enumerate(check_folder(FILMS_ROOT))
}

groups = [f["group_folder"] for f in all_films.values()]
group_folders = {
    g: g[3:].replace("-", " ").title() + f" ({groups.count(g)})"
    for g in sorted(list(set(groups)))
}
recommendation_levels = ["", "recommend", "warm-recommend"]

global_movie_index = {}
for m in all_films.values():
    global_movie_index[m["movie_id"]] = m


def get_user_progress_data(user_id):
    data = redis_client.hgetall(f"prog:{user_id}")
    return {k: json.loads(v) for k, v in data.items()}


def add_watch_info(movie, user_data):
    movie["watch_info"] = {}
    total_play_time = 0
    total_duration = 0
    for video_file in movie["video_files"]:
        file_path = os.path.join(movie["folder"][1:], video_file)
        watch_inf = user_data.get(file_path, {})
        last_play_time = watch_inf.get("last_play_time", 0)
        duration = watch_inf.get(
            "duration", float(movie["runtimes_by_files"][video_file]) * 60
        )
        watch_ratio = round(last_play_time / duration * 100)
        if watch_ratio > 95 or abs(duration - last_play_time) < 30:
            watch_ratio = 100
            last_play_time = 0
        total_play_time += watch_ratio * duration / 100
        total_duration += duration
        movie["watch_info"][video_file] = {
            "last_play_time": last_play_time,
            "watch_ratio": watch_ratio,
        }
        movie["last_play_time"] = last_play_time
    movie["watch_ratio"] = int(total_play_time / total_duration * 100)
    return movie


# Helper functions
def str_to_int(s):
    s = str(s)
    if len(s) == 0:
        return 0
    s = [int(i) for i in str(s.split(" ")[-1]).split("-")]
    return sum(s) / len(s)


def fuzzy_match(query, title):
    return difflib.SequenceMatcher(None, query, title.lower()).ratio()


# Main routes
@movies_bp.route("/")
def index():
    if current_user.is_authenticated:
        user_key = f"user_settings:{current_user.id}"
        movies_settings = redis_client.hget(user_key, "movies")
        movies_settings = (
            json.loads(movies_settings) if movies_settings else {}
        )

        new_settings = {}
        genre_filter = request.args.get(
            "genre", movies_settings.get("genre", "")
        )
        sort = request.args.get("sort", movies_settings.get("sort", ""))
        onlyunwatched = request.args.get("onlyunwatched")
        onlyrecommended = request.args.get("onlyrecommended")
        movietype = request.args.get(
            "movietype", movies_settings.get("movietype", "")
        )
        new_settings["genre"] = genre_filter
        new_settings["sort"] = sort
        new_settings["movietype"] = movietype
        redis_client.hset(user_key, "movies", json.dumps(new_settings))

        search_query = request.args.get("q", "").strip().lower()

        user_data = get_user_progress_data(current_user.id)
        movies = [
            m
            for m in all_films.values()
            if (m["group_folder"] == movietype) or (movietype == "")
        ]
        movies = [add_watch_info(m, user_data) for m in movies]

        if genre_filter:
            movies = [m for m in movies if genre_filter in m.get("genres", [])]
        if onlyunwatched == "on":
            movies = [m for m in movies if m["watch_ratio"] < 100]
        if onlyrecommended == "on":
            movies = [m for m in movies if m["recommendation_level"]]

        if sort:
            movies = sorted(
                movies,
                key=lambda m: (
                    str_to_int(m["runtimes"])
                    if "runtime" in sort
                    else m["title"]
                ),
                reverse="desc" in sort,
            )
        else:
            random.shuffle(movies)

        if search_query:
            scored = []

            for m in movies:
                title = m["title"].lower()
                original_title = m["original_title"].lower()
                score = max(
                    fuzzy_match(search_query, title),
                    (
                        fuzzy_match(search_query, original_title)
                        if original_title
                        else 0
                    ),
                )

                if search_query in title or search_query in original_title:
                    score += 0.3

                if score > 0.4:
                    m["_score"] = score
                    scored.append(m)

            movies = sorted(scored, key=lambda x: x["_score"], reverse=True)

        movie_ids = [m["movie_id"] for m in movies]
        cache_key = f"cache:movies:{current_user.id}"
        redis_client.delete(cache_key)
        if movie_ids:
            redis_client.rpush(cache_key, *movie_ids)
            redis_client.expire(cache_key, 3600)
    else:
        genre_filter = request.args.get("genre")
        sort = request.args.get("sort")
        onlyunwatched = request.args.get("onlyunwatched")
        onlyrecommended = request.args.get("onlyrecommended")
        movietype = request.args.get("movietype")
        movies = []

    movies_page = movies[:MOVIES_PER_PAGE]
    has_more = len(movies) > MOVIES_PER_PAGE

    return render_template(
        "index.html",
        pagetitle="MarinKino",
        movies=movies_page,
        has_more=has_more,
        page=1,
        selected_movietype=movietype,
        selected_genre=genre_filter,
        sort=sort,
        onlyunwatched=onlyunwatched == "on",
        onlyrecommended=onlyrecommended == "on",
        group_folders={
            k: v
            for k, v in group_folders.items()
            if (current_user.is_authenticated and current_user.is_admin)
            or "neurejen" not in k.lower()
        },
        known_genres=known_genres,
    )


@movies_bp.route("/movies/page")
@login_required
def movies_page():
    page = int(request.args.get("page", 1))

    cache_key = f"cache:movies:{current_user.id}"
    start = page * MOVIES_PER_PAGE
    end = start + MOVIES_PER_PAGE - 1

    page_ids = redis_client.lrange(cache_key, start, end)
    movies_page = [
        global_movie_index[mid]
        for mid in page_ids
        if mid in global_movie_index
    ]

    has_more = end < redis_client.llen(cache_key) - 1

    return {
        "movies": [
            {**m, "is_admin": current_user.is_admin} for m in movies_page
        ],
        "has_more": has_more,
    }


@movies_bp.route("/movies/play/<movies_subfolder>/<movie_folder>")
@login_required
def play_movie(movies_subfolder, movie_folder):
    user_data = get_user_progress_data(current_user.id)

    film_candidate = all_films.get(
        os.path.sep + os.path.join("", movies_subfolder, movie_folder)
    )
    if film_candidate is None:
        log.error("There is no film candidates!")
        return 0
    film = add_watch_info(film_candidate, user_data)
    video_files = film["video_files"]
    subtitles = film["subtitles"]
    subtitle_buttons = film["subtitle_buttons"]

    if len(video_files) > 0:
        slosubs_file = None
        for subs in subtitles:
            if "slo" in subs.lower() or "si" in subs.lower():
                slosubs_file = subs
        return render_template(
            "player.html",
            pagetitle=film["title"] + film["year"],
            is_collection=len(video_files) > 1,
            movie=film,
            known_genres=known_genres,
            group_folder=movies_subfolder,
            folder=movie_folder,
            video_file=video_files[0],
            video_files=video_files,
            subtitles=subtitles,
            slosubs_file=slosubs_file,
            subtitle_buttons=subtitle_buttons,
        )
    else:
        log.error("No video files!")
        return 0


@movies_bp.route(
    "/movies/remove/<movies_subfolder>/<movie_folder>", methods=["POST"]
)
@login_required
def remove_movie(movies_subfolder, movie_folder):
    global all_films
    if not current_user.is_admin:
        return redirect(url_for("movies.index"))
    removing_folder = os.path.sep + os.path.join(
        "", movies_subfolder, movie_folder
    )
    if removing_folder not in all_films.keys():
        log.error(f"Manjka film za odstranjevanje: {removing_folder}")
        return {"status": "missing", "folder": removing_folder}
    all_films.pop(removing_folder)
    removing_folder = os.path.join(
        "../" + FILMS_ROOT, movies_subfolder, movie_folder
    )
    for filename in os.listdir(removing_folder):
        try:
            path = safe_path(
                "../" + FILMS_ROOT,
                os.path.join(movies_subfolder, movie_folder, filename),
            )
        except ValueError:
            return "", 404
        try:
            if os.path.isfile(path) or os.path.islink(path):
                os.remove(path)
            elif os.path.isdir(path):
                shutil.rmtree(path)
        except Exception as e:
            log.error(f"Napaka pri brisanju {path}: {e}")
    shutil.rmtree(removing_folder)
    log.info(f"Film {removing_folder} odstranjen")
    return {"status": "success", "folder": removing_folder}


@movies_bp.route("/movies/recommend", methods=["POST"])
@login_required
def remcommend_movie():
    global all_films
    if not current_user.is_admin:
        return redirect(url_for("movies.index"))
    data = json.loads(request.data)

    recommendation_level = data["recommendation_level"]
    recommending_folder = data["movieFolder"]
    if recommending_folder not in all_films.keys():
        log.error(f"Manjka film za predlog: {recommending_folder}")
        return {"status": "missing", "folder": recommending_folder}

    if recommendation_level not in recommendation_levels:
        log.error(f"Neveljaven nivo priporočila: {recommendation_level}")
        return {
            "status": "invalid_level",
            "recommendation_level": recommendation_level,
        }

    all_films[recommending_folder][
        "recommendation_level"
    ] = recommendation_level
    recommending_metadata_file = os.path.join(
        FILMS_ROOT, recommending_folder[1:], "readme.json"
    )
    with open(recommending_metadata_file, "r", encoding="utf-8") as f:
        movie_metadata = json.loads(f.read())
    movie_metadata["recommendation_level"] = recommendation_level
    with open(recommending_metadata_file, "w", encoding="utf-8") as f:
        json.dump(movie_metadata, f, ensure_ascii=False, indent=4)
    log.info(
        f"Filmu {recommending_folder} nastavljen nivo priporočila: '{recommendation_level}'"
    )
    return {
        "status": "success",
        "folder": recommending_folder,
        "recommendation_level": recommendation_level,
    }


@movies_bp.route("/movies/file/<movies_subfolder>/<movie_folder>/<filename>")
@login_required
def movie_file(movies_subfolder, movie_folder, filename):
    try:
        safe_path(
            "../" + FILMS_ROOT,
            os.path.join(movies_subfolder, movie_folder, filename),
        )
    except ValueError:
        return "", 404
    if ".mp4" in filename[-4:]:
        range_header = request.headers.get("Range")
        if range_header:
            match = re.match(r"bytes=(\d+)-(\d+)?", range_header)
            if match:
                start = int(match.group(1))
                if start == 0:
                    full_filename = (
                        f"{movies_subfolder}/{movie_folder}/{filename}"
                    )
                    user_key = f"prog:{current_user.id}"
                    data = redis_client.hget(user_key, full_filename)
                    data = json.loads(data) if data else {}
                    data["last_start_time"] = datetime.now(
                        timezone.utc
                    ).isoformat()[:16]
                    data["count_start_time"] = (
                        data.get("count_start_time", 0) + 1
                    )
                    redis_client.hset(
                        user_key, full_filename, json.dumps(data)
                    )
        try:
            response = send_from_directory(
                os.path.join(
                    "../" + FILMS_ROOT, movies_subfolder, movie_folder
                ),
                filename,
                mimetype="video/mp4",
                conditional=True,
            )
            response.direct_passthrough = True
            return response
        except Exception:
            return "", 204
    elif "cover_thumb.jpg" in filename:
        response = make_response(
            send_from_directory(
                os.path.join(
                    "../" + FILMS_ROOT, movies_subfolder, movie_folder
                ),
                filename,
                conditional=True,
            )
        )
        response.headers["Cache-Control"] = "public, max-age=2592000"  # 30 dni
        return response
    return send_from_directory(
        os.path.join("../" + FILMS_ROOT, movies_subfolder, movie_folder),
        filename,
        conditional=True,
    )


@movies_bp.route("/video-progress", methods=["POST"])
@login_required
def video_progress():
    data = json.loads(request.data)
    filename = unquote(data["filename"].split("/movies/file/")[-1])
    if filename == "unknown":
        return "", 404

    current_time = round(data["currentTime"] - 0.49)
    duration = round(data["duration"], 1)

    user_key = f"prog:{current_user.id}"

    user_data = redis_client.hget(user_key, filename)
    user_data = json.loads(user_data) if user_data else {}

    last_play_time = user_data.get("last_play_time", 0)
    total_play_time = user_data.get("total_play_time", 0)

    from_last = current_time - last_play_time
    if 0 < from_last < 60:
        total_play_time += from_last

    user_data["duration"] = duration
    user_data["last_play_time"] = current_time
    user_data["total_play_time"] = total_play_time

    redis_client.hset(user_key, filename, json.dumps(user_data))

    return "", 204


@movies_bp.route("/progress-change", methods=["POST"])
@login_required
def video_progress_change():
    data = json.loads(request.data)
    selected_movie = None
    for f in all_films.values():
        if f["movie_id"] == data["movieId"]:
            selected_movie = f
            break
    if selected_movie is None:
        return "", 204

    user_key = f"prog:{current_user.id}"

    for video_file in selected_movie["video_files"]:
        filename = os.path.join(selected_movie["folder"][1:], video_file)
        user_data = redis_client.hget(user_key, filename)
        user_data = json.loads(user_data) if user_data else {}

        if "duration" not in user_data.keys():
            duration = selected_movie["runtimes_by_files"][video_file] * 60
            user_data["duration"] = duration
        else:
            duration = user_data["duration"]

        user_data["last_play_time"] = (
            0 if int(data["izbor"]) == 0 else duration
        )
        redis_client.hset(user_key, filename, json.dumps(user_data))

    return "", 204

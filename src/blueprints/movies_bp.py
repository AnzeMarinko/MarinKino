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
    session,
    url_for,
)
from flask_login import current_user, login_required

from movies_preparation import FILMS_ROOT, check_folder
from utils import is_current_admin_view, redis_client, safe_path

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
        "user_notes": m.user_notes,
        "is_chosen_series": m.is_chosen_series,
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
    if current_user.is_authenticated and session.get("view_as", None) != "anonymous":
        user_key = f"user_settings:{current_user.id}"
        movies_settings = redis_client.hget(user_key, "movies")
        movies_settings = json.loads(movies_settings) if movies_settings else {}

        new_settings = {}
        genre_filter = request.args.get("genre", movies_settings.get("genre", ""))
        sort = request.args.get("sort", movies_settings.get("sort", ""))
        onlyunwatched = request.args.get("onlyunwatched")
        onlyrecommended = request.args.get("onlyrecommended")
        movietype = request.args.get("movietype", movies_settings.get("movietype", ""))
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
                    str_to_int(m["runtimes"]) if "runtime" in sort else m["title"]
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
        if current_user.is_authenticated:
            cache_key = f"cache:movies:{current_user.id}"
            redis_client.delete(cache_key)
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
            if (is_current_admin_view(current_user) or "neurejen" not in k.lower())
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
        global_movie_index[mid] for mid in page_ids if mid in global_movie_index
    ]

    has_more = end < redis_client.llen(cache_key) - 1

    return {
        "movies": [
            {**m, "is_admin": is_current_admin_view(current_user)} for m in movies_page
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
        return "", 404
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
            video_file=sorted(
                video_files, key=lambda x: x.endswith("_Eng.mp4"), reverse=True
            )[0]
            if film["is_chosen_series"]
            else video_files[0],
            video_files=video_files,
            video_file_languages=[
                {
                    "filename": f,
                    "label": (
                        "Slovensko"
                        if f.endswith("_Slo.mp4")
                        else "Angleško"
                        if f.endswith("_Eng.mp4")
                        else "Neznano"
                    ),
                }
                for f in video_files
            ],
            subtitles=subtitles,
            slosubs_file=slosubs_file,
            subtitle_buttons=subtitle_buttons,
        )
    else:
        log.error("No video files!")
        return "", 404


@movies_bp.route("/movies/remove/<movies_subfolder>/<movie_folder>", methods=["POST"])
@login_required
def remove_movie(movies_subfolder, movie_folder):
    global all_films
    if not is_current_admin_view(current_user):
        return redirect(url_for("movies.index"))
    removing_folder = os.path.sep + os.path.join("", movies_subfolder, movie_folder)
    if removing_folder not in all_films.keys():
        log.error(f"Manjka film za odstranjevanje: {removing_folder}")
        return {"status": "missing", "folder": removing_folder}
    all_films.pop(removing_folder)
    removing_folder = os.path.join(FILMS_ROOT, movies_subfolder, movie_folder)
    for filename in os.listdir(removing_folder):
        try:
            path = safe_path(
                FILMS_ROOT,
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
    if not is_current_admin_view(current_user):
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

    all_films[recommending_folder]["recommendation_level"] = recommendation_level
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
                    full_filename = f"{movies_subfolder}/{movie_folder}/{filename}"
                    user_key = f"prog:{current_user.id}"
                    data = redis_client.hget(user_key, full_filename)
                    data = json.loads(data) if data else {}
                    data["last_start_time"] = datetime.now().isoformat()[:16]
                    data["count_start_time"] = data.get("count_start_time", 0) + 1
                    redis_client.hset(user_key, full_filename, json.dumps(data))
        try:
            response = send_from_directory(
                os.path.join("../" + FILMS_ROOT, movies_subfolder, movie_folder),
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
                os.path.join("../" + FILMS_ROOT, movies_subfolder, movie_folder),
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


@movies_bp.route("/movies/video-progress", methods=["POST"])
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


@movies_bp.route("/movies/progress-change", methods=["POST"])
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

        user_data["last_play_time"] = 0 if int(data["izbor"]) == 0 else duration
        redis_client.hset(user_key, filename, json.dumps(user_data))

    return "", 204


@movies_bp.route("/movies/add-comment", methods=["POST"])
@login_required
def add_comment():
    """Dodaj komentar na film"""
    try:
        data = json.loads(request.data)
        movie_folder = data.get("movieFolder")
        author_name = current_user.id
        author_email = current_user.emails[0]
        comment_text = data.get("comment", "").strip()
        comment_type = data.get("comment_type", "komentar").strip()

        # Validacija
        if not movie_folder or (
            movie_folder not in all_films and movie_folder != "Splošno"
        ):
            log.error(f"Neveljaven film za komentar: {movie_folder}")
            return {"status": "error", "message": "Film ne obstaja"}, 404

        if not comment_text or len(comment_text) < 5:
            msg = "Komentar mora biti dolg vsaj 5 znakov"
            return {"status": "error", "message": msg}, 400

        # Priprava komentarja
        random_index = str(random.randint(1, 1000000))
        comment_obj = {
            "author": author_name,
            "email": author_email,
            "text": comment_text,
            "comment_type": comment_type,
            "date": datetime.now(timezone.utc).isoformat(),
            "type": "ideja",
            "admin_response": None,
            "random_index": random_index,
        }

        # Branje metapodatkov filma
        is_splosno = movie_folder == "Splošno"
        if is_splosno:
            metadata_file = os.path.join(FILMS_ROOT, "users_comments.json")
        else:
            metadata_file = os.path.join(FILMS_ROOT, movie_folder[1:], "readme.json")

        if not os.path.exists(metadata_file):
            if is_splosno:
                movie_metadata = {}
            else:
                log.error(f"Manjka metadata datoteka: {metadata_file}")
                return {
                    "status": "error",
                    "message": "Napaka pri obdelavi",
                }, 500
        else:
            with open(metadata_file, "r", encoding="utf-8") as f:
                movie_metadata = json.loads(f.read())

        # Inicializacija user_notes če ne obstajajo
        if "user_notes" not in movie_metadata:
            movie_metadata["user_notes"] = {}

        # Dodaj komentar
        movie_metadata["user_notes"][random_index] = comment_obj

        # Shranjuj metapodatke
        with open(metadata_file, "w", encoding="utf-8") as f:
            json.dump(movie_metadata, f, ensure_ascii=False, indent=4)

        # Posodobi in-memory podatke
        if not is_splosno:
            all_films[movie_folder]["user_notes"] = movie_metadata["user_notes"]
            movie_title = all_films[movie_folder]["title"]
        else:
            movie_title = "Splošno"

        # Pošlji obvestilo administratorju
        from utils import send_mail, users

        admin_email = users.get("admin", {}).get(
            "emails", [os.getenv("GMAIL_USERNAME")]
        )[0]

        email_html = f"""
        <h2>Nov {comment_type}: {movie_title}</h2>
        <p><strong>Avtor:</strong> {author_name}</p>
        <p><strong>Email:</strong> {author_email}</p>
        <p><strong>Komentar:</strong></p>
        <p>{comment_text}</p>
        <hr>
        <p><a href="{os.getenv("DUCKDNS_DOMAIN")}/admin">Pojdi v admin panel</a></p>
        """

        try:
            send_mail(
                to=[admin_email],
                subject=f"Nov {comment_type}: {movie_title}",
                html=email_html,
            )
            log.info(
                f"Mail s komentarjem poslan administratorju za film {movie_folder}"
            )
        except Exception as e:
            log.error(f"Napaka pri pošiljanju maila: {e}")

        log.info(f"Nov {comment_type} dodan {movie_folder} od {author_name}")
        return {"status": "success", "message": "Hvala za vaš komentar!"}, 200

    except Exception as e:
        log.error(f"Napaka pri dodajanju komentarja: {e}")
        return {
            "status": "error",
            "message": "Napaka pri obdelavi komentarja",
        }, 500


# Tip opozoril s privzetimi ikonami
ALERT_TYPES = {
    "opozorilo": "bi-exclamation-diamond-fill",
    "ideja": "bi-lightbulb-fill",
}


@movies_bp.route("/movies/admin-comment", methods=["POST"])
@login_required
def admin_comment():
    """Dodaj admin odgovor na komentar"""
    if not is_current_admin_view(current_user):
        return {"status": "error", "message": "Dostop ni dovoljen"}, 403

    try:
        data = json.loads(request.data)
        movie_folder = data.get("movieFolder")
        comment_index = data.get("commentIndex")
        admin_response = data.get("response", "").strip()

        # Validacija
        if not movie_folder or (
            movie_folder not in all_films.keys() and movie_folder != "Splošno"
        ):
            log.error(f"Neveljaven film: {movie_folder}")
            return {"status": "error", "message": "Film ne obstaja"}, 404

        if admin_response is None or len(admin_response) == 0:
            return {
                "status": "error",
                "message": "Odgovor ne sme biti prazen",
            }, 400

        # Branje metapodatkov
        is_splosno = movie_folder == "Splošno"
        if is_splosno:
            metadata_file = os.path.join(FILMS_ROOT, "users_comments.json")
        else:
            metadata_file = os.path.join(FILMS_ROOT, movie_folder[1:], "readme.json")

        with open(metadata_file, "r", encoding="utf-8") as f:
            movie_metadata = json.loads(f.read())

        if (
            "user_notes" not in movie_metadata
            or comment_index not in movie_metadata["user_notes"].keys()
        ):
            return {"status": "error", "message": "Komentar ne obstaja"}, 404

        # Dodaj admin odgovor
        movie_metadata["user_notes"][comment_index]["admin_response"] = admin_response
        movie_metadata["user_notes"][comment_index]["admin_response_date"] = (
            datetime.now(timezone.utc).isoformat()
        )

        # Shranjuj
        with open(metadata_file, "w", encoding="utf-8") as f:
            json.dump(movie_metadata, f, ensure_ascii=False, indent=4)

        # Posodobi in-memory podatke
        if not is_splosno:
            all_films[movie_folder]["user_notes"] = movie_metadata["user_notes"]
            movie_title = all_films[movie_folder]["title"]
        else:
            movie_title = "Splošno"

        # Pošlji email avtorju komentarja
        from utils import send_mail

        user_email = movie_metadata["user_notes"][comment_index]["email"]

        email_html = f"""
        <h2>Odgovor na vaš komentar</h2>
        <p><strong>Film:</strong> {movie_title}</p>
        <p><strong>Vaš komentar:</strong></p>
        <p>{movie_metadata["user_notes"][comment_index]["text"]}</p>
        <hr>
        <p><strong>Odgovor:</strong></p>
        <p>{admin_response}</p>
        """

        try:
            send_mail(
                to=[user_email],
                subject=f"Odgovor na vaš komentar: {movie_title}",
                html=email_html,
            )
            log.info(f"Odgovor poslan avtorju komentarja na {user_email}")
        except Exception as e:
            log.error(f"Napaka pri pošiljanju maila avtorju: {e}")

        log.info(f"Admin odgovor dodan na komentar filma {movie_folder}")

        # Pripravi seznam obstoječih opozoril za odgovor
        alerts = [
            {
                "index": i,
                "icon": ALERT_TYPES.get(note.get("type", "ideja")),
                "type": note.get("type", "ideja"),
                "text": note.get("text"),
                "author": note.get("author"),
                "date": note.get("date")[:16],
                "is_admin": note.get("is_admin", False),
            }
            for i, note in movie_metadata["user_notes"].items()
            if note.get("is_admin", False)
        ]

        return {
            "status": "success",
            "message": "Odgovor je bil poslan",
            "movie_folder": movie_folder,
            "movie_title": movie_title,
            "current_alerts": alerts,
        }, 200

    except Exception as e:
        log.error(f"Napaka pri dodajanju admin odgovora: {e}")
        return {"status": "error", "message": "Napaka pri obdelavi"}, 500


@movies_bp.route("/movies/get-comments", methods=["GET"])
@login_required
def get_comments():
    """Pridobi vse uporabniške komentarje za admin panel (ne admin opozoril)"""
    if not is_current_admin_view(current_user):
        return {"status": "error", "message": "Dostop ni dovoljen"}, 403

    try:
        comments_list = []

        metadata_file = os.path.join(FILMS_ROOT, "users_comments.json")
        if os.path.exists(metadata_file):
            with open(metadata_file, "r", encoding="utf-8") as f:
                user_notes = json.loads(f.read()).get("user_notes", [])
                for comment_index, note in user_notes.items():
                    # Pokaži samo uporabniške komentarje (ne admin opozoril)
                    if not note.get("admin_response") and not note.get(
                        "is_admin", False
                    ):
                        comments_list.append(
                            {
                                "author": note.get("author"),
                                "email": note.get("email"),
                                "text": note.get("text"),
                                "date": note.get("date")[:16],
                                "movie_folder": "Splošno",
                                "movie_title": "Splošno",
                                "comment_index": comment_index,
                                "current_alerts": None,
                            }
                        )

        for movie_folder, movie_data in all_films.items():
            user_notes = movie_data.get("user_notes", [])

            for comment_index, note in user_notes.items():
                # Pokaži samo uporabniške komentarje (ne admin opozoril)
                if not note.get("admin_response") and not note.get("is_admin", False):
                    comments_list.append(
                        {
                            "author": note.get("author"),
                            "email": note.get("email"),
                            "text": note.get("text"),
                            "date": note.get("date")[:16],
                            "movie_folder": movie_folder,
                            "movie_title": movie_data.get("title"),
                            "comment_index": comment_index,
                        }
                    )

        return {"comments": comments_list}, 200

    except Exception as e:
        log.error(f"Napaka pri prejemanju komentarjev: {e}")
        return {"status": "error", "message": "Napaka pri obdelavi"}, 500


@movies_bp.route("/movies/add-warning", methods=["POST"])
@login_required
def add_warning():
    """Dodaj opozorilo na film (samo admin)"""
    if not is_current_admin_view(current_user):
        return {"status": "error", "message": "Dostop ni dovoljen"}, 403

    try:
        data = json.loads(request.data)
        movie_folder = data.get("movieFolder")
        warning_text = data.get("text", "").strip()
        warning_type = data.get("type", "opozorilo")
        icon = ALERT_TYPES.get(warning_type)

        # Validacija
        if not movie_folder or movie_folder not in all_films:
            log.error(f"Neveljaven film za opozorilo: {movie_folder}")
            return {"status": "error", "message": "Film ne obstaja"}, 404

        if not warning_text or len(warning_text) < 3:
            return {
                "status": "error",
                "message": "Opozorilo mora biti dolgo vsaj 3 znake",
            }, 400

        if warning_type not in ALERT_TYPES:
            return {
                "status": "error",
                "message": f"Neznan tip opozorila: {warning_type}",
            }, 400

        # Priprava opozorila
        random_index = str(random.randint(1, 1000000))
        warning_obj = {
            "author": current_user.id,
            "text": warning_text,
            "date": datetime.now(timezone.utc).isoformat(),
            "type": warning_type,
            "icon": icon,
            "is_admin": True,
            "random_index": random_index,
        }

        # Branje metapodatkov
        metadata_file = os.path.join(FILMS_ROOT, movie_folder[1:], "readme.json")

        with open(metadata_file, "r", encoding="utf-8") as f:
            movie_metadata = json.loads(f.read())

        if "user_notes" not in movie_metadata:
            movie_metadata["user_notes"] = {}

        # Dodaj opozorilo
        movie_metadata["user_notes"][random_index] = warning_obj

        # Shranjuj
        with open(metadata_file, "w", encoding="utf-8") as f:
            json.dump(movie_metadata, f, ensure_ascii=False, indent=4)

        # Posodobi in-memory podatke
        all_films[movie_folder]["user_notes"] = movie_metadata["user_notes"]

        log.info(
            f"Admin opozorilo '{warning_type}' dodano na film {movie_folder} "
            f"od {current_user.id}"
        )
        return {
            "status": "success",
            "message": "Opozorilo je bilo dodano",
        }, 200

    except Exception as e:
        log.error(f"Napaka pri dodajanju opozorila: {e}")
        return {"status": "error", "message": "Napaka pri obdelavi"}, 500


@movies_bp.route("/movies/edit-warning", methods=["POST"])
@login_required
def edit_warning():
    """Uredi opozorilo na filmu (samo admin)"""
    if not is_current_admin_view(current_user):
        return {"status": "error", "message": "Dostop ni dovoljen"}, 403

    try:
        data = json.loads(request.data)
        movie_folder = data.get("movieFolder")
        warning_index = data.get("warningIndex")
        new_text = data.get("text", "").strip()
        new_type = data.get("type")
        new_icon = data.get("icon")

        # Validacija
        if not movie_folder or movie_folder not in all_films:
            return {"status": "error", "message": "Film ne obstaja"}, 404

        # Branje metapodatkov
        metadata_file = os.path.join(FILMS_ROOT, movie_folder[1:], "readme.json")

        with open(metadata_file, "r", encoding="utf-8") as f:
            movie_metadata = json.loads(f.read())

        if (
            "user_notes" not in movie_metadata
            or warning_index not in movie_metadata["user_notes"].keys()
        ):
            return {"status": "error", "message": "Opozorilo ne obstaja"}, 404

        note = movie_metadata["user_notes"][warning_index]

        # Preverim da je admin opozorilo
        if not note.get("is_admin"):
            return {
                "status": "error",
                "message": "Lahko urediš samo admin opozorila",
            }, 403

        # Posodobi polja
        if new_text:
            note["text"] = new_text
        if new_type:
            note["type"] = new_type
        if new_icon:
            note["icon"] = new_icon
        note["edited_date"] = datetime.now(timezone.utc).isoformat()
        note["edited_by"] = current_user.id

        # Shranjuj
        with open(metadata_file, "w", encoding="utf-8") as f:
            json.dump(movie_metadata, f, ensure_ascii=False, indent=4)

        # Posodobi in-memory
        all_films[movie_folder]["user_notes"] = movie_metadata["user_notes"]

        log.info(f"Opozorilo na {movie_folder} je bilo spremenjeno")
        return {
            "status": "success",
            "message": "Opozorilo je bilo spremenjeno",
        }, 200

    except Exception as e:
        log.error(f"Napaka pri urejanju opozorila: {e}")
        return {"status": "error", "message": "Napaka pri obdelavi"}, 500


@movies_bp.route("/movies/delete-warning", methods=["POST"])
@login_required
def delete_warning():
    """Izbriši opozorilo (samo admin)"""
    if not is_current_admin_view(current_user):
        return {"status": "error", "message": "Dostop ni dovoljen"}, 403

    try:
        data = json.loads(request.data)
        movie_folder = data.get("movieFolder")
        warning_index = data.get("warningIndex")

        # Validacija
        if not movie_folder or movie_folder not in all_films:
            return {"status": "error", "message": "Film ne obstaja"}, 404

        # Branje metapodatkov
        metadata_file = os.path.join(FILMS_ROOT, movie_folder[1:], "readme.json")

        with open(metadata_file, "r", encoding="utf-8") as f:
            movie_metadata = json.loads(f.read())

        if (
            "user_notes" not in movie_metadata
            or warning_index not in movie_metadata["user_notes"].keys()
        ):
            return {"status": "error", "message": "Opozorilo ne obstaja"}, 404

        # Briši opozorilo
        deleted_note = movie_metadata["user_notes"].pop(warning_index)

        # Shranjuj
        with open(metadata_file, "w", encoding="utf-8") as f:
            json.dump(movie_metadata, f, ensure_ascii=False, indent=4)

        # Posodobi in-memory
        all_films[movie_folder]["user_notes"] = movie_metadata["user_notes"]

        log.info(f"Opozorilo '{deleted_note.get('text')}' izbrisano z {movie_folder}")
        return {
            "status": "success",
            "message": "Opozorilo je bilo izbrisano",
        }, 200

    except Exception as e:
        log.error(f"Napaka pri brisanju opozorila: {e}")
        return {"status": "error", "message": "Napaka pri obdelavi"}, 500

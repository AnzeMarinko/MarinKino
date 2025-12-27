from flask import Flask, session, render_template, send_from_directory, request, redirect, url_for, make_response
from flask_login import LoginManager, UserMixin, login_user, login_required, logout_user, current_user
from waitress import serve
from datetime import timedelta, datetime, timezone, date
import os
import re
from main import check_folder, FILMS_ROOT, CACHE_ROOT
from copy import copy
import json
import random
import shutil
from urllib.parse import unquote
from flask_compress import Compress
from werkzeug.middleware.proxy_fix import ProxyFix
from werkzeug.security import generate_password_hash, check_password_hash
import pathlib
from flask_wtf.csrf import CSRFProtect
from flask_limiter import Limiter
from flask_limiter.util import get_remote_address
import glob
from mutagen.mp3 import MP3
from mutagen.easyid3 import EasyID3
import pandas as pd

if not os.path.exists(CACHE_ROOT):
    os.mkdir(CACHE_ROOT)
if not os.path.exists(os.path.join(CACHE_ROOT, "users")):
    os.mkdir(os.path.join(CACHE_ROOT, "users"))

GENRES_MAPPING = {
    "Comedy": "Komedija",
    "Drama": "Drama",
    "Romance": "Romanca",
    "Adventure": "Pustolovski",
    "Family": "Druzinski",
    "Action": "Akcija",
    "Fantasy": "Domisljijski",
}
FILMS_PER_PAGE = 50

app = Flask(__name__, static_url_path='/static', static_folder='static')
app.secret_key = os.getenv("FLASK_KEY")
app.permanent_session_lifetime = timedelta(days=365)  # seja traja eno leto
app.config['REMEMBER_COOKIE_DURATION'] = timedelta(days=365)
Compress(app)
app.wsgi_app = ProxyFix(app.wsgi_app, x_for=1, x_host=1)
csrf = CSRFProtect(app)

limiter = Limiter(
    key_func=get_remote_address,
    default_limits=[]
)
limiter.init_app(app)

login_manager = LoginManager()
login_manager.init_app(app)
login_manager.login_view = 'login'


@app.after_request
def log_response_info(response):   
    request_parts = request.path[1:].split("/")
    if len(request_parts):
        if "static" in request_parts[0] or "progress" in request_parts[0] or "favicon.ico" in request_parts[0] or ".well-known" in request_parts[0]:
            return response
        if "movies" in request_parts[0] and "file" in request_parts[1] and ".mp4" not in request_parts[-1]:
            return response
    user_id = current_user.id if current_user.is_authenticated else "anonymus"
    timestamp = datetime.now().isoformat()[:16]
    if not os.path.exists(f"access/routes/{date.today().isoformat()}"):
        os.makedirs(f"access/routes/{date.today().isoformat()}")
    with open(f"access/routes/{date.today().isoformat()}/{user_id}.log", "a", encoding="utf-8") as f:
        f.write(f"{timestamp} | {request.method} | {request.path} | {response.status}\n")
    return response

# admin control panel
@app.route("/admin")
@login_required
def admin_panel():
    if not current_user.is_admin:
        return redirect(url_for('index'))
    last_system_log_file = None
    for f in sorted(os.listdir("../MarinKinoCache/logs"), reverse=True):
        if f.startswith("server_start_"):
            last_system_log_file = f
            break
    if last_system_log_file:
        with open(os.path.join("../MarinKinoCache/logs", last_system_log_file), "r", encoding="utf-8") as f:
            system_log = "\n".join(f.read().split("\n")[-500:])
    access_stats_users = {}
    access_stats_routes = {}
    for log_date in sorted(os.listdir("access/routes/"), reverse=True):
        access_stats_users[log_date] = {}
        access_stats_routes[log_date] = {}
        for log_file in os.listdir(os.path.join("access/routes/", log_date)):
            with open(os.path.join("access/routes/", log_date, log_file), "r", encoding="utf-8") as f:
                lines = f.readlines()
            user_id = log_file.replace(".log", "")
            for line in lines:
                route = line.split(" | ")[2]
                status = line.split(" | ")[3].replace("\n", "")
                if "/file/" in route:
                    route = route.split("/file/")[0] + "/file/..."
                if len(route.split("/")) > 3:
                    route = "/".join(route.split("/")[:3]) + "/..."
                access_stats_routes[log_date].setdefault(route, {})
                access_stats_routes[log_date][route] = len(lines) if int(status.split(" ")[0]) < 400 else access_stats_routes[log_date][route]

                access_stats_users[log_date].setdefault(status, {})
                access_stats_users[log_date][status].setdefault(user_id, 0)
                access_stats_users[log_date][status][user_id] += 1

    access_stats_users = pd.DataFrame(access_stats_users).T
    access_stats_users = access_stats_users[sorted(access_stats_users.columns)].fillna({}).to_dict()
    access_stats_routes = pd.DataFrame(access_stats_routes).T
    print(access_stats_routes[sorted(access_stats_routes.columns)].fillna(0))
    access_stats_routes = access_stats_routes[sorted(access_stats_routes.columns)].fillna(0).astype(int).T.to_dict()

    users_progress_files = glob.glob(os.path.join(CACHE_ROOT, "users", "*_films_progress.json"))
    users_stats = {}
    for user_progress_file in users_progress_files:
        user_id = os.path.basename(user_progress_file).replace("_films_progress.json", "")
        with open(user_progress_file, "r", encoding="utf-8") as f:
            user_data = json.load(f)
        total_watch_time = 0
        watch_ratios = []
        watched_count = 0
        starting_count = 0
        last_start_time = None
        for video_file, progress in user_data.items():
            watch_time = progress.get("total_play_time", 0)
            duration = progress.get("duration", 0)
            start_time = progress.get("start_time", [])                
            if watch_time and duration:
                watch_ratio = watch_time / duration * 100
                watch_ratios.append(watch_ratio)
                if watch_ratio >= 50:
                    watched_count += 1
                if watch_ratio > 3 and start_time:
                    last_start_time = max(start_time) if start_time else last_start_time
                    starting_count += len(start_time)
            total_watch_time += watch_time

        def seconds_to_str(seconds):
            hours = int(seconds // 3600)
            minutes = int((seconds % 3600) // 60)
            return f"{hours}h {minutes}m"

        users_stats[user_id] = {
            "Skupen čas": seconds_to_str(total_watch_time),
            "Število začetih": starting_count,
            "Število ogledanih": watched_count,
            "Povprečen delež ogleda": f"{round(sum(watch_ratios) / len(watch_ratios), 1) if watch_ratios else 0} %",
            "Zadnji začetek ogleda": last_start_time if last_start_time else "-"
        }
    users_stats = pd.DataFrame(users_stats).T.sort_values(by=["Število ogledanih", "Skupen čas"], ascending=False)
    users_stats, users_stats_columns = users_stats.to_dict(orient="index"), users_stats.columns

    return render_template("admin.html", pagetitle="MarinKino - Nadzorna plošča", system_log=system_log, access_stats_users=access_stats_users,
                           access_stats_routes=access_stats_routes, users_stats=users_stats, users_stats_columns=users_stats_columns)
    

with open("users.json", 'r', encoding="utf-8") as f:
    users = json.loads(f.read())
    

class User(UserMixin):
    def __init__(self, username):
        self.id = username
        self.is_admin = users[username].get("is_admin", False)

def safe_path(base_folder, filename):
    path = pathlib.Path(base_folder) / filename
    path = path.resolve()
    if not str(path).startswith(str(pathlib.Path(base_folder).resolve())):
        raise ValueError("Nevaren path")
    return str(path)

@login_manager.user_loader
def load_user(user_id):
    if user_id in users:
        return User(user_id)
    return None

@app.route('/login', methods=['GET', 'POST'])
@limiter.limit("10 per 15 minutes")
def login():
    error = None  # spremenljivka za napako
    if request.method == 'POST':
        username = request.form['username']
        password = request.form['password']
        if username in users and check_password_hash(users[username]['password_hash'], password):
            user = User(username)
            login_user(user, remember=True)
            session.permanent = True
            return redirect(url_for('index'))
        else:
            error = 'Napačno uporabniško ime ali geslo.'
    return render_template(
        'login.html', error=error,
        pagetitle="Prijava v MarinKino"
        )

@app.route('/register', methods=['GET', 'POST'])
@login_required
def register():
    global users
    error = None 
    if not current_user.is_admin:
        return redirect(url_for('index'))
    if request.method == 'POST':
        username = request.form['username']
        email = request.form['email']
        if username in users:
            error = 'Uporabniško ime zasedeno!'
        else:
            password = ''.join(random.choices('abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789', k=12))
            users[username] = {"password_hash": generate_password_hash(password), "user_id_hash": password, "email": email}
            content = f"Nov uporabnik je bil registriran v MarinKino:\n\nUporabniško ime: {username}\nE-naslov: {email}\nGeslo: {password}\n\nLep pozdrav,\nMarinKino sistem"
            # send to my telegram bot
            os.system(f"curl -X POST https://api.telegram.org/bot{os.getenv('TELEGRAM_BOT_TOKEN')}/sendMessage -d chat_id={os.getenv('TELEGRAM_CHAT_ID')} -d text='{content}'")
            with open("users.json", 'w', encoding="utf-8") as f:
                f.write(json.dumps(users, indent=4))
            return redirect(url_for('index'))
    return render_template('register.html', pagetitle="Registracija v MarinKino", error=error)

@app.route('/logout')
@login_required
def logout():
    logout_user()
    return redirect(url_for('login'))

all_films = check_folder(FILMS_ROOT)
all_films = [{
        "cover": m.cover.replace(FILMS_ROOT, ""), 
        "thumbnail": m.thumbnail.replace(FILMS_ROOT, ""), 
        "title": m.title, 
        "year": f" ({m.year})" if m.year else "", 
        "folder": m.folder.replace(FILMS_ROOT, ""),
        "group_folder": m.folder.replace(FILMS_ROOT, "").split(os.sep)[1],
        "description": m.plot_2,
        "description_2": m.plot_1,
        "players": m.players.replace(";", ","),
        "runtimes": m.runtimes,
        "runtimes_by_files": m.runtimes_by_files,
        "slosinh": " Sinhronizirano" if m.slosinh else "",
        "genres": [GENRES_MAPPING.get(g, g) for g in m.genres], 
        "video_files": m.video_files,
        "subtitles": m.subtitles,
        "subtitle_buttons": [subtitle.replace(".vtt", "").lower().replace("subs", "").replace("subtitles-", "").replace("_", "").replace("si", "slo").title().replace("-Auto", " - Avtomatski prevod") for subtitle in m.subtitles],
        "movie_id": f"mov_{i}"
        } for i, m in enumerate(all_films)]

groups = [f["group_folder"] for f in all_films]
group_folders = {g: g[3:].replace("-", " ").title() + f" ({groups.count(g)})" for g in sorted(list(set(groups)))}
all_films = {g: [f for f in all_films if f["group_folder"] == g] for g in group_folders.keys()}


# Seznam vseh memov v mapi
memes = os.listdir("memes")
# Filtriramo le veljavne slikovne datoteke
memes = [slika for slika in memes if slika.lower().endswith(('.png', '.jpg', '.jpeg', '.gif', '.webp', "mp4"))]
random.shuffle(memes)
meme_id = 0

def str_to_int(s):
    s = str(s)
    if len(s) == 0:
        return 0
    s = [int(i) for i in str(s.split(" ")[-1]).split("-")]
    return sum(s) / len(s)

def add_watch_info(movie, user_data):
    movie["watch_info"] = {}
    total_play_time = 0
    total_duration = 0
    for video_file in movie["video_files"]:
        file_path = os.path.join(movie["folder"][1:], video_file)
        watch_inf = user_data.get(file_path, {})
        last_play_time = watch_inf.get("last_play_time", 0)
        duration = watch_inf.get("duration", float(movie["runtimes_by_files"][video_file]) * 60)
        watch_ratio = round(last_play_time / duration * 100)
        if watch_ratio > 95 or abs(duration - last_play_time) < 30:
            watch_ratio = 100
            last_play_time = 0
        total_play_time += watch_ratio * duration / 100
        total_duration += duration
        movie["watch_info"][video_file] = {"last_play_time": last_play_time, "watch_ratio": watch_ratio}
        movie["last_play_time"] = last_play_time
    movie["watch_ratio"] = total_play_time / total_duration * 100
    return movie

def get_user_progress_data(user_id):
    films_progress_file = os.path.join(CACHE_ROOT, "users", f"{user_id}_films_progress.json")
    if os.path.exists(films_progress_file):
        with open(films_progress_file, "r", encoding="utf-8") as f:
            user_data = json.load(f)
    else:
        user_data = {}
    return user_data

MOVIES_PER_PAGE = 40

@app.route("/")
def index():
    genre_filter = request.args.get('genre')
    sort = request.args.get('sort', "name-asc")
    onlyunwatched = request.args.get('onlyunwatched') == "on"
    movietype = request.args.get('movietype', "")

    if current_user.is_authenticated:
        user_data = get_user_progress_data(current_user.id)
        movies = copy(all_films.get(movietype, []))
        movies = [add_watch_info(m, user_data) for m in movies]

        if genre_filter:
            movies = [m for m in movies if genre_filter in m.get('genres', [])]
        if onlyunwatched:
            movies = [m for m in movies if m["watch_ratio"] < 100]

        movies = sorted(
            movies,
            key=lambda m: str_to_int(m["runtimes"]) if "runtime" in sort else m["title"],
            reverse="desc" in sort
        )

        # 🔥 Shrani seznam v session
        movie_ids = [m["movie_id"] for m in movies]
        session["movies_cache"] = movie_ids
    else:
        movies = []

    # Vrni prvi batch
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
        onlyunwatched=onlyunwatched,
        group_folders=group_folders,
        known_genres=GENRES_MAPPING.values()
    )

# Global lookup: movie_id -> movie object
global_movie_index = {}

for group in all_films.values():
    for m in group:
        global_movie_index[m["movie_id"]] = m

@app.route("/movies/page")
@login_required
def movies_page():
    page = int(request.args.get('page', 1))
    MOVIES_PER_PAGE = 40

    movie_ids = session.get("movies_cache", [])
    start = page * MOVIES_PER_PAGE
    end = start + MOVIES_PER_PAGE

    page_ids = movie_ids[start:end]

    # Pobere dejanske filme iz all_films (ki je globalen)
    movies_page = [global_movie_index[mid] for mid in page_ids]   # razlozim spodaj

    has_more = end < len(movie_ids)

    return {"movies": [
        { **m, "is_admin": current_user.is_admin }
        for m in movies_page
    ], "has_more": has_more}



@app.route("/movies/play/<movies_subfolder>/<movie_folder>")
@login_required
def play_movie(movies_subfolder, movie_folder):
    user_data = get_user_progress_data(current_user.id)

    film_candidates = [f for f in all_films[movies_subfolder] if os.path.sep + os.path.join("", movies_subfolder, movie_folder) == f["folder"]]
    if len(film_candidates) != 1:
        print(f"Got {len(film_candidates)} candidates!")
        return 0
    film = add_watch_info(film_candidates[0], user_data)
    video_files = film["video_files"]
    subtitles = film["subtitles"]
    subtitle_buttons = film["subtitle_buttons"]

    if len(video_files) > 0:
        slosubs_file = None
        for subs in subtitles:
            if "slo" in subs.lower() or "si" in subs.lower():
                slosubs_file = subs
        return render_template("player.html", pagetitle=film["title"] + film["year"], is_collection=len(video_files) > 1, movie=film, known_genres=GENRES_MAPPING.values(), group_folder=movies_subfolder, 
                               folder=movie_folder, video_file=video_files[0], video_files=video_files, subtitles=subtitles, slosubs_file=slosubs_file, subtitle_buttons=subtitle_buttons)
    else:
        print("No video files!")
        return 0

@app.route("/movies/remove/<movies_subfolder>/<movie_folder>", methods=['POST'])
@login_required
def remove_movie(movies_subfolder, movie_folder):
    global all_films
    if not current_user.is_admin:
        return redirect(url_for('index'))
    removing_folder = os.path.sep + os.path.join("", movies_subfolder, movie_folder)
    all_films[movies_subfolder] = [f for f in all_films[movies_subfolder] if removing_folder != f["folder"]]
    removing_folder = os.path.join(FILMS_ROOT, movies_subfolder, movie_folder)
    for filename in os.listdir(removing_folder):
        try:
            path = safe_path(FILMS_ROOT, os.path.join(movies_subfolder, movie_folder, filename))
        except ValueError:
            return "", 404
        try:
            if os.path.isfile(path) or os.path.islink(path):
                os.remove(path)
            elif os.path.isdir(path):
                
                shutil.rmtree(path)
        except Exception as e:
            print(f"Napaka pri brisanju {path}: {e}")
    shutil.rmtree(removing_folder)
    return "", 204

@app.route("/movies/file/<movies_subfolder>/<movie_folder>/<filename>")
@login_required
def movie_file(movies_subfolder, movie_folder, filename):
    try:
        safe_path(FILMS_ROOT, os.path.join(movies_subfolder, movie_folder, filename))
    except ValueError:
        return "", 404
    if ".mp4" in filename[-4:]:
        range_header = request.headers.get('Range')
        if range_header:
            match = re.match(r"bytes=(\d+)-(\d+)?", range_header)
            if match:
                start = int(match.group(1))
                if start == 0:
                
                    films_progress_file = os.path.join(CACHE_ROOT, "users", f"{current_user.id}_films_progress.json")

                    if os.path.exists(films_progress_file):
                        with open(films_progress_file, "r", encoding="utf-8") as f:
                            user_data = json.load(f)
                    else:
                        user_data = {}
                    
                    full_filename = f"{movies_subfolder}/{movie_folder}/{filename}"
                    if full_filename not in user_data.keys():
                        user_data[full_filename] = {}
                    user_data[full_filename]["start_time"] = user_data[full_filename].get("start_time", []) + [datetime.now(timezone.utc).isoformat()[:16]]

                    with open(films_progress_file, "w", encoding="utf-8") as f:
                        json.dump(user_data, f, indent=2)
        return send_from_directory(os.path.join(FILMS_ROOT, movies_subfolder, movie_folder), filename, mimetype='video/mp4', conditional=True)
    elif "cover_thumb.jpg" in filename:
        response = make_response(
            send_from_directory(os.path.join(FILMS_ROOT, movies_subfolder, movie_folder), filename, conditional=True)
        )
        response.headers["Cache-Control"] = "public, max-age=2592000"  # 30 dni
        return response
    return send_from_directory(os.path.join(FILMS_ROOT, movies_subfolder, movie_folder), filename, conditional=True)

@app.route('/video-progress', methods=['POST'])
@login_required
def video_progress():
    data = json.loads(request.data)
    filename = unquote(data['filename'].split("/movies/")[-1])
    if filename == "unknown":
        return "", 204
    current_time = round(data['currentTime'] - .49)
    duration = round(data['duration'], 1)
    films_progress_file = os.path.join(CACHE_ROOT, "users", f"{current_user.id}_films_progress.json")

    if os.path.exists(films_progress_file):
        with open(films_progress_file, "r", encoding="utf-8") as f:
            user_data = json.load(f)
    else:
        user_data = {}
    
    if filename not in user_data.keys():
        user_data[filename] = {}
    if "duration" not in user_data[filename].keys():
        user_data[filename]["duration"] = duration
    from_last = current_time - user_data[filename].get("last_play_time", 0) 
    if 0 < from_last < 60:
        user_data[filename]["total_play_time"] = user_data[filename].get("total_play_time", 0) + from_last 
    user_data[filename]["last_play_time"] = current_time

    with open(films_progress_file, "w", encoding="utf-8") as f:
        json.dump(user_data, f, indent=2)
    return '', 204


@app.route('/progress-change', methods=['POST'])
@login_required
def video_progress_change():
    data = json.loads(request.data)
    selected_movie = None
    for fs in all_films.values():
        for f in fs:
            if f["movie_id"] == data["movieId"]:
                selected_movie = f
                break
    if selected_movie is None:
        return "", 204
    
    films_progress_file = os.path.join(CACHE_ROOT, "users", f"{current_user.id}_films_progress.json")

    if os.path.exists(films_progress_file):
        with open(films_progress_file, "r", encoding="utf-8") as f:
            user_data = json.load(f)
    else:
        user_data = {}

    for video_file in selected_movie["video_files"]:
        filename = os.path.join(selected_movie["folder"][1:], video_file)
    
        if filename not in user_data.keys():
            user_data[filename] = {}
        if "duration" not in user_data[filename].keys():
            duration = selected_movie["runtimes_by_files"][video_file] * 60
            user_data[filename]["duration"] = duration
        else:
            duration = user_data[filename]["duration"]
            
        user_data[filename]["last_play_time"] = 0 if int(data["izbor"]) == 0 else duration

    with open(films_progress_file, "w", encoding="utf-8") as f:
        json.dump(user_data, f, indent=2)
    return '', 204

user_meme_count = {}
user_meme_limit = 33

@app.route("/memes")
@login_required
def meme():
    global meme_id
    global user_meme_count
    user_meme_count[current_user.id] = user_meme_count.get(current_user.id, {})
    if user_meme_count[current_user.id].get("last_date") != str(date.today()):
        user_meme_count[current_user.id]["last_date"] = str(date.today())
        user_meme_count[current_user.id]["count"] = 0
    user_meme_count[current_user.id]["count"] += 1
    if user_meme_count[current_user.id]["count"] > user_meme_limit:
        return render_template("limit_exceeded.html", section="šal", pagetitle="Dovolj za danes v MarinKino")

    # Izberi naključno sliko
    izbrana = memes[meme_id]
    meme_id = (meme_id + 1) % len(memes)
    return render_template("memes.html", pagetitle="MarinKino - Šale in navdihi", fullscreenbutton=True, meme_file_name=izbrana)

@app.route("/memes/file/<meme_file_name>")
@login_required
def meme_file(meme_file_name):
    try:
        path = safe_path("memes", meme_file_name)
    except ValueError:
        return "", 404
    if path.endswith(".mp4"):
        return send_from_directory("memes", meme_file_name, mimetype='video/mp4', conditional=True)
    return send_from_directory("memes", meme_file_name, conditional=True)

@app.route("/meme/delete/<meme_file_name>", methods=["DELETE"])
@login_required
def meme_remove(meme_file_name):
    if not current_user.is_admin:
        return "", 204
    try:
        path = safe_path("memes", meme_file_name)
    except ValueError:
        return "", 404
    os.remove(path)
    return "", 204

def get_albums():
    music_albums = {}
    music_files = sorted([f[6:] for f in glob.iglob("music/**/*.mp3", recursive=True)])
    for s in music_files:
        parts = s.split("/")[:-1]
        music_albums.setdefault("Vse", []).append(s)
        for i in range(len(parts)):
            album = " - ".join(parts[:i+1]).title()
            music_albums.setdefault(album, []).append(s)
    return music_albums

import pandas as pd
music_metadata = {}
for file in get_albums()["Vse"]:
        try:
            audio = MP3(os.path.join("music", file), ID3=EasyID3)

        except Exception as e:
            print(f"❌ Napaka pri {file}: {e}")
            audio = {}

        item = {
            "title": audio.get("title", [file.split("/")[-1].replace(".mp3", "")])[0],
            "artist": audio.get("artist", [""])[0] + " - " + audio.get("album", [""])[0],
            "album": "/" + "/".join(file.split("/")[:-1])
        }
        music_metadata[file] = item

@app.route("/music")
@login_required
def music():
    return render_template("music_player.html", pagetitle="MarinKino - Glasba", is_music=True, albums=get_albums(), music_metadata=music_metadata)

@app.route("/music/file/<path:filename>")
@login_required
def song(filename):
    try:
        path = safe_path("music", filename)
    except ValueError:
        return "", 404
    return send_from_directory("music", filename, conditional=True)

@app.route("/music/delete/<path:filename>", methods=["DELETE"])
@login_required
def song_remove(filename):
    if not current_user.is_admin:
        return "", 204
    try:
        path = safe_path("music", filename)
    except ValueError:
        return "", 404
    os.remove(path)
    return "", 204

@app.route('/favicon.ico')
def favicon():
    return send_from_directory('static', 'logo.png')

@app.route("/pod_krinko")
def pod_krinko():
    return render_template("pod_krinko.html")

pod_krinko_words = pd.read_csv("data/pod_krinko_besede.csv", sep=";").to_dict(orient="split")["data"]

@app.route("/pod_krinko/new_words")
@limiter.limit("10 per 15 minutes")
def pod_krinko_new_words():
    new_words = copy(pod_krinko_words[random.randint(0, len(pod_krinko_words) - 1)])
    random.shuffle(new_words)
    return new_words


if __name__ == "__main__":
    print("Started server")
    try:
        serve(app, host="0.0.0.0", port=5000, threads=8)
    except OSError:
        app.run(host="localhost", port=5050)

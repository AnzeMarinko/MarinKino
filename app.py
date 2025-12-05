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
@limiter.limit("5 per 15 minutes")
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
    return render_template('login.html', error=error)

@app.route('/register', methods=['GET', 'POST'])
@login_required
def register():
    global users
    error = None 
    if not current_user.is_admin:
        return redirect(url_for('index'))
    if request.method == 'POST':
        username = request.form['username']
        password = request.form['password']
        password2 = request.form['password2']
        if username in users:
            error = 'Uporabniško ime zasedeno!'
        elif len(password) < 4 or password != password2:
            error = 'Geslo mora imeti vsaj 4 znake in mora biti pravilno ponovljeno!'
        else:
            users[username] = {"password_hash": generate_password_hash(password), "user_id_hash": password}
            with open("users.json", 'w', encoding="utf-8") as f:
                f.write(json.dumps(users, indent=4))
            return redirect(url_for('index'))
    return render_template('register.html', error=error)

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
group_folders = {g: g[3:].title() + f"-({groups.count(g)})" for g in set(groups)}
all_films = {g: [f for f in all_films if f["group_folder"] == k] for k, g in group_folders.items()}

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

@app.route("/")
@login_required
def index():
    user_data = get_user_progress_data(current_user.id)
    genre_filter = request.args.get('genre')
    sort = request.args.get('sort', "name-asc")
    onlyunwatched = request.args.get('onlyunwatched') == "on"
    movies = copy(all_films)
    for k in movies.keys():
        movies[k] = [add_watch_info(m, user_data) for m in movies[k]]
        if genre_filter:
            movies[k] = [m for m in movies[k] if genre_filter in m.get('genres', [])]
        if onlyunwatched:
            movies[k] = [m for m in movies[k] if m["watch_ratio"] < 100]
        movies[k] = sorted(movies[k], key=lambda m: str_to_int(m["runtimes"]) if "runtime" in sort else m["title"], reverse="desc" in sort)

    return render_template("index.html", movies=movies, selected_genre=genre_filter, sort=sort, onlyunwatched=onlyunwatched, group_folders=[group_folders[k] for k in sorted(group_folders.keys())], known_genres=GENRES_MAPPING.values())

@app.route("/play/<movies_subfolder>/<movie_folder>")
@login_required
def play_movie(movies_subfolder, movie_folder):
    user_data = get_user_progress_data(current_user.id)

    film_candidates = [f for f in all_films[group_folders[movies_subfolder]] if os.path.sep + os.path.join("", movies_subfolder, movie_folder) == f["folder"]]
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
        return render_template("player.html", is_collection=len(video_files) > 1, movie=film, known_genres=GENRES_MAPPING.values(), group_folder=movies_subfolder, 
                               folder=movie_folder, video_file=video_files[0], video_files=video_files, subtitles=subtitles, slosubs_file=slosubs_file, subtitle_buttons=subtitle_buttons)
    else:
        print("No video files!")
        return 0

@app.route("/remove/<movies_subfolder>/<movie_folder>", methods=['POST'])
@login_required
def remove_movie(movies_subfolder, movie_folder):
    global all_films
    if not current_user.is_admin:
        return redirect(url_for('index'))
    removing_folder = os.path.sep + os.path.join("", movies_subfolder, movie_folder)
    all_films[group_folders[movies_subfolder]] = [f for f in all_films[group_folders[movies_subfolder]] if removing_folder != f["folder"]]
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

@app.route("/movies/<movies_subfolder>/<movie_folder>/<filename>")
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

@app.route("/meme")
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
        return render_template("limit_exceeded.html", section="šal")

    # Izberi naključno sliko
    izbrana = memes[meme_id]
    meme_id = (meme_id + 1) % len(memes)
    return render_template("memes.html", meme_file_name=izbrana)

@app.route("/memes/<meme_file_name>")
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


if __name__ == "__main__":
    print("Started server")
    serve(app, host="0.0.0.0", port=5000, threads=8)
    # app.run(host="localhost", port=5000)

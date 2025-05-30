from flask import Flask, session, render_template, send_from_directory, request, redirect, url_for, flash
from flask_login import LoginManager, UserMixin, login_user, login_required, logout_user, current_user
from waitress import serve
from datetime import timedelta, datetime, timezone
import os
import re
from main import check_folder, FILMS_ROOT
from copy import copy
import json
import random

GENRES_MAPPING = {
    "Comedy": "Komedija",
    "Drama": "Drama",
    "Romance": "Romanca",
    "Adventure": "Pustolovski",
    "Family": "Druzinski",
    "Action": "Akcija",
    "Fantasy": "Domisljijski",
}

app = Flask(__name__, static_url_path='/static', static_folder='static')
app.secret_key = os.getenv("FLASK_KEY")
app.permanent_session_lifetime = timedelta(days=7)  # seja traja 7 dni

login_manager = LoginManager()
login_manager.init_app(app)
login_manager.login_view = 'login'

with open("users.json", 'r', encoding="utf-8") as f:
    users = json.loads(f.read())

class User(UserMixin):
    def __init__(self, username):
        self.id = username
        self.is_admin = users[username].get("is_admin", False)

@login_manager.user_loader
def load_user(user_id):
    if user_id in users:
        return User(user_id)
    return None

@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        username = request.form['username']
        password = request.form['password']
        if username in users and users[username]['password'] == password:
            user = User(username)
            login_user(user)
            session.permanent = True
            flash('Prijava uspešna!')
            return redirect(url_for('index'))
        else:
            flash('Napačno uporabniško ime ali geslo.')
    return render_template('login.html')

@app.route('/logout')
@login_required
def logout():
    logout_user()
    flash('Odjavljen si bil.')
    return redirect(url_for('login'))

all_films = check_folder(FILMS_ROOT)
all_films = [{
        "cover": m.cover.replace(FILMS_ROOT, ""), 
        "title": m.title, 
        "year": f" ({m.year})" if m.year else "", 
        "folder": m.folder.replace(FILMS_ROOT, ""),
        "group_folder": m.folder.split(os.sep)[3],
        "description": m.plot_2,
        "description_2": m.plot_1,
        "players": m.players.replace(";", ","),
        "runtimes": m.runtimes,
        "slosinh": " Sinhronizirano" if m.slosinh else "",
        "genres": [GENRES_MAPPING.get(g, g) for g in m.genres], 
        
        "video_files": m.video_files,
        "subtitles": m.subtitles,
        } for m in all_films]
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

@app.route("/")
@login_required
def index():
    genre_filter = request.args.get('genre')
    sort = request.args.get('sort', "name-asc")
    movies = copy(all_films)
    for k in movies.keys():
        if genre_filter:
            movies[k] = [m for m in movies[k] if genre_filter in m.get('genres', [])]
        movies[k] = sorted(movies[k], key=lambda m: str_to_int(m["runtimes"]) if "runtime" in sort else m["title"], reverse="desc" in sort)

    return render_template("index.html", movies=movies, selected_genre=genre_filter, sort=sort, group_folders=[group_folders[k] for k in sorted(group_folders.keys())], known_genres=GENRES_MAPPING.values())

@app.route("/play/<movies_subfolder>/<movie_folder>")
@login_required
def play_movie(movies_subfolder, movie_folder):

    film_candidates = [f for f in all_films[group_folders[movies_subfolder]] if os.path.sep + os.path.join("", movies_subfolder, movie_folder) == f["folder"]]
    if len(film_candidates) != 1:
        print(f"Got {len(film_candidates)} candidates!")
        return 0
    film = film_candidates[0]
    video_files = film["video_files"]
    subtitles = film["subtitles"]

    if len(video_files) > 0:
        slosubs_file = None
        for subs in subtitles:
            if "slo" in subs.lower():
                slosubs_file = subs
        return render_template("player.html", is_collection=len(video_files) > 1, movie=film, known_genres=GENRES_MAPPING.values(), group_folder=movies_subfolder, folder=movie_folder, video_file=video_files[0], video_files=video_files, subtitles=subtitles, slosubs_file=slosubs_file)
    else:
        print("No video files!")
        return 0

@app.route("/movies/<movies_subfolder>/<movie_folder>/<filename>")
@login_required
def movie_file(movies_subfolder, movie_folder, filename):
    if ".mp4" in filename[-4:]:
        range_header = request.headers.get('Range')
        if range_header:
            match = re.match(r"bytes=(\d+)-(\d+)?", range_header)
            if match:
                start = int(match.group(1))
                if start == 0:
                
                    films_progress_file = f"users/{current_user.id}_films_progress.json"

                    if os.path.exists(films_progress_file):
                        with open(films_progress_file, "r", encoding="utf-8") as f:
                            user_data = json.load(f)
                    else:
                        user_data = {}
                    
                    full_filename = f"{movies_subfolder}/{movie_folder}/{filename}"
                    if full_filename not in user_data.keys():
                        user_data[full_filename] = {}
                    user_data[full_filename]["start_time"] = user_data[full_filename].get("start_time", []) + [datetime.now(timezone.utc).isoformat()[:19]]

                    with open(films_progress_file, "w", encoding="utf-8") as f:
                        json.dump(user_data, f, indent=2)
        return send_from_directory(os.path.join(FILMS_ROOT, movies_subfolder, movie_folder), filename, mimetype='video/mp4')
    return send_from_directory(os.path.join(FILMS_ROOT, movies_subfolder, movie_folder), filename)

@app.route('/video-progress', methods=['POST'])
@login_required
def video_progress():
    data = json.loads(request.data)
    filename = data.get('filename', 'unknown').split("/movies/")[-1]
    if filename == "unknown":
        return "", 204
    current_time = round(data.get('currentTime', 0), 1)
    duration = round(data.get('duration', 0), 1)
    films_progress_file = f"users/{current_user.id}_films_progress.json"

    if os.path.exists(films_progress_file):
        with open(films_progress_file, "r", encoding="utf-8") as f:
            user_data = json.load(f)
    else:
        user_data = {}
    
    if filename not in user_data.keys():
        user_data[filename] = {}
    if "duration" not in user_data[filename].keys():
        user_data[filename]["duration"] = duration
    user_data[filename]["play_time"] = user_data[filename].get("play_time", []) + [current_time]
    user_data[filename]["update_time"] = user_data[filename].get("update_time", []) + [datetime.now(timezone.utc).isoformat()[:19]]

    with open(films_progress_file, "w", encoding="utf-8") as f:
        json.dump(user_data, f, indent=2)
    return '', 204

@app.route("/meme")
@login_required
def meme():
    global meme_id
    # Izberi naključno sliko
    izbrana = memes[meme_id]
    meme_id = (meme_id + 1) % len(memes)
    return render_template("memes.html", meme_file_name=izbrana)

@app.route("/memes/<meme_file_name>")
@login_required
def meme_file(meme_file_name):
    if ".mp4" in meme_file_name[-4:]:
        return send_from_directory("memes", meme_file_name, mimetype='video/mp4')
    return send_from_directory("memes", meme_file_name)


if __name__ == "__main__":
    print("Started server")
    serve(app, host="0.0.0.0", port=5000, threads=8)
    # app.run(host="localhost", port=5000)

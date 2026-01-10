from flask import Flask, session, render_template, flash, send_from_directory, request, redirect, url_for, make_response
from flask_login import LoginManager, UserMixin, login_user, login_required, logout_user, current_user
from waitress import serve
from datetime import timedelta, datetime, timezone, date
import os
import re
from main import check_folder, FILMS_ROOT
from copy import copy
import json
import random
import shutil
import secrets
from urllib.parse import unquote
from flask_compress import Compress
from werkzeug.middleware.proxy_fix import ProxyFix
from werkzeug.security import generate_password_hash, check_password_hash
import pathlib
from flask_wtf.csrf import CSRFProtect
from flask_limiter import Limiter
from flask_limiter.util import get_remote_address
import glob
from mutagen.mp3 import MP3, HeaderNotFoundError
from mutagen.easyid3 import EasyID3
import pandas as pd
import requests
import logging
import smtplib
from email.message import EmailMessage
import ssl
import redis
redis_client = redis.Redis(host='localhost', port=6379, decode_responses=True)

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
app.config['WTF_CSRF_TIME_LIMIT'] = None

log = logging.getLogger('werkzeug')
log.setLevel(logging.ERROR)

limiter = Limiter(
    key_func=get_remote_address,
    default_limits=[],
    storage_uri="redis://localhost:6379",
)
limiter.init_app(app)

login_manager = LoginManager()
login_manager.init_app(app)
login_manager.login_view = 'login'
login_manager.login_message = None

@app.after_request
def log_response_info(response):   
    request_parts = request.path[1:].split("/")
    if len(request_parts):
        if "static" in request_parts[0] or "progress" in request_parts[0] or "favicon.ico" in request_parts[0] or ".well-known" in request_parts[0]:
            return response
        if len(request_parts) > 1 and "movies/file/" in request.path:
            return response
    user_id = current_user.id if current_user.is_authenticated else "anonymus"
    today = date.today().isoformat()
    month = date.today().strftime("%Y-%m")
    route = request.path.split("/file/")[0] + "/file/..." if "/file/" in request.path else request.path
    if response.status_code < 400:
        redis_client.hincrby(f"stats:monthly:{month}", request.method + " " + route, 1)

    key = f"stats:daily:{today}:{user_id}:{response.status}"
    redis_client.hincrby(key, request.method + " " + route, 1)
    if not redis_client.exists(key):
        redis_client.expire(key, 2592000) # Ključ bo sam izginil po 30 dneh
    return response

# admin control panel
@app.route("/admin")
@login_required
def admin_panel():
    if not current_user.is_admin:
        return redirect(url_for('index'))

    access_stats_users = {}  # {datum: {status: {user_id: count}}}
    access_stats_routes = {} # {datum: {route: count}}

    # Poiščemo vse ključe, ki ustrezajo tvojemu formatu stats:YYYY-MM-DD:*
    for key in redis_client.scan_iter("stats:daily:*"):
        # Razčlenimo ključ: stats, datum, user_id, status_code
        parts = key.split(":")
        if len(parts) < 5: continue
        
        log_date = parts[2]
        user_id = parts[3]
        status = parts[4]

        # Pridobimo vse poti (poti so polja v hashu)
        routes_data = redis_client.hgetall(key)
        
        # Inicializacija struktur za ta datum
        access_stats_routes.setdefault(log_date, {})
        access_stats_users.setdefault(status, {})
        access_stats_users[status].setdefault(log_date, {})
        access_stats_users[status][log_date].setdefault(user_id, {
            "routes": "\n".join([v[1] for v in sorted([(count, f"{count}x {route_method}") for route_method, count in routes_data.items()], reverse=True)[:10]]), 
            "count": 0})

        for route_method, count in routes_data.items():
            count = int(count)
            # Dodaj k statistiki uporabnika
            access_stats_users[status][log_date][user_id]["count"] += count
            
            # Dodaj k statistiki poti
            if status.startswith("2") or status.startswith("3"):
                access_stats_routes[log_date].setdefault(route_method, 0)
                access_stats_routes[log_date][route_method] += count

    if access_stats_users:
        access_stats_users = {k: v for k, v in sorted(list(access_stats_users.items())) if v}
    
    if access_stats_routes:
        df_routes = pd.DataFrame(access_stats_routes).T
        access_stats_routes = df_routes[sorted(df_routes.columns)].fillna(0).astype(int).T.to_dict()

    access_stats_monthly = {} # {mesec: {pot: count}}

    # Poiščemo mesečne ključe
    for key in redis_client.scan_iter("stats:monthly:*"):
        month_label = key.split(":")[-1] # npr. "2025-12"
        
        # Pridobimo vse poti in njihove števce za ta mesec
        monthly_data = redis_client.hgetall(key)
        
        access_stats_monthly[month_label] = {}
        for route_method, count in monthly_data.items():
            access_stats_monthly[month_label][route_method] = int(count)

    if access_stats_monthly:
        df_monthly = pd.DataFrame(access_stats_monthly).T.fillna(0).astype(int)
        df_monthly = df_monthly[sorted(df_monthly.columns, reverse=True)].T
        df_monthly['total'] = df_monthly.sum(axis=1)
        df_monthly = df_monthly.sort_values(by='total', ascending=False).drop(columns=['total']).head(20).T
        access_stats_monthly_dict = df_monthly.to_dict(orient="index")
        monthly_columns = df_monthly.columns
    else:
        access_stats_monthly_dict = {}
        monthly_columns = []

    users_stats = {}
    # Dobimo vse ključe, ki se začnejo s "prog:" (to so naši uporabniki)
    user_prog_keys = redis_client.keys("prog:*")

    for key in user_prog_keys:
        user_id = key.split(":")[1]
        # Pridobimo vse podatke o filmih za tega uporabnika (vsebuje JSON nize)
        user_data_raw = redis_client.hgetall(key)
        
        total_watch_time = 0
        watch_ratios = []
        watched_count = 0
        starting_count = 0
        last_start_time = "-"

        for video_file, progress_json in user_data_raw.items():
            progress = json.loads(progress_json)
            
            watch_time = progress.get("total_play_time", 0)
            duration = progress.get("duration", 0)
            # Če boš v Redis dodajal tudi start_time (seznam), ga obdelaj tukaj
            count_start_time = progress.get("count_start_time", 0) 
            current_max_start = progress.get("last_start_time")

            if watch_time and duration:
                ratio = (watch_time / duration) * 100
                watch_ratios.append(ratio)
                if ratio >= 50: # Recimo, da je 50% že ogledan film
                    watched_count += 1
                
                # Preverimo zadnji štart ogleda (če ga shranjuješ)
                if count_start_time and current_max_start:
                    starting_count += count_start_time
                    if last_start_time == "-" or current_max_start > last_start_time:
                        last_start_time = current_max_start
            
            total_watch_time += watch_time

        def seconds_to_str(seconds):
            hours = int(seconds // 3600)
            minutes = int((seconds % 3600) // 60)
            return f"{hours}h {minutes:02}m"

        users_stats[user_id] = {
            "Skupen čas": seconds_to_str(total_watch_time),
            "Število začetih": starting_count,
            "Število ogledanih": watched_count,
            "Povprečen delež ogleda": f"{round(sum(watch_ratios) / len(watch_ratios), 1) if watch_ratios else 0} %",
            "Zadnji začetek ogleda": last_start_time
        }

    # Pretvorba v DataFrame za lažje sortiranje in prikaz
    if users_stats:
        df_users = pd.DataFrame(users_stats).T.sort_values(by=["Število ogledanih", "Skupen čas"], ascending=False)
        users_stats_dict = df_users.to_dict(orient="index")
        users_stats_columns = df_users.columns
    else:
        users_stats_dict = {}
        users_stats_columns = []

    last_system_log_file = None
    for f in sorted(os.listdir("../MarinKinoCache/logs"), reverse=True):
        if f.startswith("server_start_"):
            last_system_log_file = f
            break
    if last_system_log_file:
        with open(os.path.join("../MarinKinoCache/logs", last_system_log_file), "r", encoding="utf-8") as f:
            lines = [l.split(" - ") for l in f.read().split("\n")]
            new_lines = []
            last_line = lines[0]
            for line in lines[1:]:
                if len(last_line) < 4 or len(line) < 4 or line[3] != last_line[3] or line[2] != last_line[2]:
                    new_lines.append(" - ".join(last_line))
                    last_line = line
                else:
                    last_line[0] = last_line[0].split(" <-> ")[0] + " <-> " + line[0]
                    last_line[1] = str(int(last_line[1].replace("x", "")) + int(line[1])) + "x"
            new_lines.append(" - ".join(last_line))

            system_log = "\n".join(new_lines[-500:])
        with open(os.path.join("../MarinKinoCache/logs", last_system_log_file), "w", encoding="utf-8") as f:
            f.write("\n".join(new_lines))

    return render_template("admin.html", pagetitle="MarinKino - Nadzorna plošča", system_log=system_log, access_stats_users=access_stats_users,
                           access_stats_routes=access_stats_routes, users_stats=users_stats_dict, users_stats_columns=users_stats_columns,
                           access_stats_monthly=access_stats_monthly_dict, monthly_columns=monthly_columns)
    

with open("users.json", 'r', encoding="utf-8") as f:
    users = json.loads(f.read())
    

class User(UserMixin):
    def __init__(self, username):
        self.id = username
        self.is_admin = users[username].get("is_admin", False)
        self.email = users[username].get("email", "")

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
            flash(error, "error")
    return render_template(
        'login.html', 
        pagetitle="Prijava v MarinKino"
        )


def save_users():
    global users
    with open("users.json", 'w', encoding="utf-8") as f:
        f.write(json.dumps(users, indent=4))


def find_user_by_email(email):
    if not email:
        return None
    for username, data in users.items():
        if data.get("email", "").lower() == email.lower():
            return username
    return None

def send_mail(to, cc=None, bcc=None, subject="", text="", html="", batch_id=""):
    msg = EmailMessage()

    msg["From"] = f"MarinKino <{os.getenv('MAIL_USERNAME')}>"
    msg["To"] = ", ".join(to) if isinstance(to, list) else to

    if cc:
        msg["Cc"] = ", ".join(cc)
    if bcc:
        msg["Bcc"] = ", ".join(bcc)

    msg["Subject"] = subject

    # fallback text (zelo priporočeno)
    msg.set_content(text)

    # HTML verzija
    if html:
        msg.add_alternative(html, subtype="html")

    recipients = []
    for field in (to, cc, bcc):
        if field:
            recipients += field if isinstance(field, list) else [field]

    base = f"mail:{date.today().isoformat()[:7]}:{batch_id}"
    # add recipients to Redis set
    redis_client.sadd(f"{base}:recipients", *recipients)
    context = ssl.create_default_context()

    try:
        with smtplib.SMTP("smtp.gmail.com", 587, timeout=15) as server:
            server.starttls(context=context)
            server.login(
                os.getenv("GMAIL_USERNAME"),
                os.getenv("GMAIL_TOKEN")
            )

            # send_message VRNE dict zavrnjenih naslovov
            failed = server.send_message(
                msg,
                to_addrs=recipients
            )

            for email in recipients:
                if email in (failed or {}):
                    code, reason = failed[email]
                    redis_client.hset(
                        f"{base}:errors",
                        find_user_by_email(email) or email,
                        f"{code} {reason}"
                    )

    except smtplib.SMTPException as e:
        # globalni SMTP error (npr. auth, timeout)
        redis_client.hset(
            f"{base}:errors",
            f"smtp_exception_{datetime.utcnow().isoformat()}",
            str(e)
        )
        raise


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
        elif find_user_by_email(email) is not None:
            error = 'E-naslov je že registriran!'
        elif username is None or not re.match(r'^[a-zA-Z0-9_.-]+$', username) or len(username) < 3 or len(username) > 30:
            error = 'Uporabniško ime sme vsebovati le črke, številke, pike, podčrtaje in vezaje ter mora biti dolgo od 3 do 30 znakov!'
        else:
            password = ''.join(random.choices('abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789', k=12))
            users[username] = {"password_hash": generate_password_hash(password), "email": email, "incoming_date": date.today().isoformat()}
            content = f"Nov uporabnik je bil registriran v MarinKino:\n\nVstopna stran: anzemarinko.duckdns.org\nUporabniško ime: {username}\nE-naslov: {email}\nGeslo: {password}\n\nLep pozdrav,\nMarinKino sistem"
            # send to my telegram bot
            requests.post(f"https://api.telegram.org/bot{os.getenv('TELEGRAM_BOT_TOKEN')}/sendMessage", data={"chat_id": os.getenv('TELEGRAM_CHAT_ID'), "text": content})
            with open("users.json", 'w', encoding="utf-8") as f:
                f.write(json.dumps(users, indent=4))
            send_mail(
                to=[email],
                subject="Dostop do MarinKino",
                text=content,
                html=render_template("mail_newuser.html", username=username, password=password, is_for_mail=True),
                batch_id="new_user_credentials"
            )
            send_mail(
                to=[email],
                subject="Uporaba MarinKino",
                text="https://anzemarinko.duckdns.org/help",
                html=render_template("mail_user_intro.html", username=username, is_for_mail=True),
                batch_id="new_user_introduction"
            )
            return redirect(url_for('index'))
    if error:
        flash(error, "error")
    return render_template('register.html', pagetitle="Registracija v MarinKino")


@app.route('/forgot_password', methods=['GET', 'POST'])
@limiter.limit("5 per 10 minutes")
def forgot_password():
    if request.method == 'POST':
        email = request.form.get('email', '').strip()
        username = find_user_by_email(email)
        if username:
            token = secrets.token_urlsafe(32)
            expiry = (datetime.now(timezone.utc) + timedelta(minutes=30)).isoformat()
            users[username]['reset_token'] = token
            users[username]['reset_expiry'] = expiry
            save_users()
            reset_link = url_for('reset_password', token=token, _external=True)
            try:
                send_mail(
                    to=[email],
                    subject="MarinKino - Ponastavitev gesla",
                    text=f"Za ponastavitev gesla za uporabnika {username} uporabite to povezavo: {reset_link} (povezava poteče čez 30 minut)",
                    html=render_template('mail_reset_password.html', reset_link=reset_link, username=username, expiry_minutes=30),
                    batch_id="reset_password"
                )
            except Exception:
                # If mail sending fails, we still silently continue (do not reveal existence)
                pass
        # Generic response to avoid user enumeration
        flash("Če uporabnik z navedenim e-naslovom obstaja, mu je bila poslana povezava za ponastavitev gesla.", "info")
        return redirect(url_for('login'))
    return render_template('forgot_password.html', pagetitle="Pozabljeno geslo")


@app.route('/reset_password/<token>', methods=['GET', 'POST'])
@limiter.limit("10 per 10 minutes")
def reset_password(token):
    # find user by token
    username = None
    user_data = None
    for u, data in users.items():
        if data.get('reset_token') == token:
            username = u
            user_data = data
            break
    if not username or not user_data:
        # redirect to index and add error message:
        flash("Neveljavna ali potekla povezava za ponastavitev gesla.", "error")
        return redirect(url_for('login'))

    expiry_iso = user_data.get('reset_expiry')
    try:
        expiry_dt = datetime.fromisoformat(expiry_iso)
    except Exception:
        expiry_dt = datetime.now(timezone.utc) - timedelta(seconds=1)

    if expiry_dt < datetime.now(timezone.utc):
        users[username].pop('reset_token', None)
        users[username].pop('reset_expiry', None)
        save_users()
        flash("Povezava za ponastavitev gesla je potekla.", "error")
        return redirect(url_for('login'))

    if request.method == 'POST':
        new_password = request.form.get('password', '')
        input_username = request.form.get('username', '')
        form_token = request.form.get('token', '')
        if form_token != token:
            flash("Neveljavna zahteva.", "error")
            return render_template('reset_password.html', token=token)
        if username != input_username:
            flash("Uporabniško ime se ne ujema.", "error")
            return render_template('reset_password.html', token=token)
        if not new_password or len(new_password) < 6:
            flash("Geslo mora vsebovati vsaj 6 znakov.", "error")
            return render_template('reset_password.html', token=token)
        users[username]['password_hash'] = generate_password_hash(new_password)
        users[username].pop('reset_token', None)
        users[username].pop('reset_expiry', None)
        save_users()
        flash("Geslo je bilo uspešno ponastavljeno. Sedaj se lahko prijavite.", "success")
        return redirect(url_for('login'))
    return render_template('reset_password.html', token=token, pagetitle="Ponastavi geslo")

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
    data = redis_client.hgetall(f"prog:{user_id}")
    return {k: json.loads(v) for k, v in data.items()}

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

        # 🔥 Shrani seznam
        movie_ids = [m["movie_id"] for m in movies]
        cache_key = f"cache:movies:{current_user.id}"
        redis_client.delete(cache_key) # počistimo staro
        if movie_ids:
            redis_client.rpush(cache_key, *movie_ids) # shranimo seznam v Redis List
            redis_client.expire(cache_key, 3600) # cache velja 1 uro
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
        group_folders={k: v for k, v in group_folders.items() if (current_user.is_authenticated and current_user.is_admin) or "neurejen" not in k.lower()},
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

    cache_key = f"cache:movies:{current_user.id}"
    start = page * MOVIES_PER_PAGE
    end = start + MOVIES_PER_PAGE - 1 # Redis range vključuje zadnji element
    
    page_ids = redis_client.lrange(cache_key, start, end)
    movies_page = [global_movie_index[mid] for mid in page_ids if mid in global_movie_index]

    has_more = end < redis_client.llen(cache_key) - 1

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
        logging.error(f"Got {len(film_candidates)} candidates!")
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
        logging.error("No video files!")
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
            logging.error(f"Napaka pri brisanju {path}: {e}")
    shutil.rmtree(removing_folder)
    return {"status": "success", "folder": removing_folder}

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
                    full_filename = f"{movies_subfolder}/{movie_folder}/{filename}"
                    user_key = f"prog:{current_user.id}"
                    data = redis_client.hget(user_key, full_filename)
                    data = json.loads(data) if data else {}
                    data["last_start_time"] = datetime.now(timezone.utc).isoformat()[:16]
                    data["count_start_time"] = data.get("count_start_time", 0) + 1
                    redis_client.hset(user_key, full_filename, json.dumps(data))
        try:
            response = send_from_directory(
                os.path.join(FILMS_ROOT, movies_subfolder, movie_folder), 
                filename, 
                mimetype='video/mp4', 
                conditional=True
            )
            response.direct_passthrough = True 
            return response
        except Exception:
            return "", 204 # Tiho vrnemo prazen odgovor
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
    filename = unquote(data['filename'].split("/movies/file/")[-1])
    if filename == "unknown":
        return "", 204
        
    current_time = round(data['currentTime'] - .49)
    duration = round(data['duration'], 1)
    
    # Redis ključ za uporabnika
    user_key = f"prog:{current_user.id}"
    
    # Pridobimo prejšnji čas, da izračunamo skupni čas igranja
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

music_albums = {}
music_files = [f[6:] for f in glob.iglob("music/**/*.mp3", recursive=True)]
for s in music_files:
    parts = s.split("/")[:-1]
    music_albums.setdefault("Vse", []).append(s)
    for i in range(len(parts)):
        album = " - ".join(parts[:i+1]).title()
        music_albums.setdefault(album, []).append(s)
        
music_metadata = {}
for file in music_albums["Vse"]:
        try:
            audio = MP3(os.path.join("music", file), ID3=EasyID3)
        except HeaderNotFoundError as e:
            audio = {}
        except Exception as e:
            logging.error(f"❌ Napaka pri {file}: {e}")
            audio = {}

        item = {
            "title": audio.get("title", [file.split("/")[-1].replace(".mp3", "")])[0],
            "artist": audio.get("artist", [""])[0] + " - " + audio.get("album", [""])[0],
            "album": "/" + "/".join(file.split("/")[:-1])
        }
        music_metadata[file] = item
music_metadata = {k: v for k, v in sorted(music_metadata.items(), key=lambda item: (item[1]["album"], item[1]["artist"], item[1]["title"]))}
music_albums = {k: sorted(music_albums[k], key=lambda x: (music_metadata[x]["album"].lower(), music_metadata[x]["artist"].lower(), music_metadata[x]["title"].lower())) for k in sorted(music_albums.keys())}

@app.route("/music")
@login_required
def music():
    return render_template("music_player.html", pagetitle="MarinKino - Glasba", is_music=True, albums=music_albums, music_metadata=music_metadata)

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
    word_1, word_2 = new_words[0], new_words[1]
    return [word_1.strip().lower(), word_2.strip().lower()]
    

@app.route("/newsletter_image/file/<path:filename>")
def newsletter_image(filename):
    try:
        path = safe_path("newsletter_images", filename)
    except ValueError:
        return "", 404
    user = current_user.id if current_user.is_authenticated else request.args.get("user", "guest")
    if user in users:
        redis_client.incr(f"newsletter_views:{date.today().isoformat()[:7]}:{user}")
    return send_from_directory("newsletter_images", filename, conditional=True)

@app.route("/help")
@login_required
def help():
    return render_template("mail_user_intro.html", is_for_mail=False, username=current_user.id if current_user.is_authenticated else "gost", pagetitle="Navodila za uporabo MarinKino")

@app.route('/send_admin_emails', methods=['GET', 'POST'])
@login_required
def send_admin_emails():
    if not current_user.is_admin:
        return redirect(url_for('index'))
    if request.method == 'POST':
        data = json.loads(request.data)
        whole_list = data.get('whole_list') == "true"
        list_of_emailed_users = [current_user.id] if not whole_list else list(users.keys())
        for username in list_of_emailed_users:
            email = users.get(username, {}).get("email")
            if email:
                # TODO: ob pošiljanju mailov spreminjaj ta klic funkcije
                # if whole_list:
                #     return {"error": "Pošiljanje mailov vsem uporabnikom je začasno onemogočeno."}
                send_mail(
                    to=[email],
                    subject="Uporaba MarinKino",
                    text="https://anzemarinko.duckdns.org/help",
                    html=render_template("mail_user_intro.html", username=username, is_for_mail=True),
                    batch_id="new_user_introduction"
                )
        return {"sent": len(list_of_emailed_users), "emails": list_of_emailed_users, "time": datetime.now().isoformat()}
    return render_template('admin_mailing.html', pagetitle="Pošiljanje mailov uporabnikom MarinKino")

@app.route("/test")
def test():
    is_for_mail = request.args.get("is_for_mail", "true") == "true"
    return render_template("mail_newsletters/2026_januar.html", is_for_mail=True, username=current_user.id if current_user.is_authenticated else "uporabnik", pagetitle="Testni mail")


if __name__ == "__main__":
    logging.info("Started server")
    try:
        serve(app, host="0.0.0.0", port=5000, threads=8)
    except OSError:
        app.run(host="localhost", port=5050)

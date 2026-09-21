import hashlib
import logging
import os
import re
import secrets
from datetime import date, datetime, timedelta, timezone

import requests
from flask import (
    Blueprint,
    flash,
    redirect,
    render_template,
    request,
    session,
    url_for,
)
from flask_login import current_user, login_required, login_user, logout_user
from werkzeug.security import check_password_hash, generate_password_hash

from utils import (
    find_user_by_email,
    is_current_admin_view,
    redis_client,
    send_mail,
    users_file,
)

log = logging.getLogger(__name__)

auth_bp = Blueprint("auth", __name__)
WWW_DOMAIN = os.getenv("WWW_DOMAIN")
AUTH_RATE_LIMIT = 5
AUTH_RATE_LIMIT_TTL = 15 * 60
PASSWORD_MIN_LENGTH = 12

# Shared utilities (imported from main app)
users = {}
User = None


def init_auth_bp(_users, _user):
    """Initialize blueprint with app context"""
    global users, User
    users = _users
    User = _user


def save_users():
    global users
    with open(users_file, "w", encoding="utf-8") as f:
        import json

        f.write(json.dumps(users, indent=4))


def auth_rate_limited(identifier, action):
    client_ip = request.remote_addr or "unknown"
    values = [client_ip, identifier.lower()]
    counts = []
    for value in values:
        digest = hashlib.sha256(value.encode()).hexdigest()
        key = f"auth:limit:{action}:{digest}"
        count = redis_client.incr(key)
        if count == 1:
            redis_client.expire(key, AUTH_RATE_LIMIT_TTL)
        counts.append(count)
    return any(count > AUTH_RATE_LIMIT for count in counts)


def public_base_url():
    configured_url = os.getenv("PUBLIC_BASE_URL")
    if configured_url:
        return configured_url.rstrip("/")
    if WWW_DOMAIN:
        return f"https://{WWW_DOMAIN}"
    return None


def password_strength_error(password, username=""):
    if len(password) < PASSWORD_MIN_LENGTH:
        return "Geslo mora vsebovati vsaj 12 znakov."
    if username and username.lower() in password.lower():
        return "Geslo ne sme vsebovati uporabniškega imena."
    requirements = (
        any(char.islower() for char in password),
        any(char.isupper() for char in password),
        any(char.isdigit() for char in password),
        any(not char.isalnum() for char in password),
    )
    if not all(requirements):
        return (
            "Geslo mora vsebovati malo in veliko črko, številko "
            "ter poseben znak."
        )
    return None


def get_welcome_stats():
    """Vrne enake osnovne statistike kot domača stran."""
    from blueprints.blog_bp import load_blog_posts
    from blueprints.memes_bp import MEMES_COUNT
    from blueprints.movies_bp import get_movies_statistics
    from blueprints.music_bp import MUSIC_COUNT

    stats = get_movies_statistics()
    stats["music_count"] = MUSIC_COUNT
    stats["memes_count"] = MEMES_COUNT
    stats["blog_count"] = sum(
        post.get("published", False) for post in load_blog_posts().values()
    )
    return stats


@auth_bp.route("/login", methods=["GET", "POST"])
def login():
    error = None
    if request.method == "POST":
        username = request.form.get("username", "").strip()
        password = request.form["password"]
        if auth_rate_limited(username, "login"):
            flash("Preveč poskusov. Poskusite znova čez nekaj minut.", "error")
            return render_template("login.html", pagetitle="Prijava"), 429
        if username in users and check_password_hash(
            users[username]["password_hash"], password
        ):
            user = User(username)
            login_user(user, remember=True)
            session.permanent = True
            redis_client.incr(
                f"auth:login:{date.today().isoformat()[:7]}:{username}"
            )
            if users[username].get("first_login", True):
                return redirect(url_for("auth.welcome"))
            return redirect(url_for("home"))
        else:
            client_ip = request.headers.get("X-Real-IP", request.remote_addr)
            log.warning(
                f"ZAVRNJENA_PRIJAVA IP: {client_ip} Uporabnik: {username}"
            )
            redis_client.incr(
                f"auth:reject:{date.today().isoformat()[:7]}:{username}"
            )
            error = "Napačno uporabniško ime ali geslo."
            flash(error, "error")
    return render_template("login.html", pagetitle="Prijava")


@auth_bp.route("/welcome", methods=["GET", "POST"])
@login_required
def welcome():
    if request.method == "POST":
        users[current_user.id]["first_login"] = False
        save_users()
        return redirect(url_for("home"))

    return render_template(
        "welcome.html",
        pagetitle="Dobrodošli v MarinKino",
        stats=get_welcome_stats(),
    )


@auth_bp.route("/admin/register", methods=["GET", "POST"])
@login_required
def register():
    global users
    error = None
    if not is_current_admin_view(current_user):
        return redirect(url_for("home"))
    if request.method == "POST":
        username = request.form["username"].strip()
        email = request.form["email"].strip()
        email2 = request.form.get("email2", "").strip()
        if username in users:
            error = "Uporabniško ime zasedeno!"
        elif find_user_by_email(email, users) is not None:
            error = f"E-naslov {email} je že registriran!"
        elif find_user_by_email(email2, users) is not None:
            error = f"E-naslov {email2} je že registriran!"
        elif (
            username is None
            or not re.match(r"^[a-zA-Z0-9_.-]+$", username)
            or len(username) < 3
            or len(username) > 30
        ):
            error = (
                "Uporabniško ime sme vsebovati le črke, številke, pike,"
                " podčrtaje in vezaje ter mora biti dolgo od 3 do 30 znakov!"
            )
        else:
            base_url = public_base_url()
            if not base_url:
                flash("PUBLIC_BASE_URL ali WWW_DOMAIN ni nastavljen.", "error")
                return redirect(request.url)
            setup_token = secrets.token_urlsafe(32)
            setup_expiry = (
                datetime.now(timezone.utc) + timedelta(hours=24)
            ).isoformat()
            emails = [email] + ([email2] if email2 else [])
            users[username] = {
                "password_hash": generate_password_hash(
                    secrets.token_urlsafe(32)
                ),
                "setup_token_hash": hashlib.sha256(
                    setup_token.encode()
                ).hexdigest(),
                "setup_expiry": setup_expiry,
                "must_set_password": True,
                "emails": emails,
                "incoming_date": date.today().isoformat(),
                "first_login": True,
            }
            setup_link = (
                f"{base_url}"
                f"{url_for('auth.reset_password', token=setup_token)}"
            )
            content = (
                "Ustvarjen je bil vaš uporabniški račun za MarinKino.\n\n"
                f"Uporabniško ime: {username}\n\n"
                "Povezavo za nastavitev gesla smo poslali po e-pošti.\n\n"
                "Lep pozdrav,\nMarinKino sistem"
            )
            requests.post(
                "https://api.telegram.org"
                f"/bot{os.getenv('TELEGRAM_BOT_TOKEN')}/sendMessage",
                data={
                    "chat_id": os.getenv("TELEGRAM_CHAT_ID"),
                    "text": content,
                },
            )
            save_users()
            send_mail(
                to=emails,
                subject="Dostop do MarinKino",
                text=content,
                html=render_template(
                    "mail_newuser.html",
                    username=username,
                    reset_link=setup_link,
                    expiry_minutes=24 * 60,
                    is_for_mail=True,
                ),
                batch_id="new_user_setup",
            )
            return redirect(url_for("home"))
    if error:
        flash(error, "error")
    return render_template(
        "register.html", pagetitle="Registracija v MarinKino"
    )


@auth_bp.route("/password/forgot", methods=["GET", "POST"])
def forgot_password():
    if request.method == "POST":
        email = request.form.get("email", "").strip()
        username = find_user_by_email(email, users)
        if auth_rate_limited(email, "forgot"):
            flash("Preveč zahtev. Poskusite znova čez nekaj minut.", "info")
            return redirect(url_for("auth.login"))
        if username:
            token = secrets.token_urlsafe(32)
            expiry = (
                datetime.now(timezone.utc) + timedelta(minutes=30)
            ).isoformat()
            users[username]["reset_token_hash"] = hashlib.sha256(
                token.encode()
            ).hexdigest()
            users[username]["reset_expiry"] = expiry
            save_users()
            base_url = public_base_url()
            if not base_url:
                log.error("PUBLIC_BASE_URL or WWW_DOMAIN must be configured")
                return redirect(url_for("auth.login"))
            reset_link = (
                f"{base_url}{url_for('auth.reset_password', token=token)}"
            )
            redis_client.incr(
                f"auth:forgot:{date.today().isoformat()[:7]}:{username}"
            )
            try:
                send_mail(
                    to=users[username].get("emails", []),
                    subject="MarinKino - Ponastavitev gesla",
                    text=(
                        f"Za ponastavitev gesla za uporabnika {username} "
                        f"uporabite to povezavo: {reset_link} "
                        f"(povezava poteče čez 30 minut). Zaprosil je nekdo"
                        f" za vaš naslov {email}."
                    ),
                    html=render_template(
                        "mail_reset_password.html",
                        reset_link=reset_link,
                        username=username,
                        expiry_minutes=30,
                        email=email,
                        is_for_mail=True,
                    ),
                    batch_id="reset_password",
                )
            except Exception:
                pass
        flash(
            "Če uporabnik z navedenim e-naslovom obstaja, mu je bila poslana "
            "povezava za ponastavitev gesla.",
            "info",
        )
        return redirect(url_for("auth.login"))
    return render_template(
        "forgot_password.html", pagetitle="Pozabljeno geslo"
    )


@auth_bp.route("/password/reset/<token>", methods=["GET", "POST"])
def reset_password(token):
    username = None
    user_data = None
    token_hash = hashlib.sha256(token.encode()).hexdigest()
    for u, data in users.items():
        if token_hash in {
            data.get("reset_token_hash"),
            data.get("setup_token_hash"),
        }:
            username = u
            user_data = data
            break
    if not username or not user_data:
        redis_client.incr(
            f"auth:reset_token_invalid:{date.today().isoformat()[:7]}:{username}"
        )
        flash(
            "Neveljavna ali potekla povezava za ponastavitev gesla.", "error"
        )
        return redirect(url_for("auth.login"), code=400)

    expiry_iso = user_data.get("reset_expiry") or user_data.get("setup_expiry")
    try:
        expiry_dt = datetime.fromisoformat(expiry_iso)
    except Exception:
        expiry_dt = datetime.now(timezone.utc) - timedelta(seconds=1)

    if expiry_dt < datetime.now(timezone.utc):
        users[username].pop("reset_token_hash", None)
        users[username].pop("reset_expiry", None)
        users[username].pop("setup_token_hash", None)
        users[username].pop("setup_expiry", None)
        save_users()
        flash("Povezava za ponastavitev gesla je potekla.", "error")
        redis_client.incr(
            f"auth:reset_token_expired:{date.today().isoformat()[:7]}:{username}"
        )
        return redirect(url_for("auth.login"), code=400)

    if request.method == "POST":
        new_password = request.form.get("password", "")
        input_username = request.form.get("username", "")
        form_token = request.form.get("token", "")
        if form_token != token:
            flash("Neveljavna zahteva.", "error")
            redis_client.incr(
                f"auth:reset_token_invalid:{date.today().isoformat()[:7]}:{username}"
            )
            return render_template(
                "reset_password.html",
                token=token,
                username=username,
                is_initial_setup=bool(user_data.get("must_set_password")),
            )
        if username != input_username:
            flash("Uporabniško ime se ne ujema.", "error")
            redis_client.incr(
                f"auth:reset_username_invalid:{date.today().isoformat()[:7]}:{username}"
            )
            return render_template(
                "reset_password.html",
                token=token,
                username=username,
                is_initial_setup=bool(user_data.get("must_set_password")),
            )
        strength_error = password_strength_error(new_password, username)
        if strength_error:
            flash(strength_error, "error")
            return render_template(
                "reset_password.html",
                token=token,
                username=username,
                is_initial_setup=bool(user_data.get("must_set_password")),
            )
        if new_password != request.form.get("password_confirm", ""):
            flash("Gesli se ne ujemata.", "error")
            return render_template(
                "reset_password.html",
                token=token,
                username=username,
                is_initial_setup=bool(user_data.get("must_set_password")),
            )
        users[username]["password_hash"] = generate_password_hash(new_password)
        users[username].pop("reset_token_hash", None)
        users[username].pop("reset_expiry", None)
        users[username].pop("setup_token_hash", None)
        users[username].pop("setup_expiry", None)
        users[username].pop("must_set_password", None)
        save_users()
        redis_client.incr(
            f"auth:reset_successful:{date.today().isoformat()[:7]}:{username}"
        )
        flash(
            "Geslo je bilo uspešno ponastavljeno. Sedaj se lahko prijavite.",
            "success",
        )
        return redirect(url_for("auth.login"))
    is_initial_setup = bool(user_data.get("must_set_password"))
    return render_template(
        "reset_password.html",
        token=token,
        username=username,
        is_initial_setup=is_initial_setup,
        pagetitle=("Nastavi geslo" if is_initial_setup else "Ponastavi geslo"),
    )


@auth_bp.route("/logout")
@login_required
def logout():
    logout_user()
    return redirect(url_for("auth.login"))


@auth_bp.route("/password/change", methods=["GET", "POST"])
@login_required
def change_password():
    if request.method == "POST":
        current_password = request.form.get("current_password", "")
        new_password = request.form.get("password", "")
        if not check_password_hash(
            users[current_user.id]["password_hash"], current_password
        ):
            flash("Trenutno geslo ni pravilno.", "error")
            return render_template("change_password.html"), 400

        strength_error = password_strength_error(new_password, current_user.id)
        if strength_error:
            flash(strength_error, "error")
            return render_template("change_password.html"), 400
        if new_password != request.form.get("password_confirm", ""):
            flash("Gesli se ne ujemata.", "error")
            return render_template("change_password.html"), 400

        users[current_user.id]["password_hash"] = generate_password_hash(
            new_password
        )
        save_users()
        logout_user()
        flash("Geslo je bilo spremenjeno. Ponovno se prijavite.", "success")
        return redirect(url_for("auth.login"))

    return render_template("change_password.html")

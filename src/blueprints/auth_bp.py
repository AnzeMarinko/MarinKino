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
    users_file,
)

log = logging.getLogger(__name__)

auth_bp = Blueprint("auth", __name__)
DUCKDNS_DOMAIN = os.getenv("DUCKDNS_DOMAIN")

# Shared utilities (imported from main app)
users = {}
User = None
send_mail = None


def init_auth_bp(_users, _User, _send_mail):
    """Initialize blueprint with app context"""
    global users, User, send_mail
    users = _users
    User = _User
    send_mail = _send_mail


def save_users():
    global users
    with open(users_file, "w", encoding="utf-8") as f:
        import json

        f.write(json.dumps(users, indent=4))


@auth_bp.route("/login", methods=["GET", "POST"])
def login():
    error = None
    if request.method == "POST":
        username = request.form["username"]
        password = request.form["password"]
        if username in users and check_password_hash(
            users[username]["password_hash"], password
        ):
            user = User(username)
            login_user(user, remember=True)
            session.permanent = True
            redis_client.incr(f"auth:login:{date.today().isoformat()[:7]}:{username}")
            return redirect(url_for("movies.index"))
        else:
            redis_client.incr(f"auth:reject:{date.today().isoformat()[:7]}:{username}")
            error = "Napačno uporabniško ime ali geslo."
            flash(error, "error")
    return render_template("login.html", pagetitle="Prijava v MarinKino")


@auth_bp.route("/admin/register", methods=["GET", "POST"])
@login_required
def register():
    global users
    error = None
    if not is_current_admin_view(current_user):
        return redirect(url_for("movies.index"))
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
            error = "Uporabniško ime sme vsebovati le črke, številke, pike, podčrtaje in vezaje ter mora biti dolgo od 3 do 30 znakov!"
        else:
            import random

            password = "".join(
                random.choices(
                    "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789.-+_!=?<>",
                    k=12,
                )
            )
            emails = [email] + ([email2] if email2 else [])
            users[username] = {
                "password_hash": generate_password_hash(password),
                "emails": emails,
                "incoming_date": date.today().isoformat(),
            }
            content = f"Nov uporabnik je bil registriran v MarinKino:\n\nVstopna stran: {DUCKDNS_DOMAIN}\nUporabniško ime: {username}\nE-naslov: {' + '.join(emails)}\nGeslo: {password}\n\nLep pozdrav,\nMarinKino sistem"
            requests.post(
                f"https://api.telegram.org/bot{os.getenv('TELEGRAM_BOT_TOKEN')}/sendMessage",
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
                    password=password,
                    is_for_mail=True,
                ),
                batch_id="new_user_credentials",
            )
            send_mail(
                to=emails,
                subject="Uporaba MarinKino",
                text=f"https://{DUCKDNS_DOMAIN}/help",
                html=render_template(
                    "mail_user_intro.html", username=username, is_for_mail=True
                ),
                batch_id="new_user_introduction",
            )
            return redirect(url_for("movies.index"))
    if error:
        flash(error, "error")
    return render_template("register.html", pagetitle="Registracija v MarinKino")


@auth_bp.route("/password/forgot", methods=["GET", "POST"])
def forgot_password():
    if request.method == "POST":
        email = request.form.get("email", "").strip()
        username = find_user_by_email(email, users)
        if username:
            token = secrets.token_urlsafe(32)
            expiry = (datetime.now(timezone.utc) + timedelta(minutes=30)).isoformat()
            users[username]["reset_token"] = token
            users[username]["reset_expiry"] = expiry
            save_users()
            reset_link = url_for("auth.reset_password", token=token, _external=True)
            redis_client.incr(f"auth:forgot:{date.today().isoformat()[:7]}:{username}")
            try:
                send_mail(
                    to=users[username].get("emails", []),
                    subject="MarinKino - Ponastavitev gesla",
                    text=f"Za ponastavitev gesla za uporabnika {username} uporabite to povezavo: {reset_link} (povezava poteče čez 30 minut). Zaprosil je nekdo za vaš naslov {email}.",
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
            "Če uporabnik z navedenim e-naslovom obstaja, mu je bila poslana povezava za ponastavitev gesla.",
            "info",
        )
        return redirect(url_for("auth.login"))
    return render_template("forgot_password.html", pagetitle="Pozabljeno geslo")


@auth_bp.route("/password/reset/<token>", methods=["GET", "POST"])
def reset_password(token):
    username = None
    user_data = None
    for u, data in users.items():
        if data.get("reset_token") == token:
            username = u
            user_data = data
            break
    if not username or not user_data:
        redis_client.incr(
            f"auth:reset_token_invalid:{date.today().isoformat()[:7]}:{username}"
        )
        flash("Neveljavna ali potekla povezava za ponastavitev gesla.", "error")
        return redirect(url_for("auth.login"), code=400)

    expiry_iso = user_data.get("reset_expiry")
    try:
        expiry_dt = datetime.fromisoformat(expiry_iso)
    except Exception:
        expiry_dt = datetime.now(timezone.utc) - timedelta(seconds=1)

    if expiry_dt < datetime.now(timezone.utc):
        users[username].pop("reset_token", None)
        users[username].pop("reset_expiry", None)
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
            return render_template("reset_password.html", token=token)
        if username != input_username:
            flash("Uporabniško ime se ne ujema.", "error")
            redis_client.incr(
                f"auth:reset_username_invalid:{date.today().isoformat()[:7]}:{username}"
            )
            return render_template("reset_password.html", token=token)
        if not new_password or len(new_password) < 6:
            flash("Geslo mora vsebovati vsaj 6 znakov.", "error")
            return render_template("reset_password.html", token=token)
        users[username]["password_hash"] = generate_password_hash(new_password)
        users[username].pop("reset_token", None)
        users[username].pop("reset_expiry", None)
        save_users()
        redis_client.incr(
            f"auth:reset_successful:{date.today().isoformat()[:7]}:{username}"
        )
        flash(
            "Geslo je bilo uspešno ponastavljeno. Sedaj se lahko prijavite.",
            "success",
        )
        return redirect(url_for("auth.login"))
    return render_template(
        "reset_password.html", token=token, pagetitle="Ponastavi geslo"
    )


@auth_bp.route("/logout")
@login_required
def logout():
    logout_user()
    return redirect(url_for("auth.login"))

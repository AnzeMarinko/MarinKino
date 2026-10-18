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
from redis import Redis
from redis.exceptions import RedisError
from werkzeug.security import check_password_hash, generate_password_hash

from device_sessions import MAX_ADMIN_DEVICES, MAX_DEVICES, DeviceSessionStore
from security_http import rate_limit_identity
from security_storage import atomic_write_json, locked_path, serialized_json
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
_DUMMY_PASSWORD_HASH = generate_password_hash(secrets.token_urlsafe(32))
# Auth state has its own bounded Redis, isolated from public statistics.
statistics_redis = redis_client
if os.getenv("AUTH_REDIS_HOST"):
    redis_client = Redis(
        host=os.environ["AUTH_REDIS_HOST"],
        port=int(os.getenv("AUTH_REDIS_PORT", "6379")),
        decode_responses=True,
        socket_connect_timeout=2,
        socket_timeout=2,
    )
device_sessions = DeviceSessionStore(redis_client)

# Shared utilities (imported from main app)
users = {}
User = None


def init_auth_bp(_users, _user):
    """Initialize blueprint with app context"""
    global users, User
    users = _users
    User = _user


def _clear_device_session():
    # Preserve CSRF and flash state; never call logout_user from a user loader.
    for key in (
        "_user_id",
        "_fresh",
        "_id",
        "_permanent",
        "_remember_seconds",
        "device_id",
        "view_as",
        "authenticated_at",
        "credential_version",
    ):
        session.pop(key, None)
    # Block fallback to an older username-only remember cookie.
    session["_remember"] = "clear"


def load_device_user(user_id):
    """Authenticate only registered devices and refresh their idle timeout."""
    device_id = session.get("device_id")
    started = session.get("authenticated_at", 0)
    lifetime = (
        12 * 3600 if users.get(user_id, {}).get("is_admin") else 30 * 86400
    )
    if (
        isinstance(started, (int, float))
        and 0 <= datetime.now(timezone.utc).timestamp() - started < lifetime
        and user_id in users
        and session.get("credential_version")
        == users[user_id].get("credential_version", "")
        and isinstance(device_id, str)
        and device_id
        and device_sessions.touch(user_id, device_id)
    ):
        session.permanent = True
        return User(user_id)

    _clear_device_session()
    flash("Seja naprave ni več veljavna. Ponovno se prijavite.", "info")
    return None


def _logout_current_device():
    device_id = session.get("device_id")
    if device_id:
        device_sessions.release(current_user.id, device_id)
    logout_user()
    _clear_device_session()


def _remove_bootstrap_password(username):
    if users.get(username, {}).get("is_admin"):
        try:
            os.unlink(
                os.path.join(
                    os.path.dirname(users_file), ".initial-admin-password"
                )
            )
        except FileNotFoundError:
            pass


def save_users():
    for data in users.values():
        data.pop("initial_password", None)
    atomic_write_json(users_file, users)


def auth_stat(event, username):
    username = username if username in users else "<unknown>"
    key = f"auth:{event}:{date.today().isoformat()[:7]}:{username}"
    try:
        pipe = statistics_redis.pipeline(transaction=False)
        pipe.incr(key)
        pipe.expire(key, 400 * 86400)
        pipe.execute()
    except RedisError:
        log.warning("Authentication statistics unavailable")


def auth_rate_limited(identifier, action):
    values = [rate_limit_identity(), identifier.lower()]
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


def _admin_second_factor(username):
    secret = os.getenv("ADMIN_TOTP_SECRET", "").strip()
    if not secret or not users[username].get("is_admin"):
        return True
    import pyotp

    code = request.form.get("otp", "").strip()
    if not re.fullmatch(r"[0-9]{6}", code):
        return False
    if not pyotp.TOTP(secret).verify(code, valid_window=1):
        return False
    # Prevent reuse during the validity window, across devices and workers.
    digest = hashlib.sha256(f"{username}:{code}".encode()).hexdigest()
    return bool(redis_client.set(f"auth:otp:{digest}", "1", nx=True, ex=90))


def password_strength_error(password, username=""):
    if len(password) > 256:
        return "Geslo je predolgo. Največ 256 znakov."
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
    from blueprints.memes_bp import available_memes
    from blueprints.movies_bp import get_movies_statistics
    from blueprints.music_bp import MUSIC_COUNT

    stats = get_movies_statistics()
    stats["music_count"] = MUSIC_COUNT
    stats["memes_count"] = len(available_memes())
    stats["blog_count"] = sum(
        post.get("published", False) for post in load_blog_posts().values()
    )
    return stats


@auth_bp.route("/login", methods=["GET", "POST"])
@serialized_json(lambda: users_file)
def login():
    error = None
    if request.method == "POST":
        username = request.form.get("username", "").strip()
        password = request.form.get("password", "")
        if len(username) > 30 or len(password) > 256:
            return render_template("login.html", pagetitle="Prijava"), 400
        if auth_rate_limited(username, "login"):
            log.warning(
                "ZAVRNJENA_PRIJAVA IP: %s Uporabnik: <rate-limited>",
                request.remote_addr,
            )
            flash("Preveč poskusov. Poskusite znova čez nekaj minut.", "error")
            return render_template("login.html", pagetitle="Prijava"), 429
        if (
            check_password_hash(
                users.get(username, {}).get(
                    "password_hash", _DUMMY_PASSWORD_HASH
                ),
                password,
            )
            and username in users
            and _admin_second_factor(username)
        ):
            previous_user_id = session.get("_user_id")
            previous_device_id = session.get("device_id")
            device_id = secrets.token_urlsafe(32)
            max_devices = (
                MAX_ADMIN_DEVICES
                if users[username].get("is_admin")
                else MAX_DEVICES
            )
            if not device_sessions.register(
                username,
                device_id,
                max_devices=max_devices,
                previous_device_id=(
                    previous_device_id
                    if previous_user_id == username
                    else None
                ),
            ):
                flash(
                    f"Prijavljeni ste že na največ {max_devices} napravah. "
                    "Pred prijavo na tej napravi se odjavite na eni od "
                    "drugih naprav.",
                    "error",
                )
                return render_template("login.html", pagetitle="Prijava"), 403

            if (
                previous_user_id
                and previous_user_id != username
                and previous_device_id
            ):
                device_sessions.release(previous_user_id, previous_device_id)
            _clear_device_session()
            user = User(username)
            login_user(user, remember=False)
            session["device_id"] = device_id
            session["authenticated_at"] = datetime.now(
                timezone.utc
            ).timestamp()
            session["credential_version"] = users[username].get(
                "credential_version", ""
            )
            session.permanent = True
            auth_stat("login", username)
            if users[username].get("must_change_password"):
                return redirect(url_for("auth.change_password"))
            if users[username].get("first_login", True):
                return redirect(url_for("auth.welcome"))
            return redirect(url_for("home"))
        else:
            log.warning(
                "ZAVRNJENA_PRIJAVA IP: %s Uporabnik: %s",
                request.remote_addr,
                username.replace("\n", "").replace("\r", "")[:30],
            )
            auth_stat("reject", username)
            error = "Napačno uporabniško ime ali geslo."
            flash(error, "error")
    return render_template("login.html", pagetitle="Prijava")


@auth_bp.route("/welcome", methods=["GET", "POST"])
@login_required
@serialized_json(lambda: users_file)
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
        elif find_user_by_email(email, dict(users)) is not None:
            error = f"E-naslov {email} je že registriran!"
        elif find_user_by_email(email2, dict(users)) is not None:
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
            with locked_path(users_file):
                if (
                    username in users
                    or find_user_by_email(email, dict(users)) is not None
                    or find_user_by_email(email2, dict(users)) is not None
                ):
                    flash("Uporabnik ali e-naslov že obstaja.", "error")
                    return redirect(request.url)
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
                save_users()
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
                timeout=5,
            )
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
        username = find_user_by_email(email, dict(users))
        if auth_rate_limited(email, "forgot"):
            flash("Preveč zahtev. Poskusite znova čez nekaj minut.", "info")
            return redirect(url_for("auth.login"))
        if username:
            with locked_path(users_file):
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
            auth_stat("forgot", username)
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
@serialized_json(lambda: users_file)
def reset_password(token):
    username = None
    user_data = None
    token_hash = hashlib.sha256(token.encode()).hexdigest()
    expiry_key = None
    for u, data in users.items():
        if token_hash == data.get("reset_token_hash"):
            username = u
            user_data = data
            expiry_key = "reset_expiry"
            break
        if token_hash == data.get("setup_token_hash"):
            username = u
            user_data = data
            expiry_key = "setup_expiry"
            break
    if not username or not user_data:
        auth_stat("reset_token_invalid", username)
        flash(
            "Neveljavna ali potekla povezava za ponastavitev gesla.", "error"
        )
        return redirect(url_for("auth.login"), code=400)

    expiry_iso = user_data.get(expiry_key)
    try:
        expiry_dt = datetime.fromisoformat(expiry_iso)
    except Exception:
        expiry_dt = datetime.now(timezone.utc) - timedelta(seconds=1)

    if expiry_dt < datetime.now(timezone.utc):
        token_key = (
            "reset_token_hash"
            if expiry_key == "reset_expiry"
            else "setup_token_hash"
        )
        users[username].pop(token_key, None)
        users[username].pop(expiry_key, None)
        save_users()
        flash("Povezava za ponastavitev gesla je potekla.", "error")
        auth_stat("reset_token_expired", username)
        return redirect(url_for("auth.login"), code=400)

    if request.method == "POST":
        new_password = request.form.get("password", "")
        input_username = request.form.get("username", "")
        form_token = request.form.get("token", "")
        if form_token != token:
            flash("Neveljavna zahteva.", "error")
            auth_stat("reset_token_invalid", username)
            return render_template(
                "reset_password.html",
                token=token,
                username=username,
                is_initial_setup=bool(user_data.get("must_set_password")),
            )
        if username != input_username:
            flash("Uporabniško ime se ne ujema.", "error")
            auth_stat("reset_username_invalid", username)
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
        device_sessions.revoke_all(username)
        users[username]["credential_version"] = secrets.token_urlsafe(24)
        users[username]["password_hash"] = generate_password_hash(new_password)
        users[username].pop("reset_token_hash", None)
        users[username].pop("reset_expiry", None)
        users[username].pop("setup_token_hash", None)
        users[username].pop("setup_expiry", None)
        users[username].pop("must_set_password", None)
        users[username].pop("must_change_password", None)
        save_users()
        _remove_bootstrap_password(username)
        auth_stat("reset_successful", username)
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


@auth_bp.route("/logout", methods=["POST"])
@login_required
def logout():
    _logout_current_device()
    return redirect(url_for("auth.login"))


@auth_bp.route("/password/change", methods=["GET", "POST"])
@login_required
@serialized_json(lambda: users_file)
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

        device_sessions.revoke_all(current_user.id)
        for key in (
            "reset_token_hash",
            "reset_expiry",
            "setup_token_hash",
            "setup_expiry",
            "must_change_password",
            "must_set_password",
        ):
            users[current_user.id].pop(key, None)
        users[current_user.id]["credential_version"] = secrets.token_urlsafe(
            24
        )
        users[current_user.id]["password_hash"] = generate_password_hash(
            new_password
        )
        save_users()
        _remove_bootstrap_password(current_user.id)
        _logout_current_device()
        flash("Geslo je bilo spremenjeno. Ponovno se prijavite.", "success")
        return redirect(url_for("auth.login"))

    return render_template("change_password.html")

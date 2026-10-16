# ruff: noqa: E402
# Set private creation permissions before imports initialize runtime storage.
import logging
import os
import time
from datetime import date, timedelta

import requests
from flask import Flask, jsonify, redirect, render_template, session
from flask_compress import Compress
from flask_limiter import Limiter
from flask_login import LoginManager, current_user
from flask_wtf.csrf import CSRFProtect, generate_csrf

os.umask(0o027)

from blueprints import (
    MUSIC_COUNT,
    admin_bp,
    auth_bp,
    available_memes,
    blog_bp,
    fitness_bp,
    get_movies_statistics,
    init_admin_bp,
    init_auth_bp,
    init_misc_bp,
    load_blog_posts,
    memes_bp,
    misc_bp,
    movies_bp,
    music_bp,
    seo_bp,
)
from blueprints.auth_bp import load_device_user
from blueprints.auth_bp import redis_client as auth_redis_client
from device_sessions import DEVICE_IDLE_SECONDS
from fitness import DEFAULT_DATABASE
from fitness_access import init_fitness_access
from security_http import (
    add_headers,
    init_security,
    rate_limit_identity,
    record_response,
)
from utils import FLASK_ENV, User, redis_client, users

# Flask app setup
app = Flask(__name__, static_url_path="/static", static_folder="static")
app.secret_key = os.getenv("FLASK_KEY")
if FLASK_ENV == "production" and (
    not app.secret_key
    or len(app.secret_key) < 32
    or app.secret_key == "to_pomaga_kodirati_uporabnikove_piskotke"
):
    raise RuntimeError(
        "FLASK_KEY must be a random secret of at least 32 characters"
    )
app.permanent_session_lifetime = timedelta(seconds=DEVICE_IDLE_SECONDS)
app.config["REMEMBER_COOKIE_DURATION"] = timedelta(days=30)
app.config.update(
    ADMIN_TOTP_ENABLED=bool(os.getenv("ADMIN_TOTP_SECRET")),
    FITNESS_DATABASE=os.getenv("FITNESS_DATABASE", str(DEFAULT_DATABASE)),
    MAX_CONTENT_LENGTH=40 * 1024 * 1024,
    SESSION_COOKIE_SECURE=FLASK_ENV == "production",
    SESSION_COOKIE_HTTPONLY=True,
    SESSION_COOKIE_SAMESITE="Lax",
    SESSION_REFRESH_EACH_REQUEST=True,
    REMEMBER_COOKIE_SECURE=FLASK_ENV == "production",
    REMEMBER_COOKIE_HTTPONLY=True,
    REMEMBER_COOKIE_SAMESITE="Lax",
)
Compress(app)
csrf = CSRFProtect(app)
app.config["WTF_CSRF_TIME_LIMIT"] = 3600

log = logging.getLogger(__name__)

redis_host = os.getenv("AUTH_REDIS_HOST") or os.getenv("REDIS_HOST")
redis_port = int(
    os.getenv("AUTH_REDIS_PORT") or os.getenv("REDIS_PORT", "6379")
)
limiter = Limiter(
    key_func=rate_limit_identity,
    default_limits=[],
    storage_uri=f"redis://{redis_host}:{redis_port}" if redis_host else None,
)
limiter.init_app(app)

last_timeout_time = 0


@app.get("/csrf-token")
def csrf_token():
    return jsonify({"csrf_token": generate_csrf()})


def get_location_from_ip(ip):
    """Get location info from IP address using ipinfo.io
    (free tier: 50k requests/month)"""
    global last_timeout_time
    if FLASK_ENV != "production":
        return {"country": "SI", "city": "Ljubljana", "region": "Unknown"}
    if time.time() - last_timeout_time < 60 * 60:
        return {
            "country": "Unknown",
            "city": "Unknown",
            "region": "Unknown",
        }
    try:
        # Using ipinfo.io instead of ipapi.co (free tier: 50k/month)
        response = requests.get(f"https://ipinfo.io/{ip}/json", timeout=2)
        if response.status_code == 200:
            data = response.json()
            if "error" in data:
                log.warning(f"ipinfo.io error: {data}")
                return {
                    "country": "Unknown",
                    "city": "Unknown",
                    "region": "Unknown",
                }
            return {
                "country": data.get("country", "Unknown"),
                "city": data.get("city", "Unknown"),
                "region": data.get("region", "Unknown"),
                "geolocation": data.get("loc"),
                "postal": data.get("postal"),
            }
        else:
            if response.status_code == 429:
                last_timeout_time = time.time()
                log.warning("ipinfo.io rate limit exceeded")
            else:
                log.warning(
                    f"ipinfo.io request failed"
                    f" with status {response.status_code} and"
                    f" response content: {response.text}"
                )
    except Exception as e:
        if "timeout" in str(e).lower():
            last_timeout_time = time.time()
            log.error("ipinfo.io timeout")
        else:
            log.error(f"Error getting geolocation: {str(e)}")
    return {"country": "Unknown", "city": "Unknown", "region": "Unknown"}


# add variables to all template rendering
@app.context_processor
def inject_global_variables():
    return {
        "current_year": date.today().year,
        "domain": os.getenv("WWW_DOMAIN"),
        "view_as": session.get("view_as", None),
    }


login_manager = LoginManager()
login_manager.init_app(app)
login_manager.login_view = "auth.login"
login_manager.login_message = None


@app.after_request
def add_security_headers(response):
    return add_headers(response, FLASK_ENV == "production")


@app.after_request
def log_response_info(response):
    return record_response(response, redis_client, get_location_from_ip)


@app.get("/healthz")
def healthz():
    try:
        redis_client.ping()
        auth_redis_client.set("health:write-probe", "1", ex=30)
    except Exception:
        return {"status": "unavailable"}, 503
    return {"status": "ok"}


@login_manager.user_loader
def load_user(user_id):
    return load_device_user(user_id)


# Register blueprints
app.register_blueprint(auth_bp)
app.register_blueprint(admin_bp)
app.register_blueprint(fitness_bp)
app.register_blueprint(blog_bp)
app.register_blueprint(movies_bp)
app.register_blueprint(memes_bp)
app.register_blueprint(music_bp)
app.register_blueprint(misc_bp)
app.register_blueprint(seo_bp)
init_fitness_access(app)

# Initialize blueprints with app context
init_auth_bp(users, User)
init_admin_bp(users)
init_misc_bp(users)
init_security(app, limiter)


# Root path handled by movies blueprint
@app.route("/")
def home():
    """Home page with statistics cards"""
    if (
        current_user.is_authenticated
        and session.get("view_as", None) != "anonymous"
    ):
        stats = get_movies_statistics()
        stats["music_count"] = MUSIC_COUNT
        stats["memes_count"] = len(available_memes())
        stats["blog_count"] = sum(
            v.get("published", False) for v in load_blog_posts().values()
        )

        return render_template("index.html", pagetitle="MarinKino", **stats)
    else:
        return redirect("/blog")


if __name__ == "__main__":
    log.info("Started server")
    app.run(host="127.0.0.1", port=5000, debug=False)

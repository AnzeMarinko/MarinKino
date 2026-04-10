import json
import logging
import os
from datetime import date, timedelta

import requests
from flask import Flask, redirect, render_template, request, session
from flask_compress import Compress
from flask_limiter import Limiter
from flask_limiter.util import get_remote_address
from flask_login import LoginManager, current_user
from flask_wtf.csrf import CSRFProtect
from werkzeug.middleware.proxy_fix import ProxyFix

from blueprints import (
    MEMES_COUNT,
    MUSIC_COUNT,
    admin_bp,
    auth_bp,
    blog_bp,
    get_movies_statistics,
    init_admin_bp,
    init_auth_bp,
    init_misc_bp,
    load_blog_posts,
    memes_bp,
    misc_bp,
    movies_bp,
    music_bp,
)
from utils import User, redis_client, send_mail, users

# Flask app setup
app = Flask(__name__, static_url_path="/static", static_folder="static")
app.secret_key = os.getenv("FLASK_KEY")
app.permanent_session_lifetime = timedelta(days=365)
app.config["REMEMBER_COOKIE_DURATION"] = timedelta(days=365)
Compress(app)
app.wsgi_app = ProxyFix(app.wsgi_app, x_for=2, x_host=1, x_proto=2)
csrf = CSRFProtect(app)
app.config["WTF_CSRF_TIME_LIMIT"] = None

log = logging.getLogger(__name__)

redis_host = os.getenv("REDIS_HOST")
redis_port = int(os.getenv("REDIS_PORT", "6379"))
limiter = Limiter(
    key_func=get_remote_address,
    default_limits=[],
    storage_uri=f"redis://{redis_host}:{redis_port}" if redis_host else None,
)
limiter.init_app(app)


def get_location_from_ip(ip):
    """Get location info from IP address using ipinfo.io (free tier: 50k requests/month)"""
    try:
        # Using ipinfo.io instead of ipapi.co (free tier: 50k/month)
        response = requests.get(f"https://ipinfo.io/{ip}/json", timeout=5)
        if response.status_code == 200:
            data = response.json()
            if "error" in data:
                log.warning(f"ipinfo.io error for {ip}: {data}")
                return {"country": "Unknown", "city": "Unknown", "region": "Unknown"}
            return {
                "country": data.get("country", "Unknown"),
                "city": data.get("city", "Unknown"),
                "region": data.get("region", "Unknown"),
                "geolocation": data.get("loc"),
                "postal": data.get("postal"),
            }
        else:
            log.warning(
                f"ipinfo.io request failed for {ip} with status {response.status_code}"
            )
            log.warning(f"IP API response content: {response.text}")
    except Exception as e:
        log.error(f"Error getting geolocation for {ip}: {e}")
    return {"country": "Unknown", "city": "Unknown", "region": "Unknown"}


# add variables to all template rendering
@app.context_processor
def inject_global_variables():
    return {
        "current_year": date.today().year,
        "domain": os.getenv("DUCKDNS_DOMAIN"),
        "view_as": session.get("view_as", None),
    }


login_manager = LoginManager()
login_manager.init_app(app)
login_manager.login_view = "auth.login"
login_manager.login_message = None


@app.after_request
def log_response_info(response):
    request_parts = request.path[1:].split("/")
    if len(request_parts):
        if (
            "static" in request_parts[0]
            or (len(request_parts) > 1 and "progress" in request_parts[1])
            or "favicon.ico" in request_parts[0]
            or ".well-known" in request_parts[0]
        ):
            return response
        if len(request_parts) > 1 and "movies/file/" in request.path:
            return response
    user_id = current_user.id if current_user.is_authenticated else "anonymus"
    today = date.today().isoformat()
    month = date.today().strftime("%Y-%m")
    route = (
        request.path.split("/file/")[0] + "/file/..."
        if "/file/" in request.path
        else request.path
    )
    route = (
        route.split("/password/reset/")[0] + "/password/reset/..."
        if "/password/reset/" in route
        else route
    )

    if response.status_code < 400:
        redis_client.hincrby(f"stats:monthly:{month}", request.method + " " + route, 1)

    key = f"stats:daily:{today}:{user_id}:{response.status}"
    redis_client.hincrby(key, request.method + " " + route, 1)
    if not redis_client.exists(key):
        redis_client.expire(key, 2592000 * 3)

    path_parts = request.path.split("/")
    content_type = path_parts[1] if len(path_parts) > 1 else "other"

    # Track referrer sources
    referrer = request.headers.get("Referer", "")
    if referrer and response.status_code < 400:
        referrer_source = "direct"
        if "facebook.com" in referrer:
            referrer_source = "facebook"
        elif "instagram.com" in referrer:
            referrer_source = "instagram"
        elif "google.com" in referrer:
            referrer_source = "google"
        elif os.getenv("DUCKDNS_DOMAIN") in referrer:
            referrer_source = "internal"
        elif referrer:
            # log.info(f"Unknown referrer source: {referrer} for {request.path}")
            referrer_source = "other"

        redis_client.hincrby(
            f"stats:referrer_content:{today}:{content_type}", referrer_source, 1
        )
        redis_client.expire(f"stats:referrer_content:{today}", 2592000 * 3)

        redis_client.hincrby(f"stats:referrer:{today}", referrer_source, 1)
        redis_client.expire(f"stats:referrer:{today}", 2592000 * 3)

    # Track geolocation (only for successful requests and not too frequent)
    client_ip = request.headers.get("X-Real-IP", request.remote_addr)

    if (
        content_type == "blog"
        and response.status_code < 400
        and not redis_client.exists(f"stats:geo:{client_ip}:{today}")
    ):
        location = get_location_from_ip(client_ip)
        if location["country"] != "Unknown":
            redis_client.hset(f"stats:geo:{today}", client_ip, json.dumps(location))
            redis_client.expire(f"stats:geo:{today}", 2592000 * 3)

    return response


@login_manager.user_loader
def load_user(user_id):
    if user_id in users:
        return User(user_id)
    return None


# Register blueprints
app.register_blueprint(auth_bp)
app.register_blueprint(admin_bp)
app.register_blueprint(blog_bp)
app.register_blueprint(movies_bp)
app.register_blueprint(memes_bp)
app.register_blueprint(music_bp)
app.register_blueprint(misc_bp)

# Initialize blueprints with app context
init_auth_bp(users, User, send_mail)
init_admin_bp(users)
init_misc_bp(users, send_mail)


# Root path handled by movies blueprint
@app.route("/")
def home():
    """Home page with statistics cards"""
    if current_user.is_authenticated and session.get("view_as", None) != "anonymous":
        stats = get_movies_statistics()
        stats["music_count"] = MUSIC_COUNT
        stats["memes_count"] = MEMES_COUNT
        stats["blog_count"] = len(
            [v for v in load_blog_posts().values() if v.get("published", False)]
        )

        return render_template("index.html", pagetitle="MarinKino", **stats)
    else:
        return redirect("/blog")


if __name__ == "__main__":
    log.info("Started server")
    app.run(host="0.0.0.0", port=5000, debug=True)

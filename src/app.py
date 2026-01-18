import logging
import os
from datetime import date, timedelta

from flask import Flask, request
from flask_compress import Compress
from flask_limiter import Limiter
from flask_limiter.util import get_remote_address
from flask_login import LoginManager, current_user
from flask_wtf.csrf import CSRFProtect
from waitress import serve
from werkzeug.middleware.proxy_fix import ProxyFix

from blueprints import (
    admin_bp,
    auth_bp,
    init_admin_bp,
    init_auth_bp,
    init_misc_bp,
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
app.wsgi_app = ProxyFix(app.wsgi_app, x_for=1, x_host=1)
csrf = CSRFProtect(app)
app.config["WTF_CSRF_TIME_LIMIT"] = None

log = logging.getLogger(__name__)

limiter = Limiter(
    key_func=get_remote_address,
    default_limits=[],
    storage_uri="redis://localhost:6379",
)
limiter.init_app(app)

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
            or "progress" in request_parts[0]
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
        route.split("/reset_password/")[0] + "/reset_password/..."
        if "/reset_password/" in route
        else route
    )

    if response.status_code < 400:
        redis_client.hincrby(
            f"stats:monthly:{month}", request.method + " " + route, 1
        )

    key = f"stats:daily:{today}:{user_id}:{response.status}"
    redis_client.hincrby(key, request.method + " " + route, 1)
    if not redis_client.exists(key):
        redis_client.expire(key, 2592000)
    return response


@login_manager.user_loader
def load_user(user_id):
    if user_id in users:
        return User(user_id)
    return None


# Register blueprints
app.register_blueprint(auth_bp)
app.register_blueprint(admin_bp)
app.register_blueprint(movies_bp)
app.register_blueprint(memes_bp)
app.register_blueprint(music_bp)
app.register_blueprint(misc_bp)

# Initialize blueprints with app context
init_auth_bp(users, User, send_mail)
init_admin_bp(users)
init_misc_bp(users, send_mail)


# Apply rate limiting after blueprint registration
@app.before_request
def apply_limiter():
    if request.endpoint:
        if request.endpoint == "auth.login":
            limiter.limit(
                "150 per 15 minutes",
                key_func=lambda: "login:" + get_remote_address(),
            )(lambda: None)()
        elif request.endpoint == "auth.forgot_password":
            limiter.limit(
                "150 per 15 minutes",
                key_func=lambda: "forgot:" + get_remote_address(),
            )(lambda: None)()
        elif request.endpoint == "auth.reset_password":
            limiter.limit(
                "150 per 15 minutes",
                key_func=lambda: "reset:" + get_remote_address(),
            )(lambda: None)()
        elif request.endpoint == "misc.pod_krinko.new_words":
            limiter.limit(
                "150 per 15 minutes",
                key_func=lambda: "pod_krinko:" + get_remote_address(),
            )(lambda: None)()


if __name__ == "__main__":
    log.info("Started server")
    try:
        serve(app, host="0.0.0.0", port=5000, threads=8)
    except OSError:
        app.run(host="0.0.0.0", port=5050)

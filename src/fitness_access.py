"""One cached fitness decision per admin; no journal reads on cache hits."""

import sqlite3
from threading import RLock
from time import monotonic
from urllib.parse import unquote
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from flask import (
    current_app,
    flash,
    g,
    jsonify,
    redirect,
    request,
    session,
    url_for,
)
from flask_login import current_user

import fitness
from fitness import DEFAULT_DATABASE, database, read_state

CACHE_SECONDS = 15 * 60
ESSENTIAL_ENDPOINTS = frozenset(
    {
        "static",
        "csrf_token",
        "auth.login",
        "auth.logout",
        "auth.welcome",
        "auth.forgot_password",
        "auth.reset_password",
        "auth.change_password",
        "admin.clear_view_as",
    }
)
NIGHT_WARNING = (
    "Nočni počitek: filmi, glasba in druge razvedrilne vsebine so med "
    "00:00 in 06:00 po uri tvoje naprave zaklenjene. "
    "Gibanje in blog ostaneta dostopna."
)


def device_night_locked():
    """The browser supplies its zone; its clock handles the first visit."""
    name = request.cookies.get("marinkino_device_timezone", "")
    if not name or len(name) > 100:
        return False
    try:
        local = fitness.now_local().astimezone(ZoneInfo(unquote(name)))
    except (ZoneInfoNotFoundError, ValueError):
        return False
    return local.hour < 6


class AccessCache:
    def __init__(self):
        self.lock = RLock()
        self.entries = {}

    def remember(self, user_id, progress):
        with self.lock:
            self.entries[user_id] = (
                monotonic() + CACHE_SECONDS,
                fitness.now_local().date(),
                progress,
            )

    def invalidate(self, user_id):
        with self.lock:
            self.entries.pop(user_id, None)

    def get(self, user_id):
        with self.lock:
            cached = self.entries.get(user_id)
            now = monotonic()
            if (
                cached
                and cached[0] > now
                and cached[1] == fitness.now_local().date()
            ):
                return cached[2]
            path = current_app.config.get("FITNESS_DATABASE", DEFAULT_DATABASE)
            with database(path) as connection:
                state = read_state(connection, user_id)
            progress = {
                **state["plan_progress"],
                "weighing_status": state["weighing_status"],
            }
            if progress["weighing_status"]["locked"]:
                progress["allowed"] = False
            self.remember(user_id, progress)
            return progress


def access_cache():
    cache = current_app.extensions.get("fitness_access")
    if cache is None:
        cache = current_app.extensions["fitness_access"] = AccessCache()
    return cache


def remember_progress(progress, weighing):
    access = {
        **progress,
        "weighing_status": fitness.weighing_status(weighing),
    }
    if access["weighing_status"]["locked"]:
        access["allowed"] = False
    access_cache().remember(current_user.get_id(), access)
    g.fitness_access = access


def init_fitness_access(app):
    app.extensions["fitness_access"] = AccessCache()

    @app.before_request
    def require_planned_activity():
        if (
            not current_user.is_authenticated
            or not current_user.is_admin
            or request.endpoint in ESSENTIAL_ENDPOINTS
            or request.blueprint == "fitness"
        ):
            return None
        blog = request.blueprint == "blog" or (
            request.blueprint == "admin"
            and (
                request.path == "/admin/blog"
                or request.path.startswith("/admin/blog/")
            )
        )
        night = not blog and device_night_locked()
        progress = None
        if not night:
            try:
                progress = access_cache().get(current_user.get_id())
            except (sqlite3.Error, OSError):
                current_app.logger.exception(
                    "Fitness access check unavailable"
                )
                return jsonify(
                    error="Preverjanje gibanja ni uspelo. Odpri Gibanje.",
                    fitness_url=url_for("fitness.panel"),
                ), 503
            g.fitness_access = progress
            weighing_locked = progress["weighing_status"]["locked"]
            if progress["allowed"] and not weighing_locked:
                return None
        # View-as must not bypass the condition or trap the owner in redirects.
        session.pop("view_as", None)
        fitness_url = url_for("fitness.panel")
        if (
            request.method not in ("GET", "HEAD")
            or request.is_json
            or request.headers.get("X-Requested-With") == "XMLHttpRequest"
            or request.accept_mimetypes.best == "application/json"
        ):
            response = jsonify(
                error=NIGHT_WARNING
                if night
                else (
                    "Od zadnjega tehtanja sta minila več kot dva meseca. "
                    "Zabeleži novo meritev teže za odklep ostalih vsebin."
                    if weighing_locked
                    else "Ta teden najprej opravi vsaj eno aktivnost iz plana."
                ),
                fitness_url=fitness_url,
                progress=progress,
            )
            response.status_code = 423
        else:
            warning = (
                NIGHT_WARNING
                if night
                else (
                    "Ostale vsebine so zaklenjene. "
                    "Zabeleži novo meritev teže; od zadnjega tehtanja sta "
                    "minila več kot dva meseca."
                    if weighing_locked
                    else (
                        "Ostale vsebine so zaklenjene. Ta teden najprej "
                        "opravi vsaj eno aktivnost iz plana in zabeleži "
                        "izvedbo."
                    )
                )
            )
            if request.method == "GET" and (
                "warning",
                warning,
            ) not in session.get("_flashes", []):
                flash(warning, "warning")
            response = redirect(fitness_url)
        response.headers["Cache-Control"] = "private, no-store"
        return response

    @app.context_processor
    def fitness_context():
        return {"fitness_access": g.get("fitness_access")}

"""Admin-only personal fitness journal endpoints."""

import json
import sqlite3
from datetime import date

from flask import (
    Blueprint,
    abort,
    current_app,
    flash,
    jsonify,
    redirect,
    render_template,
    request,
    session,
    url_for,
)
from flask_login import current_user, login_required

from fitness import (
    COLLECTIONS,
    DEFAULT_DATABASE,
    ValidationError,
    calendar_date,
    database,
    get_entry,
    insert,
    now_local,
    read_state,
    sync_schedule,
    update,
    validate,
    validate_profile,
    week_start,
)
from fitness_access import NIGHT_WARNING, access_cache, remember_progress
from utils import is_current_admin_view

fitness_bp = Blueprint("fitness", __name__, url_prefix="/admin/fitness")


@fitness_bp.before_request
def require_admin():
    if not current_user.is_authenticated:
        if request.path.rstrip("/") == "/admin/fitness":
            return None
        abort(401)
    if request.endpoint == "fitness.night_lock" and current_user.is_admin:
        return None
    if not is_current_admin_view(current_user):
        if request.path.rstrip("/") == "/admin/fitness":
            return redirect(url_for("home"))
        abort(403)


@fitness_bp.after_request
def private_response(response):
    response.headers["Cache-Control"] = "private, no-store"
    response.headers["X-Robots-Tag"] = "noindex, nofollow"
    if (
        request.method in ("POST", "PUT", "DELETE")
        and response.status_code < 400
    ):
        access_cache().invalidate(current_user.get_id())
    return response


@fitness_bp.errorhandler(ValidationError)
def invalid_input(error):
    return jsonify(error=str(error)), 400


@fitness_bp.errorhandler(sqlite3.Error)
@fitness_bp.errorhandler(OSError)
def storage_error(error):
    current_app.logger.exception("Fitness storage unavailable")
    return jsonify(error="Podatkov ni mogoče shraniti. Poskusi znova."), 503


def storage():
    return database(
        current_app.config.get("FITNESS_DATABASE", DEFAULT_DATABASE)
    )


def body():
    data = request.get_json(silent=True)
    if not isinstance(data, dict):
        raise ValidationError("Pričakovan je zapis JSON s podatki.")
    return data


@fitness_bp.get("")
@login_required
def panel():
    with storage() as connection:
        state = read_state(connection, current_user.get_id())
    remember_progress(state["plan_progress"])
    return render_template(
        "admin_fitness.html", pagetitle="Gibanje · MarinKino", fitness=state
    )


@fitness_bp.get("/night-lock")
def night_lock():
    session.pop("view_as", None)
    if ("warning", NIGHT_WARNING) not in session.get("_flashes", []):
        flash(NIGHT_WARNING, "warning")
    return redirect(url_for("fitness.panel"))


@fitness_bp.get("/data")
def data():
    start = request.args.get("start")
    start = (
        week_start(date.fromisoformat(calendar_date(start))) if start else None
    )
    with storage() as connection:
        state = read_state(connection, current_user.get_id(), start)
    remember_progress(state["plan_progress"])
    return jsonify(state)


@fitness_bp.put("/profile")
def profile():
    payload = validate_profile(body())
    with storage() as connection:
        user_id = current_user.get_id()
        read_state(connection, user_id)
        connection.execute(
            "UPDATE fitness_profiles SET payload = ? WHERE user_id = ?",
            (json.dumps(payload), user_id),
        )
    return jsonify(profile=payload)


@fitness_bp.post("/<collection>")
def create(collection):
    if collection not in COLLECTIONS:
        abort(404)
    payload = validate(collection, body())
    if collection == "schedule":
        payload["starts_on"] = week_start(now_local().date()).isoformat()
    with storage() as connection:
        entry = insert(connection, current_user.get_id(), collection, payload)
    return jsonify(entry=entry), 201


@fitness_bp.route("/<collection>/<entry_id>", methods=["PUT", "DELETE"])
def edit(collection, entry_id):
    if collection not in COLLECTIONS:
        abort(404)
    payload = validate(collection, body()) if request.method == "PUT" else None
    with storage() as connection:
        user_id = current_user.get_id()
        original = get_entry(connection, user_id, collection, entry_id)
        if original is None or original.get("cancelled"):
            abort(404)
        if request.method == "DELETE":
            if collection == "schedule":
                sync_schedule(connection, user_id, entry_id)
            if collection == "activities" and original.get("plan_id"):
                plan_id = original["plan_id"]
                plan = get_entry(connection, user_id, "plan", plan_id)
                if plan and plan.get("activity_id") == entry_id:
                    plan.pop("activity_id", None)
                    plan["status"] = "planned"
                    update(connection, user_id, "plan", plan_id, plan)
            if collection == "plan" and original.get("schedule_id"):
                # Keep a tombstone so refreshing does not recreate this day.
                original["cancelled"] = True
                update(connection, user_id, collection, entry_id, original)
            else:
                connection.execute(
                    "DELETE FROM fitness_entries WHERE id = ? AND user_id = ?",
                    (entry_id, user_id),
                )
        else:
            if collection == "activities" and original.get("plan_id"):
                payload["plan_id"] = original["plan_id"]
            if collection == "plan" and original.get("activity_id"):
                payload.update(
                    status="completed", activity_id=original["activity_id"]
                )
            if collection == "plan" and original.get("schedule_id"):
                payload.update(
                    schedule_id=original["schedule_id"],
                    scheduled_date=original["scheduled_date"],
                    customized=True,
                )
            if collection == "schedule":
                payload["starts_on"] = original["starts_on"]
                sync_schedule(connection, user_id, entry_id, payload)
            update(connection, user_id, collection, entry_id, payload)
    return jsonify(entry={**payload, "id": entry_id}) if payload else ("", 204)


@fitness_bp.post("/plan/<entry_id>/complete")
def complete(entry_id):
    overrides = body()
    with storage() as connection:
        user_id = current_user.get_id()
        plan = get_entry(connection, user_id, "plan", entry_id)
        if plan is None or plan.get("cancelled"):
            abort(404)
        if plan.get("activity_id"):
            return jsonify(activity_id=plan["activity_id"])
        actual = {**plan, **overrides}
        if "duration_seconds" not in overrides and (
            "duration_min" in overrides or "elapsed_time" in overrides
        ):
            actual.pop("duration_seconds", None)
        payload = validate("activities", actual)
        payload["plan_id"] = entry_id
        activity = insert(connection, user_id, "activities", payload)
        plan.update(status="completed", activity_id=activity["id"])
        update(connection, user_id, "plan", entry_id, plan)
    return jsonify(activity_id=activity["id"]), 201

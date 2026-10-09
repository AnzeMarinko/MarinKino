import logging
import os
import random
from datetime import date
from urllib.parse import quote

from flask import (
    Blueprint,
    abort,
    flash,
    jsonify,
    make_response,
    render_template,
    request,
    send_from_directory,
    url_for,
)
from flask_login import current_user, login_required

from utils import (
    FLASK_ENV,
    get_guest_identity,
    is_current_admin_view,
    redis_client,
    safe_path,
)

log = logging.getLogger(__name__)

memes_bp = Blueprint("memes", __name__)

# Global variables
meme_id = None
user_meme_count = {}
user_meme_limit = 12

MEMES_DIR = "data/memes"


def available_memes():
    """Read current files so additions and deletions work across workers."""
    try:
        return sorted(
            filename
            for filename in os.listdir(MEMES_DIR)
            if filename.lower().endswith(
                (".png", ".jpg", ".jpeg", ".gif", ".webp", ".mp4")
            )
            and os.path.isfile(os.path.join(MEMES_DIR, filename))
        )
    except OSError:
        log.warning("Meme directory unavailable", exc_info=True)
        return []


@memes_bp.route("/memes")
def meme():
    global meme_id
    global user_meme_count
    is_admin = current_user.is_authenticated and current_user.is_admin
    wants_json = request.args.get("format") == "json"
    files = available_memes()
    if not files:
        payload = {
            "empty": True,
            "meme_file_name": None,
            "can_delete": is_current_admin_view(current_user),
            "remaining": None,
            "total": 0,
        }
        if wants_json:
            return jsonify(payload)
        return render_template(
            "memes.html",
            pagetitle="Šale in navdih",
            meme_data=payload,
        )
    identity = (
        current_user.id
        if current_user.is_authenticated
        else get_guest_identity()
    )
    user_meme_count[identity] = user_meme_count.get(identity, {})
    if user_meme_count[identity].get("last_date") != str(date.today()):
        user_meme_count[identity]["last_date"] = str(date.today())
        user_meme_count[identity]["count"] = 0
    if (
        user_meme_count[identity]["count"] >= user_meme_limit and not is_admin
    ) or user_meme_count[identity]["count"] >= 3000:
        if wants_json:
            return jsonify(
                {
                    "error": "limit_reached",
                    "message": (
                        "Dnevna omejitev šal je dosežena. "
                        "Nove šale te čakajo jutri."
                    ),
                }
            ), 429
        return render_template(
            "limit_exceeded.html",
            section="šal",
            pagetitle="Dovolj šal za danes v MarinKino",
        )
    user_meme_count[identity]["count"] += 1
    if is_admin:
        meme_id = (redis_client.incr("memes:explore") - 1) % len(files)
        previous = request.args.get("previous")
        if len(files) > 1 and files[meme_id] == previous:
            meme_id = (meme_id + 1) % len(files)
        izbrana = files[meme_id]
        log.info("Admin selected meme: %s (ID: %d)", izbrana, meme_id)
        if meme_id % 10 == 0:
            log.info(user_meme_count)
    else:
        choices = [
            name for name in files if name != request.args.get("previous")
        ] or files
        izbrana = random.choice(choices)
    payload = {
        "empty": False,
        "meme_file_name": izbrana,
        "media_url": url_for("memes.meme_file", meme_file_name=izbrana),
        "delete_url": url_for("memes.meme_remove", meme_file_name=izbrana),
        "is_video": izbrana.lower().endswith(".mp4"),
        "can_delete": is_current_admin_view(current_user),
        "remaining": None
        if is_admin
        else max(0, user_meme_limit - user_meme_count[identity]["count"]),
        "total": len(files),
    }
    if wants_json:
        response = jsonify(payload)
        response.headers["Cache-Control"] = "no-store"
        return response
    return render_template(
        "memes.html",
        pagetitle="Šale in navdih",
        meme_data=payload,
        meme_file_name=izbrana,
    )


@memes_bp.route("/memes/file/<meme_file_name>")
def meme_file(meme_file_name):
    try:
        path = safe_path(MEMES_DIR, meme_file_name)
        if not os.path.isfile(path):
            abort(404)
    except ValueError:
        abort(404)
    if FLASK_ENV == "production":
        response = make_response()
        safe_filename = quote(meme_file_name, safe="/")
        if not safe_filename.startswith("/"):
            safe_filename = "/" + safe_filename
        response.headers["X-Accel-Redirect"] = (
            f"/protected_memes{safe_filename}"
        )

        lower_name = meme_file_name.lower()
        if lower_name.endswith(".mp4"):
            response.headers["Content-Type"] = "video/mp4"
        elif lower_name.endswith(".jpg") or lower_name.endswith(".jpeg"):
            response.headers["Content-Type"] = "image/jpeg"
        elif lower_name.endswith(".png"):
            response.headers["Content-Type"] = "image/png"
        elif lower_name.endswith(".gif"):
            response.headers["Content-Type"] = "image/gif"
        elif lower_name.endswith(".webp"):
            response.headers["Content-Type"] = "image/webp"
    else:
        mimetype = None
        lower_name = meme_file_name.lower()
        if lower_name.endswith(".mp4"):
            mimetype = "video/mp4"
        elif lower_name.endswith(".jpg") or lower_name.endswith(".jpeg"):
            mimetype = "image/jpeg"
        elif lower_name.endswith(".png"):
            mimetype = "image/png"
        elif lower_name.endswith(".gif"):
            mimetype = "image/gif"
        elif lower_name.endswith(".webp"):
            mimetype = "image/webp"

        response = send_from_directory(
            os.path.abspath(MEMES_DIR),
            meme_file_name,
            mimetype=mimetype,
            conditional=True,
        )
        response.headers["Accept-Ranges"] = "bytes"
    return response


@memes_bp.route("/memes/delete/<meme_file_name>", methods=["DELETE"])
@login_required
def meme_remove(meme_file_name):
    if not is_current_admin_view(current_user):
        return jsonify({"error": "forbidden"}), 403
    try:
        path = safe_path(MEMES_DIR, meme_file_name)
    except ValueError:
        log.warning("Invalid meme file path: %s", meme_file_name)
        flash("Invalid meme file path.", "error")
        return "", 404
    if not os.path.exists(path):
        log.warning("Meme file does not exist: %s", path)
        flash("Meme file does not exist.", "error")
        return "", 404
    os.remove(path)
    flash("Meme file removed successfully.", "success")
    log.info("Meme file removed: %s", path)
    return "", 204

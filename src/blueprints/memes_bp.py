import logging
import os
import random
from datetime import date
from urllib.parse import quote

from flask import Blueprint, abort, make_response, render_template, send_from_directory
from flask_login import current_user, login_required

from utils import FLASK_ENV, is_current_admin_view, safe_path

log = logging.getLogger(__name__)

memes_bp = Blueprint("memes", __name__)

# Global variables
meme_id = 0
user_meme_count = {}
user_meme_limit = 33

# Initialize memes
memes = os.listdir("data/memes")
memes = [
    slika
    for slika in memes
    if slika.lower().endswith((".png", ".jpg", ".jpeg", ".gif", ".webp", ".mp4"))
]
random.shuffle(memes)


@memes_bp.route("/memes")
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
        return render_template(
            "limit_exceeded.html",
            section="šal",
            pagetitle="Dovolj za danes v MarinKino",
        )

    izbrana = memes[meme_id]
    meme_id = (meme_id + 1) % len(memes)
    return render_template(
        "memes.html",
        pagetitle="MarinKino - Šale in navdihi",
        fullscreenbutton=True,
        meme_file_name=izbrana,
    )


@memes_bp.route("/memes/file/<meme_file_name>")
@login_required
def meme_file(meme_file_name):
    try:
        path = safe_path("../data/memes", meme_file_name)
        if not os.path.exists(os.path.join("data/memes", meme_file_name)):
            abort(404)
    except ValueError:
        abort(404)
    if FLASK_ENV == "production":
        response = make_response()
        safe_filename = quote(meme_file_name, safe="/")
        if not safe_filename.startswith("/"):
            safe_filename = "/" + safe_filename
        response.headers["X-Accel-Redirect"] = f"/protected_memes{safe_filename}"

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
            "../data/memes", meme_file_name, mimetype=mimetype, conditional=True
        )
        response.headers["Accept-Ranges"] = "bytes"
    return response


@memes_bp.route("/memes/delete/<meme_file_name>", methods=["DELETE"])
@login_required
def meme_remove(meme_file_name):
    if not is_current_admin_view(current_user):
        return "", 204
    try:
        path = safe_path("data/memes", meme_file_name)
    except ValueError:
        return "", 404
    if not os.path.exists(path):
        return "", 404
    os.remove(path)
    return "", 204

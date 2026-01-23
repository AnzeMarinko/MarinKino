import logging
import os
import random
from datetime import date

from flask import Blueprint, render_template, send_from_directory
from flask_login import current_user, login_required

from utils import safe_path

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
    if slika.lower().endswith(
        (".png", ".jpg", ".jpeg", ".gif", ".webp", "mp4")
    )
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
    except ValueError:
        return "", 404
    if path.endswith(".mp4"):
        return send_from_directory(
            "../data/memes",
            meme_file_name,
            mimetype="video/mp4",
            conditional=True,
        )
    return send_from_directory(
        "../data/memes", meme_file_name, conditional=True
    )


@memes_bp.route("/meme/delete/<meme_file_name>", methods=["DELETE"])
@login_required
def meme_remove(meme_file_name):
    if not current_user.is_admin:
        return "", 204
    try:
        path = safe_path("../data/memes", meme_file_name)
    except ValueError:
        return "", 404
    if not os.path.exists(path):
        return "", 404
    os.remove(path)
    return "", 204

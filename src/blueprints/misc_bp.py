import json
import logging
import os
from copy import copy
from datetime import date, datetime

import pandas as pd
from flask import (
    Blueprint,
    redirect,
    render_template,
    request,
    send_from_directory,
    url_for,
)
from flask_login import current_user, login_required

from utils import is_current_admin_view, redis_client, safe_path

log = logging.getLogger(__name__)

misc_bp = Blueprint("misc", __name__)
DUCKDNS_DOMAIN = os.getenv("DUCKDNS_DOMAIN")

# Global variables
users = {}
send_mail = None


def init_misc_bp(_users, _send_mail=None):
    """Initialize blueprint with app context"""
    global users, send_mail
    users = _users
    send_mail = _send_mail


@misc_bp.route("/favicon.ico")
def favicon():
    return send_from_directory("static", "logo.png")


@misc_bp.route("/pod_krinko")
def pod_krinko():
    return render_template(
        "pod_krinko.html",
        pagetitle="Pod krinko",
    )


# Initialize pod_krinko
pod_krinko_words = pd.read_csv("data/pod_krinko_besede.csv", sep=";").to_dict(
    orient="split"
)["data"]


@misc_bp.route("/pod_krinko/new_words")
def pod_krinko_new_words():
    import random

    new_words = copy(pod_krinko_words[random.randint(0, len(pod_krinko_words) - 1)])
    random.shuffle(new_words)
    word_1, word_2 = new_words[0], new_words[1]
    return [word_1.strip().lower(), word_2.strip().lower()]


@misc_bp.route("/newsletter_image/file/<path:filename>")
def newsletter_image(filename):
    try:
        path = safe_path("../data/newsletter_images", filename)
    except ValueError:
        return "", 404
    user = (
        current_user.id
        if current_user.is_authenticated
        else request.args.get("user", "guest")
    )
    if user in users:
        redis_client.incr(f"newsletter_views:{date.today().isoformat()[:7]}:{user}")
    return send_from_directory("../data/newsletter_images", filename, conditional=True)


@misc_bp.route("/help")
@login_required
def help():
    return render_template(
        "mail_user_intro.html",
        is_for_mail=False,
        username=current_user.id if current_user.is_authenticated else "gost",
        pagetitle="Navodila za uporabo MarinKino",
    )


@misc_bp.route("/send_admin_emails", methods=["GET", "POST"])
@login_required
def send_admin_emails():
    template_name = "mail_newsletters/mail_monthly_recommendation"
    if not is_current_admin_view(current_user):
        return redirect(url_for("movies.index"))
    if request.method == "POST":
        if send_mail is None:
            log.error("send_mail function not initialized")
            return {"error": "Mail function not initialized"}

        data = json.loads(request.data)
        whole_list = data.get("whole_list") == "true"
        list_of_emailed_users = (
            [current_user.id] if not whole_list else list(users.keys())
        )
        for username in list_of_emailed_users:
            emails = users.get(username, {}).get("emails", [])
            if emails:
                # TODO: ob pošiljanju mailov spreminjaj ta klic funkcije
                # if whole_list:
                #     return {"error": "Pošiljanje mailov vsem uporabnikom je začasno onemogočeno."}
                send_mail(
                    to=emails,
                    subject="Filmski izbor MarinKino",
                    text=f"https://{DUCKDNS_DOMAIN}/last_mail_newsletter",
                    html=render_template(
                        template_name + ".html",
                        username=username,
                        is_for_mail=True,
                    ),
                    batch_id="mail_newsletter",
                )
        return {
            "sent": len(list_of_emailed_users),
            "emails": list_of_emailed_users,
            "time": datetime.now().isoformat(),
        }
    return render_template(
        "admin_mailing.html",
        pagetitle=f"Pošiljanje {template_name} mailov uporabnikom MarinKino",
    )


last_mail_newsletter_data = {
    "film_recommendations": [
        {
            "title": "Vrvež v moji glavi",
            "path": "02-animirani-filmi/Inside.Out.2015.SloSinh",
            "genres": ["Komedija", "Družinski"],
            "duration": "1h 45min",
            "short_description": "kratek opis",
            "cover_filename": "Inside.Out-cover.jpg",
        }
    ],
    "meme_file": "2026_januar/meme.jpg",
    "template": "mail_newsletters/mail_monthly_recommendation.html",
    "pagetitle": "Filmski izbor MarinKino",
    "mailtitle": "Februarski filmski izbor",
}


@misc_bp.route("/last_mail_newsletter")
@login_required
def last_mail_newsletter():
    return render_template(
        last_mail_newsletter_data["template"],
        is_for_mail=False,
        username=current_user.id,
        pagetitle=last_mail_newsletter_data["pagetitle"],
        mailtitle=last_mail_newsletter_data["mailtitle"],
        film_recommendations=last_mail_newsletter_data["film_recommendations"],
        meme_file=last_mail_newsletter_data["meme_file"],
    )


@misc_bp.route("/suggestions", methods=["GET"])
@login_required
def suggestions():
    """Stran za splošne predloge in komentarje"""
    return render_template(
        "suggestions.html",
        pagetitle="Predlogi in komentarji",
    )

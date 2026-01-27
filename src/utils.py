import json
import logging
import os
import pathlib
import random
import smtplib
import ssl
from datetime import date
from email.message import EmailMessage

import redis
from flask import session
from flask_login import UserMixin
from werkzeug.security import generate_password_hash

log = logging.getLogger(__name__)
redis_client = redis.Redis(
    host=os.getenv("REDIS_HOST", "localhost"),
    port=int(os.getenv("REDIS_PORT", "6379")),
    decode_responses=True,
)


def safe_path(base_folder, filename):
    path = pathlib.Path(base_folder) / filename
    path = path.resolve()
    if not str(path).startswith(str(pathlib.Path(base_folder).resolve())):
        raise ValueError("Nevaren path")
    return str(path)


FLASK_ENV = os.getenv("FLASK_ENV", "development")

# Load users
users_file = (
    "data/users.json" if FLASK_ENV == "production" else "data/test_users.json"
)
if not os.path.exists(users_file):
    # make admin user
    password = "".join(
        random.choices(
            "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789.-+_!=?<>",
            k=12,
        )
    )
    users = {
        "admin": {
            "is_admin": True,
            "initial_password": password,
            "password_hash": generate_password_hash(password),
            "emails": [os.getenv("GMAIL_USERNAME")],
            "incoming_date": date.today().isoformat(),
        }
    }
    with open(users_file, "w", encoding="utf-8") as f:
        f.write(json.dumps(users, indent=4))
with open(users_file, "r", encoding="utf-8") as f:
    users = json.loads(f.read())


class User(UserMixin):
    def __init__(self, username):
        self.id = username
        self.is_admin = users.get(username, {}).get("is_admin", False)
        self.emails = users.get(username, {}).get("emails", [])


def is_current_admin_view(user):
    return (
        user.is_admin
        and session.get("view_as", None) != "anonymous"
        and session.get("view_as", None) != "user"
    )


def find_user_by_email(email, users_dict):
    if not email:
        return None
    for username, data in users_dict.items():
        for aux_email in data.get("emails", []):
            if aux_email.lower() == email.lower():
                return username
    return None


def send_mail(
    to, cc=None, bcc=None, subject="", text="", html="", batch_id=""
):
    """Send email using Gmail SMTP"""
    msg = EmailMessage()

    msg["From"] = f"MarinKino <{os.getenv('MAIL_USERNAME')}>"
    msg["To"] = ", ".join(to) if isinstance(to, list) else to

    if cc:
        msg["Cc"] = ", ".join(cc)
    if bcc:
        msg["Bcc"] = ", ".join(bcc)

    msg["Subject"] = subject

    msg.set_content(text)

    if html:
        msg.add_alternative(html, subtype="html")

    recipients = []
    for field in (to, cc, bcc):
        if field:
            recipients += field if isinstance(field, list) else [field]

    base = f"mail:{date.today().isoformat()[:7]}:{batch_id}"
    redis_client.sadd(f"{base}:recipients", *recipients)
    context = ssl.create_default_context()

    try:
        with smtplib.SMTP("smtp.gmail.com", 587, timeout=15) as server:
            server.starttls(context=context)
            server.login(os.getenv("GMAIL_USERNAME"), os.getenv("GMAIL_TOKEN"))

            failed = server.send_message(msg, to_addrs=recipients)

            for email in recipients:
                if email in (failed or {}):
                    code, reason = failed[email]
                    redis_client.hset(
                        f"{base}:errors",
                        find_user_by_email(email, users) or email,
                        f"{code} {reason}",
                    )

    except smtplib.SMTPException as e:
        redis_client.hset(
            f"{base}:errors",
            f"smtp_exception_{date.today().isoformat()}",
            str(e),
        )
        raise

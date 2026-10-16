import logging
import os
import pathlib
import secrets
import smtplib
import ssl
from datetime import date
from email.message import EmailMessage
from typing import List

import redis
from flask import session
from flask_login import UserMixin
from werkzeug.security import generate_password_hash

from blog_subscribers import normalize_subscribers
from security_http import guest_identity
from security_storage import (
    atomic_write_json,
    locked_path,
    read_json,
    safe_resolved_path,
)

log = logging.getLogger(__name__)
redis_client = redis.Redis(
    host=os.getenv("REDIS_HOST", "localhost"),
    port=int(os.getenv("REDIS_PORT", "6379")),
    decode_responses=True,
    socket_connect_timeout=2,
    socket_timeout=2,
    health_check_interval=30,
)


def get_guest_identity() -> str:
    return guest_identity()


SUBSCRIBERS_FILE = os.path.join(
    os.path.dirname(__file__), "..", "data", "blog_subscribers.json"
)


def load_blog_subscribers() -> List[dict[str, str]]:
    return normalize_subscribers(read_json(SUBSCRIBERS_FILE, []))


def save_blog_subscribers(subscribers: List[dict[str, str] | str]):
    atomic_write_json(SUBSCRIBERS_FILE, normalize_subscribers(subscribers))


def safe_path(base_folder, filename):
    return safe_resolved_path(base_folder, filename)


FLASK_ENV = os.getenv("FLASK_ENV", "development")

# Load users
users_file = (
    "data/users.json" if FLASK_ENV == "production" else "data/test_users.json"
)
with locked_path(users_file):
    users = read_json(users_file, None)
    if users is None:
        password = secrets.token_urlsafe(24)
        users = {
            "admin": {
                "is_admin": True,
                "must_change_password": True,
                "password_hash": generate_password_hash(password),
                "emails": [os.getenv("GMAIL_USERNAME")],
                "incoming_date": date.today().isoformat(),
            }
        }
        # One-time local bootstrap credential; never stored in the user JSON.
        bootstrap = pathlib.Path(users_file).with_name(
            ".initial-admin-password"
        )
        descriptor = os.open(
            bootstrap,
            os.O_WRONLY | os.O_CREAT | os.O_TRUNC | os.O_NOFOLLOW,
            0o600,
        )
        with os.fdopen(descriptor, "w") as stream:
            os.fchmod(stream.fileno(), 0o600)
            stream.write(password + "\n")
        atomic_write_json(users_file, users)
    elif any("initial_password" in entry for entry in users.values()):
        for entry in users.values():
            entry.pop("initial_password", None)
        atomic_write_json(users_file, users)


class User(UserMixin):
    def __init__(self, username):
        self.id = username
        self.is_admin = users.get(username, {}).get("is_admin", False)
        self.emails = users.get(username, {}).get("emails", [])
        self.must_change_password = users.get(username, {}).get(
            "must_change_password", False
        )


def is_current_admin_view(user):
    return (
        user.is_authenticated
        and user.is_admin
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
    to,
    cc=None,
    bcc=None,
    subject="",
    text="",
    html="",
    batch_id="",
    blog=False,
):
    """Send email using Gmail SMTP"""
    msg = EmailMessage()

    msg["From"] = (
        f"{'Rože dobrega' if blog else 'MarinKino'}"
        f" <{os.getenv('MAIL_SENDER')}>"
    )
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

    return failed or {}

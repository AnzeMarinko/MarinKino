"""Persist outgoing mail before returning HTTP responses."""

import smtplib
from datetime import datetime, timezone

from flask import current_app
from flask_login import current_user

from background_jobs import DeliveryUncertain
from security_storage import atomic_write_json, locked_path, read_json


def queue_mail(**message):
    return current_app.extensions["jobs"].enqueue(
        "mail", {"message": message}, owner=current_user.get_id() or ""
    )


def _deliver(message):
    from utils import send_mail

    try:
        rejected = send_mail(**message)
    except (smtplib.SMTPRecipientsRefused, smtplib.SMTPAuthenticationError):
        # Both inherit OSError, but SMTP explicitly rejected this attempt.
        raise
    except (smtplib.SMTPServerDisconnected, OSError) as error:
        raise DeliveryUncertain("SMTP delivery was interrupted") from error
    if not rejected:
        return
    recipients = set()
    for name in ("to", "cc", "bcc"):
        value = message.get(name)
        if value:
            recipients.update(value if isinstance(value, list) else [value])
    if recipients - set(rejected):
        raise DeliveryUncertain("SMTP accepted only some recipients")
    if rejected:
        raise RuntimeError("Some mail recipients rejected delivery")


def deliver_mail_job(job):
    _deliver(job["payload"]["message"])


def deliver_blog_mail_job(job):
    payload = job["payload"]
    path, post_id = payload["posts_path"], payload["post_id"]
    for language, recipients, subject, html, text in payload["deliveries"]:
        post = read_json(path, {}).get(post_id)
        if not post or not post.get("published"):
            raise RuntimeError("Publication is no longer available")
        if language in post.get("mail_languages_sent", []):
            continue
        _deliver(
            {
                "to": payload["sender_recipient"],
                "bcc": recipients,
                "subject": subject,
                "html": html,
                "text": text,
                "batch_id": post_id,
                "blog": True,
            }
        )
        # Never hold a content lock during SMTP. Preserve concurrent edits.
        try:
            with locked_path(path):
                posts = read_json(path, {})
                if post_id not in posts:
                    raise DeliveryUncertain(
                        "Publication was removed after delivery"
                    )
                sent = set(posts[post_id].get("mail_languages_sent", []))
                sent.add(language)
                posts[post_id]["mail_languages_sent"] = sorted(sent)
                atomic_write_json(path, posts)
        except (OSError, ValueError) as error:
            # Retry cannot identify this successfully delivered batch.
            raise DeliveryUncertain(
                "Could not record completed delivery"
            ) from error
    with locked_path(path):
        posts = read_json(path, {})
        if post_id in posts:
            posts[post_id]["mail_date"] = datetime.now(
                timezone.utc
            ).isoformat()
            atomic_write_json(path, posts)

import hashlib
import json
import logging
import os
import secrets
from datetime import datetime, timezone
from typing import cast
from urllib.parse import quote

import markdown
import requests
from flask import (
    Blueprint,
    abort,
    flash,
    make_response,
    redirect,
    render_template,
    request,
    send_from_directory,
    url_for,
)
from flask_login import current_user

from utils import (
    FLASK_ENV,
    load_blog_subscribers,
    redis_client,
    safe_path,
    save_blog_subscribers,
    send_mail,
    users,
)

log = logging.getLogger(__name__)

blog_bp = Blueprint("blog", __name__)

BLOG_DATA_FILE = os.path.join(
    os.path.dirname(__file__), "..", "..", "data", "blog_posts.json"
)
SUBSCRIPTION_TOKEN_TTL = 24 * 60 * 60
SUBSCRIPTION_IP_LIMIT = 5
SUBSCRIPTION_EMAIL_LIMIT = 3
SUBSCRIPTION_LIMIT_TTL = 60 * 60
TURNSTILE_VERIFY_URL = (
    "https://challenges.cloudflare.com/turnstile/v0/siteverify"
)


def masked_email(email):
    local, _, domain = email.partition("@")
    return f"{local[:1]}***@{domain}" if domain else "<invalid>"


def load_blog_posts():
    if os.path.exists(BLOG_DATA_FILE):
        with open(BLOG_DATA_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    return {}


def save_blog_posts(posts):
    os.makedirs(os.path.dirname(BLOG_DATA_FILE), exist_ok=True)
    with open(BLOG_DATA_FILE, "w", encoding="utf-8") as f:
        json.dump(posts, f, ensure_ascii=False, indent=2)


def blog_timestamp(blog):
    timestamp = (
        blog.get("published_at") or blog.get("created_at", "")
    ).replace("Z", "+00:00")
    try:
        return datetime.fromisoformat(timestamp)
    except Exception:
        return datetime.now(timezone.utc)


@blog_bp.route("/blog")
def blog_list():
    posts = load_blog_posts()
    # Filter published posts for non-admin users
    if not (current_user.is_authenticated and current_user.is_admin):
        posts = {k: v for k, v in posts.items() if v.get("published", False)}
    # Sort by date descending
    sorted_posts = sorted(posts.values(), key=blog_timestamp, reverse=True)

    # Format dates
    for post in sorted_posts:
        post["created_at_display"] = blog_timestamp(post).strftime(
            "%d. %m. %Y"
        )

    return render_template(
        "blog_list.html",
        posts=sorted_posts,
        pagetitle="Sončnice",
        blog_view="blog",
        turnstile_site_key=os.getenv("TURNSTILE_SITE_KEY"),
    )


@blog_bp.route("/blog/pogoji-uporabe")
def blog_terms():
    return render_template(
        "blog_legal.html",
        legal_page="terms",
        pagetitle="Pogoji uporabe",
        blog_view="blog",
    )


@blog_bp.route("/blog/politika-zasebnosti")
def blog_privacy():
    return render_template(
        "blog_legal.html",
        legal_page="privacy",
        pagetitle="Politika zasebnosti",
        blog_view="blog",
    )


def verify_turnstile(token):
    secret = os.getenv("TURNSTILE_SECRET_KEY")
    if not secret:
        verified = FLASK_ENV in {"development", "testing"}
        log.debug("Turnstile: secret_missing verified=%s", verified)
        return verified
    if not token:
        log.debug("Turnstile: token_missing")
        return False

    try:
        response = requests.post(
            TURNSTILE_VERIFY_URL,
            data={
                "secret": secret,
                "response": token,
                "remoteip": request.remote_addr,
            },
            timeout=5,
        )
        result = response.json()
        expected_hostname = os.getenv("TURNSTILE_HOSTNAME")
        verified = (
            response.ok
            and result.get("success", False)
            and result.get("action") == "blog_subscribe"
            and (
                not expected_hostname
                or result.get("hostname") == expected_hostname
            )
        )
        log.debug(
            "Turnstile: http_status=%s success=%s action=%s "
            "hostname=%s verified=%s",
            response.status_code,
            result.get("success", False),
            result.get("action"),
            result.get("hostname"),
            verified,
        )
        return verified
    except (requests.RequestException, ValueError):
        log.exception("Napaka pri preverjanju Cloudflare Turnstile")
        return False


def notify_admins_about_subscriber(email):
    admin_emails = []
    for username, data in users.items():
        if data.get("is_admin"):
            admin_emails += data.get("emails", [])
    if not admin_emails:
        admin_emails = [os.getenv("GMAIL_USERNAME")]
    send_mail(
        to=admin_emails,
        subject=f"Nov potrjen naročnik na blog: {email}",
        text=(
            f"Nov potrjen naročnik na blog: {email}\nStran: {request.host_url}"
        ),
        batch_id="new_subscriber",
    )


def subscription_rate_limited(email):
    client_ip = request.remote_addr or "unknown"
    ip_hash = hashlib.sha256(client_ip.encode()).hexdigest()
    email_hash = hashlib.sha256(email.encode()).hexdigest()
    keys = [
        f"blog:subscribe:ip:{ip_hash}",
        f"blog:subscribe:email:{email_hash}",
    ]
    counts = [redis_client.incr(key) for key in keys]
    for key in keys:
        if counts[keys.index(key)] == 1:
            redis_client.expire(key, SUBSCRIPTION_LIMIT_TTL)
    limited = (
        counts[0] > SUBSCRIPTION_IP_LIMIT
        or counts[1] > SUBSCRIPTION_EMAIL_LIMIT
    )
    log.debug(
        "Subscription rate limit: ip_count=%s email_count=%s limited=%s",
        counts[0],
        counts[1],
        limited,
    )
    return limited


def public_base_url():
    configured_url = os.getenv("PUBLIC_BASE_URL")
    if configured_url:
        return configured_url.rstrip("/")
    domain = os.getenv("WWW_DOMAIN")
    if domain:
        return f"https://{domain}"
    if FLASK_ENV != "production":
        return request.host_url.rstrip("/")
    return None


@blog_bp.route("/blog/subscribe", methods=["POST"])
def blog_subscribe():
    if request.form.get("website"):
        log.debug("Subscription rejected: honeypot_filled")
        return redirect(url_for("blog.blog_list"))

    if request.form.get("terms_accepted") != "yes":
        log.debug("Subscription rejected: terms_not_accepted")
        flash(
            "Za naročnino morate sprejeti pogoje uporabe in politiko zasebnosti.",
            "error",
        )
        return redirect(url_for("blog.blog_list"))

    turnstile_token = request.form.get("cf-turnstile-response")
    log.debug(
        "Subscription received: ip=%s email_present=%s turnstile_present=%s",
        request.remote_addr,
        bool(request.form.get("email")),
        bool(turnstile_token),
    )
    if not verify_turnstile(turnstile_token):
        log.warning("Subscription rejected: turnstile_failed")
        flash("Preverjanje ni uspelo. Poskusite znova.", "error")
        return redirect(url_for("blog.blog_list"))

    raw_email = request.form.get("email")
    email = raw_email.strip().lower() if raw_email else ""
    if (
        not email
        or len(email) > 254
        or email.count("@") != 1
        or any(char.isspace() for char in email)
    ):
        log.debug("Subscription rejected: invalid_email")
        flash("Prosimo vnesite veljaven e-poštni naslov.", "error")
        return redirect(url_for("blog.blog_list"))
    if subscription_rate_limited(email):
        log.warning("Subscription rejected: rate_limited")
        flash("Poskusite znova pozneje.", "error")
        return redirect(url_for("blog.blog_list"))
    subs = load_blog_subscribers()
    spam_domains = ["@immenseignite.info", "@mail.ru"]
    if email in subs or any(domain in email for domain in spam_domains):
        log.debug(
            "Subscription ignored: duplicate_or_blocked email=%s",
            masked_email(email),
        )
        flash(
            "Hvala! Če je naslov primeren, boste prejeli "
            "potrditveno sporočilo.",
            "success",
        )
        return redirect(url_for("blog.blog_list"))

    token = secrets.token_urlsafe(32)
    redis_client.setex(
        f"blog:subscription:pending:{token}",
        SUBSCRIPTION_TOKEN_TTL,
        email,
    )
    log.debug(
        "Subscription pending: email=%s ttl=%s",
        masked_email(email),
        SUBSCRIPTION_TOKEN_TTL,
    )
    base_url = public_base_url()
    if not base_url:
        redis_client.delete(f"blog:subscription:pending:{token}")
        log.error("PUBLIC_BASE_URL or WWW_DOMAIN must be configured")
        flash("Naročnine trenutno ni mogoče obdelati.", "error")
        return redirect(url_for("blog.blog_list"))
    confirmation_url = (
        f"{base_url}{url_for('blog.blog_confirm_subscription', token=token)}"
    )
    try:
        log.debug(
            "Subscription confirmation mail: sending email=%s",
            masked_email(email),
        )
        send_mail(
            to=email,
            subject="Potrdite naročnino na blog Rože dobrega",
            text=(
                "Za potrditev naročnine odprite povezavo:\n"
                f"{confirmation_url}\n\n"
                "Povezava velja 24 ur."
            ),
            html=render_template(
                "mail_blog_subscription_confirmation.html",
                confirmation_url=confirmation_url,
                is_for_mail=True,
            ),
            batch_id="subscriber_confirmation",
            blog=True,
        )
        log.info(
            "Subscription confirmation mail: sent email=%s",
            masked_email(email),
        )
    except Exception:
        redis_client.delete(f"blog:subscription:pending:{token}")
        log.exception("Napaka pri pošiljanju potrditve naročnine")
        flash("Potrditvenega sporočila ni bilo mogoče poslati.", "error")
        return redirect(url_for("blog.blog_list"))

    flash(
        "Preverite e-pošto in potrdite naročnino.",
        "success",
    )
    return redirect(url_for("blog.blog_list"))


@blog_bp.route("/blog/subscribe/confirm/<token>")
def blog_confirm_subscription(token):
    email = cast(
        str | None,
        redis_client.getdel(f"blog:subscription:pending:{token}"),
    )
    if not email:
        log.warning(
            "Subscription confirmation rejected: token_missing_or_expired"
        )
        flash("Potrditvena povezava je neveljavna ali je potekla.", "error")
        return redirect(url_for("blog.blog_list"))

    subs = load_blog_subscribers()
    if email not in subs:
        log.info("Subscription confirmed: email=%s", masked_email(email))
        subs.append(email)
        save_blog_subscribers(subs)
        try:
            notify_admins_about_subscriber(email)
        except Exception:
            log.exception("Napaka pri pošiljanju obvestila o novem naročniku")

    flash("Naročnina je potrjena. Hvala!", "success")
    return redirect(url_for("blog.blog_list"))


@blog_bp.route("/blog/<post_id>")
def blog_post(post_id):
    posts = load_blog_posts()
    post = posts.get(post_id)
    if not post:
        abort(404)

    # Check if published for non-admin users
    if not current_user.is_authenticated and not post.get("published", False):
        abort(404)

    # Render Markdown content
    post["content_html"] = markdown.markdown(
        post.get("content", ""), extensions=["extra", "codehilite"]
    )

    # Format dates
    post["created_at_display"] = blog_timestamp(post).strftime("%d. %m. %Y")

    if (
        not current_user.is_authenticated
        or not current_user.is_admin
        or FLASK_ENV != "production"
    ):
        client_ip = request.headers.get("X-Real-IP") or request.remote_addr
        client_ip = client_ip or "unknown"
        # Increment view count
        today = datetime.now(timezone.utc).date().isoformat()
        redis_client.hincrby(f"blog:views:{post_id}:{today}", client_ip, 1)

    og_image = None
    if post.get("image"):
        og_image = post["image"]
        domain = os.getenv("WWW_DOMAIN")
        og_image = f"https://{domain}/blog/image/{og_image}"

    return render_template(
        "blog_post.html",
        post=post,
        pagetitle=post.get("title", "Sončnice"),
        blog_view="blog",
        og_image=og_image,
        og_url=request.url,
        og_title=post.get("title"),
        og_description=post.get("seo_description")
        or post.get("excerpt")
        or post.get("subtitle"),
    )


@blog_bp.route("/blog/image/<file_name>")
def blog_image_file(file_name):
    try:
        _ = safe_path("../data/blog_images", file_name)
        if not os.path.exists(os.path.join("data/blog_images", file_name)):
            abort(404)
    except ValueError:
        abort(404)
    if FLASK_ENV == "production":
        response = make_response()
        safe_filename = quote(file_name, safe="/")
        if not safe_filename.startswith("/"):
            safe_filename = "/" + safe_filename
        response.headers["X-Accel-Redirect"] = (
            f"/protected_blog_images{safe_filename}"
        )

        lower_name = file_name.lower()
        if lower_name.endswith(".jpg") or lower_name.endswith(".jpeg"):
            response.headers["Content-Type"] = "image/jpeg"
        elif lower_name.endswith(".png"):
            response.headers["Content-Type"] = "image/png"
    else:
        mimetype = None
        lower_name = file_name.lower()
        if lower_name.endswith(".jpg") or lower_name.endswith(".jpeg"):
            mimetype = "image/jpeg"
        elif lower_name.endswith(".png"):
            mimetype = "image/png"

        response = send_from_directory(
            "../data/blog_images",
            file_name,
            mimetype=mimetype,
            conditional=True,
        )
        response.headers["Accept-Ranges"] = "bytes"
    return response

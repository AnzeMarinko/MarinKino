import logging
import os
import re
from datetime import datetime, timezone
from io import BytesIO
from urllib.parse import urlsplit
from uuid import uuid4

from flask import (
    Blueprint,
    abort,
    current_app,
    flash,
    jsonify,
    make_response,
    redirect,
    render_template,
    request,
    send_file,
    session,
    url_for,
)
from flask_login import current_user, login_required
from werkzeug.exceptions import RequestEntityTooLarge

from admin_log_reader import (
    HOST_SNAPSHOT,
    file_entry,
    host_snapshot,
    secret_values,
)
from admin_statistics import AdminStatistics
from blog_content import load_posts
from blog_i18n import BLOG_LANGUAGES, messages
from blog_images import (
    MAX_GALLERY_REQUEST_BYTES,
    ImageUploadError,
    post_gallery,
    prepare_image,
    save_gallery,
    save_image,
)
from blog_subscribers import group_subscribers
from blog_translation import translate_url
from blueprints.blog_bp import public_base_url
from content_preparation.config import LOG_FILENAME
from security_storage import atomic_write_json, serialized_json
from utils import (
    is_current_admin_view,
    load_blog_subscribers,
    redis_client,
)

log = logging.getLogger(__name__)

admin_bp = Blueprint("admin", __name__)

users = {}

BLOG_DATA_FILE = os.path.join(
    os.path.dirname(__file__), "..", "..", "data", "blog_posts.json"
)
BLOG_IMAGES_DIR = os.path.join(
    os.path.dirname(__file__), "..", "..", "data", "blog_images"
)


def save_blog_image(file, crop_data=None):
    if not file:
        return None
    return save_image(file, BLOG_IMAGES_DIR, crop=crop_data)


@admin_bp.errorhandler(ImageUploadError)
def invalid_blog_image(error):
    if (
        request.endpoint == "admin.blog_image_preview"
        or request.headers.get("X-Requested-With") == "XMLHttpRequest"
    ):
        return jsonify(success=False, message=str(error)), 400
    flash(str(error), "error")
    return redirect(request.url)


@admin_bp.errorhandler(RequestEntityTooLarge)
def blog_request_too_large(_error):
    request_id = _blog_save_request_id()
    limit_mb = MAX_GALLERY_REQUEST_BYTES // (1024 * 1024)
    log.warning(
        "Blog save rejected request_id=%s reason=request-too-large "
        "content_length=%s limit_bytes=%s",
        request_id,
        request.content_length,
        MAX_GALLERY_REQUEST_BYTES,
    )
    message = (
        f"Zahteva je prevelika. Skupna velikost objave ne sme presegati "
        f"{limit_mb} MB."
    )
    if request.headers.get("X-Requested-With") == "XMLHttpRequest":
        return jsonify(success=False, message=message), 413
    return message, 413


@admin_bp.post("/admin/blog/image-preview")
@login_required
def blog_image_preview():
    if not is_current_admin_view(current_user):
        abort(403)
    image = prepare_image(request.files.get("image_file"), preview=True)
    response = send_file(BytesIO(image.data), mimetype=image.mimetype)
    response.headers["Cache-Control"] = "private, no-store"
    return response


def init_admin_bp(_users):
    """Initialize blueprint with app context"""
    global users
    users = _users


def load_blog_posts():
    return load_posts(BLOG_DATA_FILE)


def save_blog_posts(posts):
    atomic_write_json(BLOG_DATA_FILE, posts)


def _blog_save_request_id():
    candidate = request.headers.get("X-Request-ID", "")
    if re.fullmatch(r"[A-Za-z0-9_-]{1,64}", candidate):
        return candidate
    return uuid4().hex


def _log_blog_save_received(request_id):
    log.info(
        "Blog save received request_id=%s path=%s content_length=%s "
        "form_fields=%s file_fields=%s",
        request_id,
        request.path,
        request.content_length,
        sorted(request.form.keys()),
        sorted(request.files.keys()),
    )


def _save_blog_gallery(request_id, post=None):
    try:
        images, image_uploads = save_gallery(
            request.form, request.files, BLOG_IMAGES_DIR, post=post
        )
    except ImageUploadError as error:
        log.warning(
            "Blog image validation failed request_id=%s error=%s",
            request_id,
            error,
        )
        raise
    except Exception:
        log.exception("Blog image save failed request_id=%s", request_id)
        raise
    log.info(
        "Blog gallery prepared request_id=%s images=%d uploads=%d",
        request_id,
        len(images),
        len(image_uploads),
    )
    return images, image_uploads


def _persist_blog_posts(posts, request_id, post_id):
    try:
        save_blog_posts(posts)
    except Exception:
        log.exception(
            "Blog post persistence failed request_id=%s post_id=%s",
            request_id,
            post_id,
        )
        raise
    log.info(
        "Blog post persisted request_id=%s post_id=%s", request_id, post_id
    )


@admin_bp.route("/admin/logs")
@login_required
def admin_logs():
    if not is_current_admin_view(current_user):
        return redirect(url_for("home"))
    snapshot = host_snapshot(HOST_SNAPSHOT)
    sources = [
        file_entry(
            "app", "Aplikacija", LOG_FILENAME, secret_values(os.environ)
        ),
        *snapshot["entries"],
    ]
    selected = request.args.get("source", "app")
    source = next((item for item in sources if item["id"] == selected), None)
    if source is None:
        abort(400)
    response = make_response(
        render_template(
            "admin_logs.html",
            pagetitle="Sistemski dnevnik · MarinKino",
            system_log=source["text"],
            log_sources=sources,
            log_source=source,
            host_status=snapshot,
        )
    )
    response.headers["Cache-Control"] = "private, no-store"
    response.headers["X-Robots-Tag"] = "noindex, nofollow"
    return response


@admin_bp.route("/admin/gold")
@login_required
def admin_gold():
    if not is_current_admin_view(current_user):
        return redirect(url_for("home"))
    return render_template(
        "admin_gold.html", pagetitle="Cene zlata · MarinKino"
    )


@admin_bp.route("/admin")
@login_required
def admin_panel():
    if not is_current_admin_view(current_user):
        return redirect(url_for("home"))

    cache = current_app.extensions.get("admin_statistics")
    if cache is None:
        cache = AdminStatistics(redis_client)
        current_app.extensions["admin_statistics"] = cache
    statistics = cache.snapshot(load_blog_posts())
    return render_template(
        "admin.html",
        pagetitle="MarinKino - Nadzorna plošča",
        emails=", ".join(
            email for user in users.values() for email in user.get("emails", [])
        ),
        users_count=len(users),
        **statistics,
    )


@admin_bp.route("/admin/set-view-as/<view_mode>", methods=["POST"])
@login_required
def set_view_as(view_mode):
    """Set the view mode for admin preview (anonymous, user, admin)"""
    if not current_user.is_authenticated or not current_user.is_admin:
        return redirect(url_for("home"))

    if view_mode in ["anonymous", "user", "admin"]:
        session["view_as"] = view_mode
    else:
        session.pop("view_as", None)

    return redirect(url_for("home"))


@admin_bp.route("/admin/clear-view-as", methods=["POST"])
@login_required
def clear_view_as():
    """Clear the view as mode"""
    if not current_user.is_authenticated or not current_user.is_admin:
        return redirect(url_for("home"))

    session.pop("view_as", None)
    target = url_for("admin.admin_panel")
    previous = urlsplit(request.referrer or "")
    if (
        previous.scheme in {"http", "https"}
        and previous.netloc == request.host
    ):
        target = previous.path or "/"
        if previous.query:
            target += "?" + previous.query
    return redirect(target)


@admin_bp.route("/admin/blog")
@login_required
def admin_blog():
    if not is_current_admin_view(current_user):
        return redirect(url_for("home"))

    posts = load_blog_posts()
    sorted_posts = sorted(
        posts.values(), key=lambda x: x.get("created_at", ""), reverse=True
    )

    # Get view stats for each post and format dates
    for post in sorted_posts:
        views = 0
        for key in redis_client.scan_iter(f"blog:views:{post['id']}:*"):
            views += len(redis_client.hgetall(key).keys())
        post["views"] = views
        # Format dates
        if post.get("created_at"):
            try:
                dt = datetime.fromisoformat(
                    post["created_at"].replace("Z", "+00:00")
                )
                post["created_at_formatted"] = dt.strftime("%d.%m.%Y")
            except Exception:
                post["created_at_formatted"] = post.get("created_at", "")
        if post.get("published_at"):
            try:
                dt = datetime.fromisoformat(
                    post["published_at"].replace("Z", "+00:00")
                )
                post["published_at_formatted"] = dt.strftime("%d.%m.%Y")
            except Exception:
                post["published_at_formatted"] = post.get("published_at", "")

    return render_template("admin_blog.html", posts=sorted_posts)


@admin_bp.route("/admin/blog/new", methods=["GET", "POST"])
@login_required
@serialized_json(lambda: BLOG_DATA_FILE)
def admin_blog_new():
    if not is_current_admin_view(current_user):
        return redirect(url_for("home"))

    if request.method == "POST":
        request_id = _blog_save_request_id()
        _log_blog_save_received(request_id)
        title = request.form.get("title")
        subtitle = request.form.get("subtitle")
        content = request.form.get("content")
        image = request.form.get("image")
        keywords = request.form.get("keywords")
        seo_description = request.form.get("seo_description", "").strip()
        excerpt = seo_description
        image_desc = request.form.get("image_desc")
        published = request.form.get("published") == "1"

        if not title or not content:
            log.warning(
                "Blog save rejected request_id=%s "
                "reason=missing-required-fields",
                request_id,
            )
            if (
                request.headers.get("X-Requested-With") == "XMLHttpRequest"
                or request.is_json
            ):
                return jsonify(
                    {
                        "success": False,
                        "message": "Naslov in vsebina sta obvezna.",
                    }
                )
            flash("Naslov in vsebina sta obvezna.", "error")
            return redirect(request.url)

        images, image_uploads = _save_blog_gallery(request_id)
        image = images[0]["filename"] if images else None
        image_desc = images[0]["description"] if images else image_desc

        posts = load_blog_posts()
        # post_id made out of title and current timestamp to avoid collisions
        # convert title to a slug-like format by replacing spaces with
        # underscores
        # and removing special characters (ščćž and their uppercase variants)
        slug_title = (
            "".join(c if c.isalnum() else "_" for c in title.lower())
            .strip("_")
            .replace("š", "s")
            .replace("č", "c")
            .replace("ć", "c")
            .replace("ž", "z")
        )
        post_id = slug_title
        now = datetime.now(timezone.utc).isoformat()
        if post_id in posts:
            timestamp = (
                datetime.now(timezone.utc).isoformat()[:16].replace(":", "-")
            )
            post_id = f"{slug_title}_{timestamp}"
        posts[post_id] = {
            "id": post_id,
            "title": title,
            "subtitle": subtitle,
            "content": content,
            "image": image,
            "images": images,
            "image_desc": image_desc,
            "excerpt": excerpt,
            "keywords": keywords,
            "seo_description": seo_description,
            "published": published,
            "created_at": now,
            "published_at": now if published else None,
            "mail_date": None,
        }
        _persist_blog_posts(posts, request_id, post_id)

        # Vrni JSON če je AJAX zahtevek, drugače redirect
        if (
            request.headers.get("X-Requested-With") == "XMLHttpRequest"
            or request.is_json
        ):
            log.info(
                "Blog save response success request_id=%s post_id=%s",
                request_id,
                post_id,
            )
            return jsonify(
                {
                    "success": True,
                    "message": "Blog objava ustvarjena.",
                    "post_id": post_id,
                    "edit_url": url_for(
                        "admin.admin_blog_edit", post_id=post_id
                    ),
                    "images": images,
                    "image_uploads": image_uploads,
                }
            )

        flash("Blog objava ustvarjena.", "success")
        return redirect(url_for("admin.admin_blog"))
    return render_template(
        "admin_blog_edit.html", post=None, gallery_images=[]
    )


@admin_bp.route("/admin/blog/edit/<post_id>", methods=["GET", "POST"])
@login_required
@serialized_json(lambda: BLOG_DATA_FILE)
def admin_blog_edit(post_id):
    if not is_current_admin_view(current_user):
        return redirect(url_for("home"))

    posts = load_blog_posts()
    post = posts.get(post_id)
    if not post:
        abort(404)

    if request.method == "POST":
        request_id = _blog_save_request_id()
        _log_blog_save_received(request_id)
        title = request.form.get("title")
        subtitle = request.form.get("subtitle")
        content = request.form.get("content")
        keywords = request.form.get("keywords")
        seo_description = request.form.get("seo_description", "").strip()
        excerpt = seo_description
        image_desc = request.form.get("image_desc")
        published = request.form.get("published") == "1"

        if not title or not content:
            log.warning(
                "Blog save rejected request_id=%s post_id=%s "
                "reason=missing-required-fields",
                request_id,
                post_id,
            )
            if (
                request.headers.get("X-Requested-With") == "XMLHttpRequest"
                or request.is_json
            ):
                return jsonify(
                    {
                        "success": False,
                        "message": "Naslov in vsebina sta obvezna.",
                    }
                )
            flash("Naslov in vsebina sta obvezna.", "error")
            return redirect(request.url)

        images, image_uploads = _save_blog_gallery(request_id, post=post)
        image = images[0]["filename"] if images else None
        image_desc = images[0]["description"] if images else image_desc

        # Update published_at if just published
        published_at = post.get("published_at")
        if published and not published_at:
            published_at = datetime.now(timezone.utc).isoformat()
        elif not published:
            published_at = None

        # preserve existing mail_date if present
        existing_mail_date = post.get("mail_date")

        posts[post_id] = {
            "id": post_id,
            "title": title,
            "subtitle": subtitle,
            "content": content,
            "image": image,
            "images": images,
            "image_desc": image_desc,
            "excerpt": excerpt,
            "keywords": keywords,
            "seo_description": seo_description,
            "published": published,
            "created_at": post.get(
                "created_at", datetime.now(timezone.utc).isoformat()
            ),
            "published_at": published_at,
            "mail_date": existing_mail_date,
            "mail_languages_sent": post.get("mail_languages_sent", []),
        }
        _persist_blog_posts(posts, request_id, post_id)

        # Vrni JSON če je AJAX zahtevek, drugače redirect
        if (
            request.headers.get("X-Requested-With") == "XMLHttpRequest"
            or request.is_json
        ):
            log.info(
                "Blog save response success request_id=%s post_id=%s",
                request_id,
                post_id,
            )
            return jsonify(
                {
                    "success": True,
                    "message": "Blog objava posodobljena.",
                    "post_id": post_id,
                    "edit_url": url_for(
                        "admin.admin_blog_edit", post_id=post_id
                    ),
                    "images": images,
                    "image_uploads": image_uploads,
                }
            )

        flash("Blog objava posodobljena.", "success")
        return redirect(url_for("admin.admin_blog"))

    # Format dates for display
    if post:
        if post.get("created_at"):
            try:
                dt = datetime.fromisoformat(
                    post["created_at"].replace("Z", "+00:00")
                )
                post["created_at_display"] = dt.strftime("%d.%m.%Y %H:%M")
            except Exception:
                post["created_at_display"] = post.get("created_at", "")
        if post.get("published_at"):
            try:
                dt = datetime.fromisoformat(
                    post["published_at"].replace("Z", "+00:00")
                )
                post["published_at_display"] = dt.strftime("%d.%m.%Y %H:%M")
            except Exception:
                post["published_at_display"] = post.get("published_at", "")

    return render_template(
        "admin_blog_edit.html", post=post, gallery_images=post_gallery(post)
    )


@admin_bp.route("/admin/blog/delete/<post_id>", methods=["POST"])
@login_required
@serialized_json(lambda: BLOG_DATA_FILE)
def admin_blog_delete(post_id):
    if not is_current_admin_view(current_user):
        return redirect(url_for("home"))

    posts = load_blog_posts()
    if post_id in posts:
        del posts[post_id]
        save_blog_posts(posts)
        # Delete view stats
        redis_client.delete(f"blog:views:{post_id}")
        flash("Blog objava izbrisana.", "success")
    return redirect(url_for("admin.admin_blog"))


@admin_bp.route("/admin/blog/send_mail/<post_id>", methods=["POST"])
@login_required
def admin_blog_send_mail(post_id):
    if not is_current_admin_view(current_user):
        return redirect(url_for("home"))

    posts = load_blog_posts()
    post = posts.get(post_id)
    if not post:
        abort(404)

    if not post.get("published"):
        if (
            request.is_json
            or request.headers.get("X-Requested-With") == "XMLHttpRequest"
        ):
            return jsonify(
                {
                    "success": False,
                    "message": (
                        "Objava mora biti objavljena, da pošljete mail."
                    ),
                }
            )
        flash("Objava mora biti objavljena, da pošljete mail.", "error")
        return redirect(request.referrer or url_for("admin.admin_blog"))

    if post.get("mail_date"):
        if (
            request.is_json
            or request.headers.get("X-Requested-With") == "XMLHttpRequest"
        ):
            return jsonify(
                {
                    "success": False,
                    "message": "E-pošta za to objavo je bila že poslana.",
                }
            )
        flash("E-pošta za to objavo je bila že poslana.", "error")
        return redirect(request.referrer or url_for("admin.admin_blog"))

    groups = group_subscribers(load_blog_subscribers())
    if not groups:
        if (
            request.is_json
            or request.headers.get("X-Requested-With") == "XMLHttpRequest"
        ):
            return jsonify(
                {"success": False, "message": "Ni naročnikov za pošiljanje."}
            )
        flash("Ni naročnikov za pošiljanje.", "error")
        return redirect(request.referrer or url_for("admin.admin_blog"))

    sent_languages = set(post.get("mail_languages_sent", []))
    deliveries = []
    try:
        base_url = public_base_url()
        if not base_url:
            raise ValueError("Public blog URL is not configured")
        source_post_url = base_url + url_for("blog.blog_post", post_id=post_id)
        source_blog_url = base_url + url_for("blog.blog_list")
        for language, recipients in groups.items():
            if language in sent_languages:
                continue
            copy = messages(language)
            post_url = translate_url(source_post_url, language)
            subject = (
                f"Nov blog: {post.get('title', '')}"
                if language == "sl"
                else copy["new_post_subject"]
            )
            html = render_template(
                "mail_blog_post.html",
                post=post,
                is_for_mail=True,
                domain=os.getenv("WWW_DOMAIN"),
                mail_base_url=base_url,
                mail_copy=copy,
                mail_language=language,
                mail_direction=BLOG_LANGUAGES[language]["direction"],
                blog_url=translate_url(source_blog_url, language),
                post_url=post_url,
            )
            text_parts = [copy["new_post_intro"]]
            if language == "sl":
                text_parts.extend(
                    [
                        post.get("title", ""),
                        post.get("excerpt") or post.get("subtitle", ""),
                    ]
                )
            text_parts.extend(
                [
                    f"{copy['read_post']}: {post_url}",
                    copy["greeting"],
                    "Anže Marinko",
                    copy["unsubscribe"],
                ]
            )
            if language != "sl":
                text_parts.append(copy["automatic_notice"])
            deliveries.append(
                (language, recipients, subject, html, "\n\n".join(text_parts))
            )
    except Exception:
        log.exception("Napaka pri oblikovanju maila naročnikom")
        if (
            request.is_json
            or request.headers.get("X-Requested-With") == "XMLHttpRequest"
        ):
            return jsonify(
                {"success": False, "message": "Napaka pri oblikovanju maila."}
            )
        flash("Napaka pri oblikovanju maila.", "error")
        return redirect(request.referrer or url_for("admin.admin_blog"))

    # Keep subscribers private, with a separate BCC message per language.
    admin_emails = []
    for username, data in users.items():
        if data.get("is_admin"):
            admin_emails += data.get("emails", [])
    if not admin_emails:
        admin_emails = [os.getenv("GMAIL_USERNAME")]

    from background_jobs import QueueFull

    try:
        job = current_app.extensions["jobs"].enqueue(
            "blog_mail",
            {
                "posts_path": os.path.abspath(BLOG_DATA_FILE),
                "post_id": post_id,
                "deliveries": deliveries,
                "sender_recipient": admin_emails[0],
            },
            owner=current_user.get_id() or "",
            dedupe_key=f"blog-mail:{post_id}",
        )
    except QueueFull:
        return jsonify(
            success=False,
            message="Vrsta za pošiljanje je polna. Poskusi pozneje.",
        ), 503
    status_url = url_for("admin.mail_job_status", job_id=job["id"])
    message = {
        "pending": "E-pošta je v vrsti za pošiljanje.",
        "running": "Pošiljanje e-pošte že poteka.",
        "done": "E-pošta je že poslana.",
        "uncertain": "Pošiljanje je bilo prekinjeno. Pred ponovitvijo preveri dostavo.",
    }[job["state"]]
    if (
        request.is_json
        or request.headers.get("X-Requested-With") == "XMLHttpRequest"
    ):
        return jsonify(
            {
                "success": True,
                "message": message,
                "status_url": status_url,
                "state": job["state"],
            }
        )

    flash(message, "error" if job["state"] == "uncertain" else "success")
    return redirect(request.referrer or url_for("admin.admin_blog"))


@admin_bp.get("/admin/mail-jobs/<job_id>")
@login_required
def mail_job_status(job_id):
    if not is_current_admin_view(current_user):
        abort(403)
    job = current_app.extensions["jobs"].get(job_id)
    if not job or job["kind"] not in {"mail", "blog_mail"}:
        abort(404)
    return jsonify(state=job["state"])

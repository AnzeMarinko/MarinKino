import json
import logging
import os
from datetime import datetime, timezone
from urllib.parse import quote

import markdown
from flask import (
    Blueprint,
    abort,
    make_response,
    render_template,
    request,
    send_from_directory,
)
from flask_login import current_user

from utils import FLASK_ENV, redis_client, safe_path

log = logging.getLogger(__name__)

blog_bp = Blueprint("blog", __name__)

BLOG_DATA_FILE = os.path.join(
    os.path.dirname(__file__), "..", "..", "data", "blog_posts.json"
)


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
    timestamp = (blog.get("published_at") or blog.get("created_at", "")).replace(
        "Z", "+00:00"
    )
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
        post["created_at_display"] = blog_timestamp(post).strftime("%d. %m. %Y")

    return render_template(
        "blog_list.html",
        posts=sorted_posts,
        pagetitle="Sončnice",
        blog_view="blog",
    )


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
        client_ip = request.headers.get("X-Real-IP", request.remote_addr)
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
        path = safe_path("../data/blog_images", file_name)
        if not os.path.exists(os.path.join("data/blog_images", file_name)):
            abort(404)
    except ValueError:
        abort(404)
    if FLASK_ENV == "production":
        response = make_response()
        safe_filename = quote(file_name, safe="/")
        if not safe_filename.startswith("/"):
            safe_filename = "/" + safe_filename
        response.headers["X-Accel-Redirect"] = f"/protected_blog_images{safe_filename}"

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
            "../data/blog_images", file_name, mimetype=mimetype, conditional=True
        )
        response.headers["Accept-Ranges"] = "bytes"
    return response

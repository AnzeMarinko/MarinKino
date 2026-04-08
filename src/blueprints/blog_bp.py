import json
import logging
import os
from datetime import datetime, timezone

import markdown
from flask import Blueprint, abort, render_template
from flask_login import current_user

from utils import redis_client

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


@blog_bp.route("/blog")
def blog_list():
    posts = load_blog_posts()
    # Filter published posts for non-admin users
    if not (current_user.is_authenticated and current_user.is_admin):
        posts = {k: v for k, v in posts.items() if v.get("published", False)}
    # Sort by date descending
    sorted_posts = sorted(
        posts.values(), key=lambda x: x.get("created_at", ""), reverse=True
    )

    # Format dates
    for post in sorted_posts:
        if post.get("created_at"):
            try:
                dt = datetime.fromisoformat(post["created_at"].replace("Z", "+00:00"))
                post["created_at_display"] = dt.strftime("%d.%m.%Y")
            except:
                post["created_at_display"] = post.get("created_at", "")

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
    if not (current_user.is_authenticated and current_user.is_admin) and not post.get(
        "published", False
    ):
        abort(404)

    # Render Markdown content
    post["content_html"] = markdown.markdown(
        post.get("content", ""), extensions=["extra", "codehilite"]
    )

    # Format dates
    if post.get("created_at"):
        try:
            dt = datetime.fromisoformat(post["created_at"].replace("Z", "+00:00"))
            post["created_at_display"] = dt.strftime("%d.%m.%Y")
        except:
            post["created_at_display"] = post.get("created_at", "")

    # Increment view count
    today = datetime.now(timezone.utc).date().isoformat()
    redis_client.hincrby(f"blog:views:{post_id}", today, 1)
    redis_client.hincrby("blog:views:total", today, 1)

    og_image = None
    if post.get("image"):
        og_image = post["image"]
        if og_image.startswith("/"):
            domain = os.getenv("DUCKDNS_DOMAIN")
            if domain:
                og_image = f"https://{domain}{og_image}"
        elif og_image.startswith("//"):
            og_image = f"https:{og_image}"

    return render_template(
        "blog_post.html",
        post=post,
        pagetitle=post.get("title", "Sončnice"),
        blog_view="blog",
        og_image=og_image,
        og_title=post.get("title"),
        og_description=post.get("excerpt") or post.get("subtitle"),
    )

"""
SEO Blueprint - handles sitemap, robots.txt, and other SEO-related routes
"""

import json
import os
from datetime import date, datetime, timezone

from flask import Blueprint

seo_bp = Blueprint("seo", __name__)

BLOG_DATA_FILE = os.path.join(
    os.path.dirname(__file__), "..", "..", "data", "blog_posts.json"
)


def load_blog_posts():
    """Load blog posts from JSON file"""
    if os.path.exists(BLOG_DATA_FILE):
        with open(BLOG_DATA_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    return {}


def blog_timestamp(blog):
    """Parse blog timestamp"""
    timestamp = blog.get("published_at", blog.get("created_at", "")).replace(
        "Z", "+00:00"
    )
    try:
        return datetime.fromisoformat(timestamp)
    except Exception:
        return datetime.now(timezone.utc)


@seo_bp.route("/sitemap.xml")
def sitemap():
    """Generate sitemap.xml for Google Search Console"""
    domain = os.getenv("WWW_DOMAIN", "localhost")
    protocol = "https"

    # Static pages with priority and change frequency
    static_pages = [
        {"url": "/", "priority": 1.0, "changefreq": "weekly"},
        {"url": "/blog", "priority": 0.9, "changefreq": "daily"},
    ]

    # Build sitemap entries
    sitemap_entries = []

    # Add static pages
    for page in static_pages:
        sitemap_entries.append(
            {
                "loc": f"{protocol}://{domain}{page['url']}",
                "lastmod": datetime.now(timezone.utc).isoformat(),
                "changefreq": page["changefreq"],
                "priority": page["priority"],
            }
        )

    # Add blog posts
    posts = load_blog_posts()
    for post_id, post in posts.items():
        if post.get("published", False):
            sitemap_entries.append(
                {
                    "loc": f"{protocol}://{domain}/blog/{post_id}",
                    "lastmod": (
                        post.get("updated_at")
                        or post.get("published_at")
                        or post.get("created_at", "")
                    ).replace("Z", "+00:00"),
                    "changefreq": "monthly",
                    "priority": 0.8,
                }
            )

    # Generate XML
    sitemap_xml = '<?xml version="1.0" encoding="UTF-8"?>\n'
    sitemap_xml += '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9"'
    sitemap_xml += ' xmlns:image="http://www.google.com/schemas/sitemap-image/1.1"'
    sitemap_xml += ' xmlns:news="http://www.google.com/schemas/sitemap-news/0.9">\n'

    for entry in sitemap_entries:
        sitemap_xml += "  <url>\n"
        sitemap_xml += f"    <loc>{entry['loc']}</loc>\n"
        if entry.get("lastmod"):
            sitemap_xml += f"    <lastmod>{entry['lastmod']}</lastmod>\n"
        sitemap_xml += f"    <changefreq>{entry['changefreq']}</changefreq>\n"
        sitemap_xml += f"    <priority>{entry['priority']}</priority>\n"
        sitemap_xml += "  </url>\n"

    sitemap_xml += "</urlset>"

    return sitemap_xml, 200, {"Content-Type": "application/xml; charset=utf-8"}


@seo_bp.route("/robots.txt")
def robots():
    """Generate robots.txt for search engines"""
    domain = os.getenv("WWW_DOMAIN", "localhost")

    robots_txt = f"""# Soncnice robots.txt
# Generated for {domain}

# Allow all search engines
User-agent: *
Allow: /

# Disallow admin and private areas
Disallow: /admin
Disallow: /admin/
Disallow: /api/
Disallow: /auth/login
Disallow: /auth/register
Disallow: /auth/forgot-password
Disallow: /__pycache__/
Disallow: /cache/
Disallow: /.env
Disallow: /*.json$
Disallow: /static/

# Allow specific static paths
Allow: /static/css/
Allow: /static/script/
Allow: /static/favicon_io/
Allow: /static/blog_favicon_io/

# Crawl delay in seconds (be nice to servers)
User-agent: *
Crawl-delay: 1

# Specify sitemap
Sitemap: https://{domain}/sitemap.xml

# Specific rules for Googlebot
User-agent: Googlebot
Allow: /
Crawl-delay: 0.5

# Block bad bots
User-agent: MJ12bot
Disallow: /

User-agent: AhrefsBot
Disallow: /

User-agent: SemrushBot
Disallow: /
"""

    return robots_txt, 200, {"Content-Type": "text/plain; charset=utf-8"}


@seo_bp.route("/robots.txt~")
@seo_bp.route("/.well-known/security.txt")
def security():
    """Basic security.txt file"""
    domain = os.getenv("WWW_DOMAIN", "localhost")

    security_txt = f"""Contact: https://{domain}
Expires: {date.today().year + 1}-04-12T00:00:00Z
Preferred-Languages: en, sl
"""

    return security_txt, 200, {"Content-Type": "text/plain; charset=utf-8"}


@seo_bp.route("/google-site-verification.txt")
def google_verification():
    """
    Placeholder for Google Search Console verification.
    Replace with your actual verification token from Google.
    """
    return (
        f"google-site-verification: {os.environ['GOOGLE_VERIFICATION_TOKEN']}",
        200,
        {"Content-Type": "text/plain"},
    )

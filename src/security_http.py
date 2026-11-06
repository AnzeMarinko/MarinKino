"""Bound resource use and enforce common HTTP security controls."""

import ipaddress
import logging
import os
import secrets
from datetime import date
from urllib.parse import urlsplit

from flask import abort, g, request
from flask_login import current_user
from redis.exceptions import RedisError

log = logging.getLogger(__name__)
STATS_TTL = 90 * 86400


def client_ip():
    """REMOTE_ADDR is set only by the configured trusted WSGI proxy."""
    try:
        return str(ipaddress.ip_address(request.remote_addr or ""))
    except ValueError:
        return "unknown"


def rate_limit_identity():
    value = client_ip()
    if ":" in value:
        return str(ipaddress.ip_network(value + "/64", strict=False))
    return value


def guest_identity():
    return "ip:" + rate_limit_identity()


def trusted_hosts():
    hosts = {"localhost", "127.0.0.1", "[::1]"}
    for name in ("WWW_DOMAIN", "MAIN_DOMAIN", "DUCKDNS_DOMAIN"):
        value = os.getenv(name, "").strip()
        if value:
            hosts.add(value)
    if os.getenv("PUBLIC_BASE_URL"):
        host = urlsplit(os.environ["PUBLIC_BASE_URL"]).hostname
        if host:
            hosts.add(host)
    return sorted(hosts)


def init_security(app, limiter):
    app.config.update(
        TRUSTED_HOSTS=trusted_hosts(),
        MAX_FORM_MEMORY_SIZE=128 * 1024,
        MAX_FORM_PARTS=32,
    )
    app.jinja_env.globals["csp_nonce"] = lambda: getattr(g, "csp_nonce", "")

    @app.before_request
    def bound_request():
        g.csp_nonce = secrets.token_urlsafe(24)
        # Only the administrator's image forms need a large request body.
        if request.endpoint not in {
            "admin.admin_blog_new",
            "admin.admin_blog_edit",
            "admin.blog_image_preview",
        }:
            request.max_content_length = 64 * 1024
        if (
            request.content_length
            and request.content_length > request.max_content_length
        ):
            abort(413)
        if len(request.query_string) > 2048:
            abort(414)
        if request.method not in {"GET", "HEAD", "OPTIONS"}:
            if request.headers.get("Sec-Fetch-Site") == "cross-site":
                abort(403)
        if (
            current_user.is_authenticated
            and getattr(current_user, "must_change_password", False)
            and request.endpoint
            not in {
                "auth.change_password",
                "auth.logout",
                "static",
                "csrf_token",
                "healthz",
            }
        ):
            from flask import redirect, url_for

            return redirect(url_for("auth.change_password"))

    # Enforce bounds before CSRF middleware parses uploaded form data.
    app.before_request_funcs[None].remove(bound_request)
    app.before_request_funcs[None].insert(0, bound_request)

    # Streaming segments and ordinary static files have separate Nginx limits.
    for endpoint, limit in {
        "misc.weather": "20 per minute",
        "misc.weather_current_location": "10 per minute",
        "misc.pod_krinko_new_words": "30 per minute",
        "memes.meme": "60 per minute",
        "blog.blog_subscribe": "10 per minute",
        "blog.blog_confirm_subscription": "20 per minute",
        "movies.prepare_download": "3 per hour",
        "movies.add_comment": "5 per minute; 30 per day",
        "auth.change_password": "5 per minute",
        "auth.reset_password": "10 per minute",
    }.items():
        if endpoint in app.view_functions:
            app.view_functions[endpoint] = limiter.limit(limit)(
                app.view_functions[endpoint]
            )


def add_headers(response, production=False):
    # The optional chart is loaded by an administrator's explicit action.
    # Keep provider access confined to that page, including its data socket.
    chart_page = (
        request.endpoint == "admin.admin_gold"
        and current_user.is_authenticated
        and current_user.is_admin
        and response.status_code == 200
    )
    chart_assets = " https://www.bullionvault.com" if chart_page else ""
    chart_data = (
        " https://chart-data.bullionvault.com"
        " wss://chart-data.bullionvault.com"
        if chart_page
        else ""
    )
    for name, value in {
        "X-Content-Type-Options": "nosniff",
        "X-Frame-Options": "SAMEORIGIN",
        "Referrer-Policy": "same-origin",
        "Permissions-Policy": "camera=(), microphone=(), geolocation=(self)",
        "Content-Security-Policy": (
            "default-src 'self'; base-uri 'self'; object-src 'none'; "
            "frame-ancestors 'self'; form-action 'self'; "
            f"script-src 'self' 'nonce-{getattr(g, 'csp_nonce', '')}' "
            f"https://challenges.cloudflare.com{chart_assets}; "
            "script-src-attr 'none'; "
            f"style-src 'self' 'unsafe-inline'{chart_assets}; "
            "img-src 'self' data: blob: https:; "
            "font-src 'self' data:; connect-src 'self' "
            f"https://challenges.cloudflare.com{chart_data}; "
            "frame-src https://challenges.cloudflare.com; "
            "worker-src 'self' blob:; media-src 'self' blob:"
        ),
    }.items():
        response.headers.setdefault(name, value)
    if production:
        response.headers.setdefault(
            "Strict-Transport-Security", "max-age=31536000; includeSubDomains"
        )
    if current_user.is_authenticated or request.path.startswith("/password/"):
        response.headers.setdefault("Cache-Control", "private, no-store")
    return response


def record_response(response, redis):
    """Keep bounded route counters without visitor IPs or geolocation."""
    if request.endpoint in {"static", "healthz", "csrf_token"}:
        return response
    if (
        "/file/" in request.path
        or "/hls/" in request.path
        or "/blog/image/" in request.path
        or "video-progress" in request.path
    ):
        return response
    today = date.today().isoformat()
    month = today[:7]

    route = request.url_rule.rule if request.url_rule else "<unmatched>"
    user_id = current_user.id if current_user.is_authenticated else "anonymus"
    method = (
        request.method
        if request.method
        in {"GET", "POST", "HEAD", "OPTIONS", "PUT", "PATCH", "DELETE"}
        else "OTHER"
    )
    field = f"{method} {route}"
    try:
        pipe = redis.pipeline(transaction=False)
        key = f"stats:daily:{today}:{user_id}:{response.status}"
        pipe.hincrby(key, field, 1)
        pipe.expire(key, STATS_TTL)
        if response.status_code < 400:
            key = f"stats:monthly:{month}"
            pipe.hincrby(key, field, 1)
            pipe.expire(key, 400 * 86400)
        referrer = request.referrer
        if referrer and response.status_code < 400:
            host = urlsplit(referrer).hostname or ""
            source = "other"
            for domain, label in (
                ("facebook.com", "facebook"),
                ("instagram.com", "instagram"),
                ("google.com", "google"),
                (os.getenv("WWW_DOMAIN", ""), "internal"),
            ):
                if domain and (host == domain or host.endswith("." + domain)):
                    source = label
                    break
            key = f"stats:referrer:{today}"
            pipe.hincrby(key, source, 1)
            pipe.expire(key, STATS_TTL)
            content = request.blueprint or "other"
            key = f"stats:referrer_content:{today}:{content}"
            pipe.hincrby(key, source, 1)
            pipe.expire(key, STATS_TTL)
        pipe.execute()
    except (RedisError, ValueError):
        # Statistics are optional. Redis authentication still fails closed.
        pass
    return response

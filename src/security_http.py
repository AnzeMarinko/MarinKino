"""Bound resource use and enforce common HTTP security controls."""

import hashlib
import ipaddress
import json
import logging
import os
import secrets
from concurrent.futures import ThreadPoolExecutor
from datetime import date
from threading import BoundedSemaphore
from urllib.parse import urlsplit

from flask import abort, g, request
from flask_login import current_user
from redis.exceptions import RedisError

log = logging.getLogger(__name__)
STATS_TTL = 90 * 86400
_geo_pool = ThreadPoolExecutor(max_workers=1, thread_name_prefix="geo")
_geo_slots = BoundedSemaphore(4)


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
        "movies.download_movie": "3 per hour",
        "movies.add_comment": "5 per minute; 30 per day",
        "auth.change_password": "5 per minute",
        "auth.reset_password": "10 per minute",
    }.items():
        if endpoint in app.view_functions:
            app.view_functions[endpoint] = limiter.limit(limit)(
                app.view_functions[endpoint]
            )


def add_headers(response, production=False):
    for name, value in {
        "X-Content-Type-Options": "nosniff",
        "X-Frame-Options": "SAMEORIGIN",
        "Referrer-Policy": "same-origin",
        "Permissions-Policy": "camera=(), microphone=(), geolocation=(self)",
        "Content-Security-Policy": (
            "base-uri 'self'; object-src 'none'; frame-ancestors 'self'; "
            "form-action 'self'"
        ),
    }.items():
        response.headers.setdefault(name, value)
    # Report-only while legacy inline event handlers are migrated. The enforced
    # policy above already blocks base-tag, plugin and cross-origin form abuse.
    response.headers.setdefault(
        "Content-Security-Policy-Report-Only",
        "default-src 'self'; "
        f"script-src 'self' 'nonce-{getattr(g, 'csp_nonce', '')}' "
        "https://challenges.cloudflare.com; "
        "style-src 'self' 'unsafe-inline'; img-src 'self' data: https:; "
        "font-src 'self' data:; connect-src 'self' "
        "https://challenges.cloudflare.com; "
        "frame-src https://challenges.cloudflare.com; media-src 'self' blob:",
    )
    if production:
        response.headers.setdefault(
            "Strict-Transport-Security", "max-age=31536000; includeSubDomains"
        )
    if current_user.is_authenticated or request.path.startswith("/password/"):
        response.headers.setdefault("Cache-Control", "private, no-store")
    return response


def _save_geo(redis, ip, today, locate):
    try:
        location = locate(ip)
        if location.get("country") != "Unknown":
            redis.hset(f"stats:geo:{today}", ip, json.dumps(location))
            redis.expire(f"stats:geo:{today}", 14 * 86400)
    except Exception:
        log.warning("Geolocation unavailable")
    finally:
        _geo_slots.release()


def record_response(response, redis, locate=None):
    """Aggregate route patterns, expire every key and never delay responses."""
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

    def _route_hidden():
        for r in [
            "<token>",
            "<password>",
            "<entry_id>",
            "<session_token>",
        ]:
            if request.url_rule and r in request.url_rule.rule:
                return request.url_rule.rule
        return request.path

    route = _route_hidden()
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
        if (
            locate
            and request.endpoint == "blog.blog_post"
            and response.status_code == 200
            and request.method == "GET"
            and not (current_user.is_authenticated and current_user.is_admin)
        ):
            ip = client_ip()
            if ip != "unknown" and _geo_slots.acquire(blocking=False):
                digest = hashlib.sha256(ip.encode()).hexdigest()
                try:
                    if redis.set(
                        f"stats:geo:seen:{today}:{digest}",
                        "1",
                        nx=True,
                        ex=86400,
                    ):
                        _geo_pool.submit(_save_geo, redis, ip, today, locate)
                    else:
                        _geo_slots.release()
                except Exception:
                    _geo_slots.release()
                    raise
    except (RedisError, ValueError):
        # Statistics are optional. Redis authentication still fails closed.
        pass
    return response

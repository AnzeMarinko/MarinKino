"""HTTP controls must bound hostile input before expensive application work."""

import re
from types import SimpleNamespace

import fakeredis
import pytest
from flask import Flask, jsonify, request
from flask_login import LoginManager, UserMixin
from flask_wtf.csrf import CSRFProtect
from redis.exceptions import RedisError

import security_cache
import security_http


class User(UserMixin):
    def __init__(self, username):
        self.id = username
        self.is_admin = False
        self.must_change_password = username == "bootstrap"


@pytest.fixture
def http(monkeypatch):
    for name in (
        "MAIN_DOMAIN",
        "WWW_DOMAIN",
        "DUCKDNS_DOMAIN",
        "PUBLIC_BASE_URL",
    ):
        monkeypatch.delenv(name, raising=False)
    monkeypatch.setenv("WWW_DOMAIN", "site.example")
    app = Flask(__name__)
    app.config.update(
        TESTING=True,
        SECRET_KEY="isolated-http-tests",
        MAX_CONTENT_LENGTH=40 * 1024 * 1024,
    )
    manager = LoginManager(app)
    manager.user_loader(User)
    store = fakeredis.FakeRedis(decode_responses=True)

    @app.route("/probe", methods=["GET", "POST"])
    def probe():
        return jsonify(
            identity=security_http.guest_identity(),
            size=len(request.get_data()),
        )

    @app.post("/multipart")
    def multipart():
        return jsonify(parts=len(request.form))

    app.add_url_rule(
        "/admin/upload",
        "admin.admin_blog_new",
        probe,
        methods=["POST"],
    )
    app.add_url_rule(
        "/password/change",
        "auth.change_password",
        lambda: "change password",
    )
    app.add_url_rule("/article/<slug>", "article", lambda slug: "article")
    security_http.init_security(
        app,
        SimpleNamespace(limit=lambda _policy: lambda function: function),
    )

    @app.after_request
    def record(response):
        security_http.add_headers(response, production=True)
        return security_http.record_response(response, store)

    return SimpleNamespace(app=app, client=app.test_client(), redis=store)


def stats_fields(store):
    return {
        field
        for key in store.scan_iter("stats:*")
        if store.type(key) == "hash"
        for field in store.hkeys(key)
    }


def test_random_404_urls_share_bounded_statistics_and_expire(http):
    for index in range(120):
        response = http.client.get(f"/scanner-{index}/secret-{index}.php")
        assert response.status_code == 404
    fields = stats_fields(http.redis)
    assert len(fields) == 1
    assert not any(
        "scanner-" in field or "secret-" in field for field in fields
    )
    for key in http.redis.scan_iter("stats:*"):
        assert 0 < http.redis.ttl(key) <= security_http.STATS_TTL
    daily = list(http.redis.scan_iter("stats:daily:*"))
    assert len(daily) == 1
    assert sum(map(int, http.redis.hvals(daily[0]))) == 120


def test_invented_http_verbs_cannot_make_unlimited_statistics_fields(http):
    for index in range(80):
        response = http.client.open("/absent", method=f"X-SCAN-{index}")
        assert response.status_code == 404
    assert len(stats_fields(http.redis)) <= 10


def test_parameterized_routes_and_referrers_do_not_store_attacker_strings(
    http,
):
    for index in range(35):
        response = http.client.get(
            f"/article/private-id-{index}",
            headers={
                "Referer": f"https://random-{index}.example/secret-{index}"
            },
        )
        assert response.status_code == 200
    fields = stats_fields(http.redis)
    assert not any(
        "private-id-" in field or "random-" in field for field in fields
    )
    assert len(fields) <= 3
    for key in http.redis.scan_iter("stats:*"):
        assert http.redis.ttl(key) > 0


def test_malformed_referrer_never_breaks_response(http):
    response = http.client.get(
        "/probe", headers={"Referer": "https://[invalid"}
    )
    assert response.status_code == 200


def test_headers_and_fingerprint_cookie_cannot_change_guest_identity(http):
    address = {"REMOTE_ADDR": "203.0.113.12"}
    first = http.client.get("/probe", environ_overrides=address).json[
        "identity"
    ]
    http.client.set_cookie("fp_id", "forged-device-one")
    forged = http.client.get(
        "/probe",
        environ_overrides=address,
        headers={
            "X-Forwarded-For": "198.51.100.99",
            "X-Real-IP": "192.0.2.7",
            "Forwarded": "for=192.0.2.8",
        },
    ).json["identity"]
    http.client.set_cookie("fp_id", "forged-device-two")
    second = http.client.get("/probe", environ_overrides=address).json[
        "identity"
    ]
    assert first == forged == second
    other = http.client.get(
        "/probe",
        environ_overrides={"REMOTE_ADDR": "203.0.113.13"},
    ).json["identity"]
    assert other != first


def test_invalid_remote_address_does_not_fall_back_to_forwarded_header(http):
    identities = []
    for forwarded in ("203.0.113.1", "203.0.113.2"):
        identities.append(
            http.client.get(
                "/probe",
                environ_overrides={"REMOTE_ADDR": "invalid-address"},
                headers={"X-Forwarded-For": forwarded},
            ).json["identity"]
        )
    assert identities[0] == identities[1]


def test_body_limit_and_larger_admin_upload_exception(http):
    assert http.client.post("/probe", data=b"x" * 65536).status_code == 200
    assert http.client.post("/probe", data=b"x" * 65537).status_code == 413
    assert (
        http.client.post("/admin/upload", data=b"x" * 131072).status_code
        == 200
    )


def test_oversized_form_is_rejected_before_csrf_parses_it():
    app = Flask(__name__)
    app.config.update(
        TESTING=True,
        SECRET_KEY="isolated-csrf-test",
        MAX_CONTENT_LENGTH=40 * 1024 * 1024,
    )
    manager = LoginManager(app)
    manager.user_loader(User)
    CSRFProtect(app)
    app.add_url_rule("/submit", view_func=lambda: "ok", methods=["POST"])
    security_http.init_security(
        app,
        SimpleNamespace(limit=lambda _policy: lambda function: function),
    )
    # Parsing first would return missing-CSRF 400; the size guard must win.
    response = app.test_client().post("/submit", data={"payload": "x" * 66000})
    assert response.status_code == 413


def test_statistics_failure_does_not_break_public_response(http, monkeypatch):
    def unavailable(*_args, **_kwargs):
        raise RedisError("isolated statistics outage")

    monkeypatch.setattr(http.redis, "pipeline", unavailable)
    response = http.client.get("/probe")
    assert response.status_code == 200
    assert response.headers["X-Content-Type-Options"] == "nosniff"


def test_query_and_form_part_limits(http):
    assert http.client.get("/probe?" + "q=" + "x" * 2046).status_code == 200
    assert http.client.get("/probe?" + "q=" + "x" * 2047).status_code == 414
    response = http.client.post(
        "/multipart",
        content_type="multipart/form-data",
        data={f"part-{index}": "x" for index in range(33)},
    )
    assert response.status_code == 413


def test_cross_site_posts_and_untrusted_host_are_rejected(http):
    assert (
        http.client.post(
            "/probe",
            headers={"Sec-Fetch-Site": "cross-site"},
        ).status_code
        == 403
    )
    assert (
        http.client.get(
            "/probe",
            headers={"Host": "attacker.invalid"},
        ).status_code
        == 400
    )


def test_security_headers_cover_error_responses_and_nonces_are_fresh(http):
    responses = [http.client.get("/probe"), http.client.get("/missing")]
    nonces = []
    for response in responses:
        assert response.headers["X-Content-Type-Options"] == "nosniff"
        assert response.headers["Referrer-Policy"] == "no-referrer"
        assert "max-age=" in response.headers["Strict-Transport-Security"]
        enforced = response.headers["Content-Security-Policy"]
        assert "object-src 'none'" in enforced
        assert "base-uri 'self'" in enforced
        assert "form-action 'self'" in enforced
        report = response.headers["Content-Security-Policy-Report-Only"]
        nonces.append(re.search(r"'nonce-([^']+)'", report)[1])
    assert nonces[0] != nonces[1]


def test_authenticated_pages_are_not_cached_and_bootstrap_must_change_password(
    http,
):
    with http.client.session_transaction() as session:
        session["_user_id"] = "member"
    assert "no-store" in http.client.get("/probe").headers["Cache-Control"]
    with http.client.session_transaction() as session:
        session["_user_id"] = "bootstrap"
    response = http.client.get("/probe")
    assert response.status_code == 302
    assert response.headers["Location"].endswith("/password/change")
    assert http.client.get("/password/change").status_code == 200


def test_cache_expires_and_evicts_old_queries_without_losing_recent_hit(
    monkeypatch,
):
    clock, calls = [0], []
    monkeypatch.setattr(security_cache.time, "monotonic", lambda: clock[0])

    @security_cache.ttl_cache(ttl=10, maxsize=4)
    def weather(location):
        calls.append(location)
        return len(calls)

    first = weather("Ljubljana")
    assert weather("Ljubljana") == first
    clock[0] = 11
    assert weather("Ljubljana") != first
    for index in range(100):
        weather(f"caller-place-{index}")
    count = len(calls)
    assert weather("caller-place-99") == count
    assert len(calls) == count
    weather("caller-place-0")
    assert len(calls) == count + 1
    weather.cache_clear()
    weather("caller-place-99")
    assert len(calls) == count + 2


def test_ipv6_privacy_addresses_share_one_abuse_limit_bucket():
    app = Flask(__name__)
    with app.test_request_context(
        "/", environ_base={"REMOTE_ADDR": "2001:db8:1234:5678::1"}
    ):
        first = security_http.guest_identity()
    with app.test_request_context(
        "/",
        environ_base={"REMOTE_ADDR": "2001:db8:1234:5678:ffff:aaaa:bbbb:cccc"},
    ):
        assert security_http.guest_identity() == first
    with app.test_request_context(
        "/", environ_base={"REMOTE_ADDR": "2001:db8:1234:5679::1"}
    ):
        assert security_http.guest_identity() != first

"""Test browser device limits through the real authentication blueprint."""

import hashlib
import importlib.util
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path
from time import time
from types import ModuleType, SimpleNamespace
from unittest.mock import Mock, patch

import fakeredis
import pytest
from flask import Flask
from flask_login import LoginManager, UserMixin, current_user, login_required
from flask_login.utils import encode_cookie
from jinja2 import DictLoader
from werkzeug.security import check_password_hash, generate_password_hash

from device_sessions import DEVICE_IDLE_SECONDS, MAX_DEVICES

PASSWORD = "Correct-password-123!"


class User(UserMixin):
    def __init__(self, username):
        self.id = username


@pytest.fixture
def auth(tmp_path):
    redis = fakeredis.FakeRedis(decode_responses=True)
    utilities = ModuleType("utils")
    utilities.find_user_by_email = Mock(return_value=None)
    utilities.is_current_admin_view = Mock(return_value=False)
    utilities.redis_client = redis
    utilities.send_mail = Mock()
    utilities.users_file = str(tmp_path / "users.json")
    module_path = (
        Path(__file__).resolve().parents[1]
        / "src"
        / "blueprints"
        / "auth_bp.py"
    )
    spec = importlib.util.spec_from_file_location("device_auth", module_path)
    module = importlib.util.module_from_spec(spec)
    # Import only this blueprint, without production utils' data and clients.
    with patch.dict(sys.modules, {"utils": utilities}):
        spec.loader.exec_module(module)
    # Device-limit scenarios exceed the separate five-attempt login throttle.
    module.auth_rate_limited = Mock(return_value=False)

    password_hash = generate_password_hash(PASSWORD, method="pbkdf2:sha256:1")
    users = {
        username: {"password_hash": password_hash, "first_login": False}
        for username in ("alice", "bob")
    }
    module.init_auth_bp(users, User)
    app = Flask(__name__)
    app.config.update(
        TESTING=True,
        SECRET_KEY="device-tests-only",
        PERMANENT_SESSION_LIFETIME=timedelta(seconds=DEVICE_IDLE_SECONDS),
    )
    app.jinja_loader = DictLoader(
        {
            name: "{{ get_flashed_messages() | join(' ') }}"
            for name in (
                "login.html",
                "change_password.html",
                "reset_password.html",
            )
        }
    )
    manager = LoginManager(app)
    manager.login_view = "auth.login"
    manager.user_loader(module.load_device_user)
    app.register_blueprint(module.auth_bp)

    @app.route("/")
    @login_required
    def home():
        return current_user.id

    return SimpleNamespace(app=app, redis=redis, module=module, users=users)


def login(client, username="alice", password=PASSWORD):
    return client.post(
        "/login", data={"username": username, "password": password}
    )


def device_id(client):
    with client.session_transaction() as session:
        return session["device_id"]


def assert_logged_out(client):
    assert client.get("/").status_code == 302
    with client.session_transaction() as session:
        assert "_user_id" not in session
        assert "device_id" not in session
    assert client.get_cookie("remember_token") is None


def test_setup_token_keeps_own_expiry_when_reset_token_expires(auth):
    setup_token = "setup-token"
    reset_token = "reset-token"
    user = auth.users["alice"]
    user.update(
        setup_token_hash=hashlib.sha256(setup_token.encode()).hexdigest(),
        setup_expiry=(
            datetime.now(timezone.utc) + timedelta(days=1)
        ).isoformat(),
        reset_token_hash=hashlib.sha256(reset_token.encode()).hexdigest(),
        reset_expiry=(
            datetime.now(timezone.utc) - timedelta(seconds=1)
        ).isoformat(),
        must_set_password=True,
    )
    client = auth.app.test_client()

    assert client.get(f"/password/reset/{setup_token}").status_code == 200
    assert client.get(f"/password/reset/{reset_token}").status_code == 400
    assert "setup_token_hash" in user
    assert "setup_expiry" in user
    assert "reset_token_hash" not in user


def test_sixth_browser_denied_until_another_browser_logs_out(auth):
    clients = [auth.app.test_client() for _ in range(MAX_DEVICES + 1)]
    for client in clients[:-1]:
        assert login(client).status_code == 302
        assert client.get("/").data == b"alice"
        with client.session_transaction() as session:
            assert session.permanent
        assert client.get_cookie("remember_token") is None
    ids = {device_id(client) for client in clients[:-1]}
    assert len(ids) == MAX_DEVICES
    key = auth.module.device_sessions.key("alice")
    assert set(auth.redis.zrange(key, 0, -1)) == ids

    denied = login(clients[-1])
    assert denied.status_code in (200, 403)
    message = denied.get_data(as_text=True).lower()
    assert str(MAX_DEVICES) in message
    assert "odjav" in message
    assert_logged_out(clients[-1])
    assert auth.redis.zcard(key) == MAX_DEVICES

    assert clients[0].get("/logout").status_code == 302
    assert auth.redis.zcard(key) == MAX_DEVICES - 1
    assert login(clients[-1]).status_code == 302
    assert clients[-1].get("/").data == b"alice"
    assert auth.redis.zcard(key) == MAX_DEVICES


def test_login_again_replaces_same_browser_device_even_at_limit(auth):
    clients = [auth.app.test_client() for _ in range(MAX_DEVICES)]
    for client in clients:
        assert login(client).status_code == 302
    original_id = device_id(clients[0])
    old_cookie = clients[0].get_cookie("session").value

    assert login(clients[0]).status_code == 302

    assert device_id(clients[0]) != original_id
    key = auth.module.device_sessions.key("alice")
    assert auth.redis.zcard(key) == MAX_DEVICES
    replay = auth.app.test_client()
    replay.set_cookie("session", old_cookie)
    assert_logged_out(replay)
    assert clients[0].get("/").data == b"alice"


def test_wrong_password_does_not_consume_device_slot(auth):
    client = auth.app.test_client()

    assert login(client, password="wrong").status_code == 200

    assert auth.redis.zcard(auth.module.device_sessions.key("alice")) == 0
    assert_logged_out(client)


def test_thirty_days_without_activity_frees_slot_and_old_cookie_is_denied(
    auth,
):
    clients = [auth.app.test_client() for _ in range(MAX_DEVICES + 1)]
    for client in clients[:-1]:
        assert login(client).status_code == 302
    expired_id = device_id(clients[0])
    key = auth.module.device_sessions.key("alice")
    auth.redis.zadd(key, {expired_id: time() - DEVICE_IDLE_SECONDS - 1})

    assert login(clients[-1]).status_code == 302

    assert auth.redis.zscore(key, expired_id) is None
    assert auth.redis.zcard(key) == MAX_DEVICES
    assert_logged_out(clients[0])
    assert auth.redis.zcard(key) == MAX_DEVICES


def test_requests_extend_device_activity(auth):
    client = auth.app.test_client()
    assert login(client).status_code == 302
    key = auth.module.device_sessions.key("alice")
    identifier = device_id(client)
    old_activity = time() - DEVICE_IDLE_SECONDS + 60
    auth.redis.zadd(key, {identifier: old_activity})

    assert client.get("/").data == b"alice"

    assert auth.redis.zscore(key, identifier) > old_activity
    assert auth.redis.ttl(key) >= DEVICE_IDLE_SECONDS - 1


def test_logout_revokes_copied_session_cookie(auth):
    client = auth.app.test_client()
    assert login(client).status_code == 302
    copied_cookie = client.get_cookie("session").value
    assert client.get("/logout").status_code == 302
    client.set_cookie("session", copied_cookie)

    assert_logged_out(client)
    assert auth.redis.zcard(auth.module.device_sessions.key("alice")) == 0


def test_fresh_password_login_cannot_revive_copied_expired_cookie(auth):
    client = auth.app.test_client()
    assert login(client).status_code == 302
    expired_id = device_id(client)
    copied_cookie = client.get_cookie("session").value
    key = auth.module.device_sessions.key("alice")
    auth.redis.zadd(key, {expired_id: time() - DEVICE_IDLE_SECONDS - 1})

    assert login(client).status_code == 302

    assert device_id(client) != expired_id
    assert client.get("/").data == b"alice"
    replay = auth.app.test_client()
    replay.set_cookie("session", copied_cookie)
    assert_logged_out(replay)
    assert auth.redis.zcard(key) == 1


@pytest.mark.parametrize("legacy_session", [False, True])
def test_legacy_remember_cookie_cannot_bypass_device_registration(
    auth, legacy_session
):
    client = auth.app.test_client()
    if legacy_session:
        with client.session_transaction() as session:
            session["_user_id"] = "alice"
            session["_fresh"] = True
    with auth.app.app_context():
        remember_cookie = encode_cookie("alice")
    client.set_cookie("remember_token", remember_cookie)

    assert_logged_out(client)
    assert_logged_out(client)
    assert auth.redis.zcard(auth.module.device_sessions.key("alice")) == 0


def test_account_switch_denial_preserves_previous_login_and_slot(auth):
    client = auth.app.test_client()
    assert login(client).status_code == 302
    original_id = device_id(client)
    for _ in range(MAX_DEVICES):
        assert login(auth.app.test_client(), "bob").status_code == 302

    response = login(client, "bob")

    assert response.status_code in (200, 403)
    assert client.get("/").data == b"alice"
    assert device_id(client) == original_id
    assert auth.redis.zcard(auth.module.device_sessions.key("alice")) == 1
    key = auth.module.device_sessions.key("bob")
    assert auth.redis.zcard(key) == MAX_DEVICES


def test_successful_account_switch_releases_previous_account_slot(auth):
    client = auth.app.test_client()
    assert login(client).status_code == 302

    assert login(client, "bob").status_code == 302

    assert client.get("/").data == b"bob"
    assert auth.redis.zcard(auth.module.device_sessions.key("alice")) == 0
    assert auth.redis.zcard(auth.module.device_sessions.key("bob")) == 1


def test_password_change_logs_out_and_frees_current_device_slot(auth):
    client = auth.app.test_client()
    assert login(client).status_code == 302
    new_password = "Different-password-456!"

    response = client.post(
        "/password/change",
        data={
            "current_password": PASSWORD,
            "password": new_password,
            "password_confirm": new_password,
        },
    )

    assert response.status_code == 302
    assert check_password_hash(
        auth.users["alice"]["password_hash"], new_password
    )
    assert_logged_out(client)
    assert auth.redis.zcard(auth.module.device_sessions.key("alice")) == 0

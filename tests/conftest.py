"""
Pytest configuration and fixtures for MarinKino tests
"""

import json
import os
import sys
import tempfile
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
from werkzeug.security import generate_password_hash

# Add src to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from app import app
from utils import User, redis_client, users


@pytest.fixture
def client(monkeypatch):
    """Create a test client with app context"""
    app.config["TESTING"] = True
    app.config["WTF_CSRF_ENABLED"] = False

    # Disable rate limiting for tests
    app.config["RATELIMIT_ENABLED"] = False

    with app.test_client() as client:
        with app.app_context():
            yield client


@pytest.fixture
def runner():
    """Create a CLI runner"""
    return app.test_cli_runner()


@pytest.fixture
def test_users():
    """Create test users"""
    return {
        "admin_user": {
            "password_hash": generate_password_hash("admin123"),
            "emails": ["admin@example.com"],
            "incoming_date": "2024-01-01",
            "is_admin": True,
        },
        "regular_user": {
            "password_hash": generate_password_hash("user123"),
            "emails": ["user@example.com"],
            "incoming_date": "2024-01-15",
        },
        "test_user_2": {
            "password_hash": generate_password_hash("test123"),
            "emails": ["test2@example.com"],
            "incoming_date": "2024-02-01",
        },
    }


@pytest.fixture
def mock_redis(monkeypatch):
    """Mock redis client"""
    mock_client = MagicMock()
    mock_client.hgetall = MagicMock(return_value={})
    mock_client.hget = MagicMock(return_value=None)
    mock_client.hset = MagicMock(return_value=1)
    mock_client.hincrby = MagicMock(return_value=1)
    mock_client.incr = MagicMock(return_value=1)
    mock_client.exists = MagicMock(return_value=0)
    mock_client.expire = MagicMock(return_value=1)
    mock_client.keys = MagicMock(return_value=[])
    mock_client.scan_iter = MagicMock(return_value=[])

    # Patch redis_client in utils module (imported from there in blueprints)
    monkeypatch.setattr("utils.redis_client", mock_client)

    return mock_client


@pytest.fixture
def mock_send_mail(monkeypatch):
    """Mock send_mail function"""
    mock_mail = MagicMock(return_value=True)
    # Don't try to patch as blueprint attribute - it will be set via init functions
    return mock_mail


@pytest.fixture
def mock_requests(monkeypatch):
    """Mock requests library"""
    mock_post = MagicMock(return_value=MagicMock(status_code=200))
    monkeypatch.setattr("requests.post", mock_post)
    return mock_post


@pytest.fixture
def mock_users(monkeypatch, test_users, mock_send_mail):
    """Mock users data with test users and initialize blueprints"""
    from blueprints.admin_bp import init_admin_bp
    from blueprints.auth_bp import init_auth_bp
    from blueprints.misc_bp import init_misc_bp

    additional_users = test_users.copy()
    new_users = {**additional_users, **users}

    # Mock User class to add is_admin property
    class MockUser(User):
        def __init__(self, user_id):
            super().__init__(user_id)
            self.is_admin = new_users.get(user_id, {}).get("is_admin", False)

    # Patch User class in utils module
    monkeypatch.setattr("utils.User", MockUser)

    # Initialize blueprints with test data
    init_auth_bp(new_users, MockUser, mock_send_mail)
    init_admin_bp(new_users)
    init_misc_bp(new_users, mock_send_mail)

    return users


@pytest.fixture
def authenticated_client(client, mock_users, mock_redis):
    """Create an authenticated test client with regular user"""
    with client.session_transaction() as sess:
        sess["_user_id"] = "regular_user"
    return client


@pytest.fixture
def admin_client(client, mock_users, mock_redis):
    """Create an authenticated test client with admin user"""
    with client.session_transaction() as sess:
        sess["_user_id"] = "admin_user"
    return client

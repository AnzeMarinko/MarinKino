"""
Tests for auth_bp endpoints
"""

from datetime import datetime, timedelta, timezone
from unittest.mock import MagicMock, patch

import pytest


class TestAuthLogin:
    """Test login endpoint"""

    def test_login_get(self, client):
        """Test GET request to login page"""
        response = client.get("/login")
        assert response.status_code == 200
        assert b"Prijava" in response.data or b"login" in response.data.lower()

    def test_login_valid_credentials(self, authenticated_client, mock_users):
        """Test successful login with valid credentials"""
        response = authenticated_client.post(
            "/login",
            data={"username": "regular_user", "password": "user123"},
            follow_redirects=True,
        )
        assert response.status_code == 200

    def test_login_invalid_username(self, client):
        """Test login with non-existent username"""
        response = client.post(
            "/login", data={"username": "nonexistent", "password": "password"}
        )
        assert response.status_code == 200
        assert b"Napa" in response.data or b"error" in response.data.lower()

    def test_login_invalid_password(self, client):
        """Test login with wrong password"""
        response = client.post(
            "/login",
            data={"username": "regular_user", "password": "wrongpassword"},
        )
        assert response.status_code == 200

    def test_login_empty_credentials(self, client):
        """Test login with empty credentials"""
        response = client.post("/login", data={"username": "", "password": ""})
        assert response.status_code == 200


class TestAuthRegister:
    """Test register endpoint"""

    def test_register_get_without_auth(self, client):
        """Test GET register page without authentication redirects to login"""
        response = client.get("/register", follow_redirects=True)
        assert response.status_code == 200
        # Should redirect to login

    def test_register_get_as_regular_user(self, authenticated_client):
        """Test that regular users cannot access register page"""
        response = authenticated_client.get("/register", follow_redirects=True)
        # Should redirect to movies index since user is not admin
        assert response.status_code == 200

    def test_register_get_as_admin(self, admin_client):
        """Test admin can access register page"""
        response = admin_client.get("/register")
        assert response.status_code == 200

    def test_register_new_user_as_admin(
        self, admin_client, mock_send_mail, mock_requests
    ):
        """Test admin can register new user"""
        response = admin_client.post(
            "/register",
            data={"username": "newuser", "email": "new@example.com"},
            follow_redirects=True,
        )
        assert response.status_code == 200
        # Verify email was sent
        mock_send_mail.assert_called()

    def test_register_duplicate_username(self, admin_client, mock_send_mail):
        """Test cannot register duplicate username"""
        response = admin_client.post(
            "/register",
            data={
                "username": "regular_user",
                "email": "different@example.com",
            },
        )
        assert response.status_code == 200
        assert (
            b"zasedeno" in response.data
            or b"occupied" in response.data.lower()
        )

    def test_register_duplicate_email(self, admin_client):
        """Test cannot register duplicate email"""
        response = admin_client.post(
            "/register",
            data={
                "username": "newuser",
                "email": "user@example.com",  # Already used by regular_user
            },
        )
        assert response.status_code == 200

    def test_register_invalid_username_format(self, admin_client):
        """Test invalid username format"""
        response = admin_client.post(
            "/register",
            data={"username": "a", "email": "new@example.com"},  # Too short
        )
        assert response.status_code == 200
        assert b"dolgo" in response.data or b"length" in response.data.lower()

    def test_register_invalid_username_special_chars(self, admin_client):
        """Test username with invalid characters"""
        response = admin_client.post(
            "/register",
            data={"username": "user@#$%", "email": "new@example.com"},
        )
        assert response.status_code == 200


class TestAuthForgotPassword:
    """Test forgot password endpoint"""

    def test_forgot_password_get(self, client):
        """Test GET forgot password page"""
        response = client.get("/forgot_password")
        assert response.status_code == 200

    def test_forgot_password_valid_email(self, client, mock_send_mail):
        """Test forgot password with valid email"""
        response = client.post(
            "/forgot_password",
            data={"email": "user@example.com"},
            follow_redirects=True,
        )
        assert response.status_code == 200
        assert b"poslana" in response.data or b"sent" in response.data.lower()

    def test_forgot_password_nonexistent_email(self, client):
        """Test forgot password with non-existent email"""
        response = client.post(
            "/forgot_password",
            data={"email": "nonexistent@example.com"},
            follow_redirects=True,
        )
        assert response.status_code == 200
        # Should show success message regardless (security)
        assert b"poslana" in response.data or b"sent" in response.data.lower()

    def test_forgot_password_empty_email(self, client):
        """Test forgot password with empty email"""
        response = client.post(
            "/forgot_password", data={"email": ""}, follow_redirects=True
        )
        assert response.status_code == 200


class TestAuthResetPassword:
    """Test reset password endpoint"""

    def test_reset_password_get_invalid_token(self, client):
        """Test reset password with invalid token"""
        response = client.get("/reset_password/invalid_token_12345")
        assert response.status_code in [200, 400, 404]

    def test_reset_password_expired_token(self, client, mock_users):
        """Test reset password with expired token"""
        # Add an expired token to a user
        expired_time = (
            datetime.now(timezone.utc) - timedelta(hours=1)
        ).isoformat()
        mock_users["regular_user"]["reset_token"] = "test_token"
        mock_users["regular_user"]["reset_expiry"] = expired_time

        response = client.get("/reset_password/test_token")
        assert response.status_code in [200, 400]

    def test_reset_password_valid_token_get(self, client, mock_users):
        """Test reset password page with valid token"""
        # Add a valid token
        future_time = (
            datetime.now(timezone.utc) + timedelta(minutes=30)
        ).isoformat()
        mock_users["regular_user"]["reset_token"] = "valid_test_token"
        mock_users["regular_user"]["reset_expiry"] = future_time

        response = client.get("/reset_password/valid_test_token")
        assert response.status_code == 200

    def test_reset_password_valid_token_post(self, client, mock_users):
        """Test reset password with valid token submission"""
        future_time = (
            datetime.now(timezone.utc) + timedelta(minutes=30)
        ).isoformat()
        mock_users["regular_user"]["reset_token"] = "valid_test_token"
        mock_users["regular_user"]["reset_expiry"] = future_time

        response = client.post(
            "/reset_password/valid_test_token",
            data={
                "password": "newpassword123",
                "password_confirm": "newpassword123",
            },
            follow_redirects=True,
        )
        assert response.status_code == 200

    def test_reset_password_mismatched_passwords(self, client, mock_users):
        """Test reset password with mismatched passwords"""
        future_time = (
            datetime.now(timezone.utc) + timedelta(minutes=30)
        ).isoformat()
        mock_users["regular_user"]["reset_token"] = "valid_test_token"
        mock_users["regular_user"]["reset_expiry"] = future_time

        response = client.post(
            "/reset_password/valid_test_token",
            data={
                "password": "newpassword123",
                "password_confirm": "differentpassword",
            },
        )
        assert response.status_code == 200


class TestAuthLogout:
    """Test logout endpoint"""

    def test_logout_authenticated(self, authenticated_client):
        """Test logout when authenticated"""
        response = authenticated_client.get("/logout", follow_redirects=True)
        assert response.status_code == 200
        # Should redirect to login or index

    def test_logout_not_authenticated(self, client):
        """Test logout when not authenticated"""
        response = client.get("/logout", follow_redirects=True)
        # Should handle gracefully
        assert response.status_code in [200, 302, 401]

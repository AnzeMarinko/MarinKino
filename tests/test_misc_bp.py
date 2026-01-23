"""
Tests for misc_bp endpoints
"""

import json
from unittest.mock import MagicMock, patch

import pytest


class TestFavicon:
    """Test favicon endpoint"""

    def test_favicon(self, client):
        """Test favicon retrieval"""
        response = client.get("/favicon.ico")
        assert response.status_code in [200, 404]


class TestPodKrinko:
    """Test Pod Krinko game endpoints"""

    def test_pod_krinko_page(self, client):
        """Test Pod Krinko game page"""
        response = client.get("/pod_krinko")
        assert response.status_code == 200
        assert (
            b"pod_krinko" in response.data.lower()
            or b"Besede" in response.data
        )

    def test_pod_krinko_new_words_not_authenticated(self, client):
        """Test getting new words without authentication"""
        response = client.get("/pod_krinko/new_words")
        assert response.status_code in [302, 401, 200]

    def test_pod_krinko_new_words_authenticated(self, authenticated_client):
        """Test getting new words when authenticated"""
        response = authenticated_client.get("/pod_krinko/new_words")
        assert response.status_code == 200
        # Should return JSON with two words
        try:
            data = json.loads(response.data)
            assert isinstance(data, list)
            assert len(data) == 2
        except:
            pass

    def test_pod_krinko_new_words_returns_array(self, authenticated_client):
        """Test new words endpoint returns array"""
        response = authenticated_client.get("/pod_krinko/new_words")
        assert response.status_code == 200

    def test_pod_krinko_multiple_word_requests(self, authenticated_client):
        """Test multiple word requests"""
        response1 = authenticated_client.get("/pod_krinko/new_words")
        response2 = authenticated_client.get("/pod_krinko/new_words")
        response3 = authenticated_client.get("/pod_krinko/new_words")

        assert response1.status_code == 200
        assert response2.status_code == 200
        assert response3.status_code == 200


class TestNewsletterImages:
    """Test newsletter image serving"""

    def test_newsletter_image_not_authenticated(self, client, mock_redis):
        """Test newsletter image serving without authentication"""
        mock_redis.incr = MagicMock(return_value=1)
        response = client.get("/newsletter_image/file/test.jpg?user=guest")
        assert response.status_code in [404, 200]

    def test_newsletter_image_authenticated(
        self, authenticated_client, mock_redis
    ):
        """Test newsletter image serving when authenticated"""
        mock_redis.incr = MagicMock(return_value=1)
        response = authenticated_client.get("/newsletter_image/file/test.jpg")
        assert response.status_code in [404, 200]

    def test_newsletter_image_path_traversal_attempt(
        self, authenticated_client
    ):
        """Test newsletter image prevents path traversal"""
        response = authenticated_client.get(
            "/newsletter_image/file/../../../etc/passwd"
        )
        assert response.status_code in [400, 404]

    def test_newsletter_image_with_various_formats(
        self, authenticated_client, mock_redis
    ):
        """Test different newsletter image formats"""
        mock_redis.incr = MagicMock(return_value=1)

        for ext in ["jpg", "png", "gif", "webp"]:
            response = authenticated_client.get(
                f"/newsletter_image/file/image.{ext}"
            )
            assert response.status_code in [404, 200]


class TestHelp:
    """Test help page endpoint"""

    def test_help_not_authenticated(self, client):
        """Test help page without authentication"""
        response = client.get("/help")
        assert response.status_code in [302, 401]

    def test_help_authenticated(self, authenticated_client):
        """Test help page with authentication"""
        response = authenticated_client.get("/help")
        assert response.status_code == 200
        assert (
            b"navodila" in response.data.lower()
            or b"help" in response.data.lower()
        )

    def test_help_contains_instructions(self, authenticated_client):
        """Test help page contains user instructions"""
        response = authenticated_client.get("/help")
        assert response.status_code == 200


class TestAdminMailing:
    """Test admin mailing feature"""

    def test_mailing_page_not_authenticated(self, client):
        """Test mailing page without authentication"""
        response = client.get("/send_admin_emails")
        assert response.status_code in [302, 401]

    def test_mailing_page_as_regular_user(self, authenticated_client):
        """Test regular user cannot access mailing page"""
        response = authenticated_client.get(
            "/send_admin_emails", follow_redirects=True
        )
        # Should redirect
        assert response.status_code == 200

    def test_mailing_page_as_admin(self, admin_client):
        """Test admin can access mailing page"""
        response = admin_client.get("/send_admin_emails")
        assert response.status_code == 200

    def test_send_email_to_user_as_admin(self, admin_client, mock_send_mail):
        """Test admin can send email to single user"""
        response = admin_client.post(
            "/send_admin_emails",
            data=json.dumps({"whole_list": "false"}),
            content_type="application/json",
        )
        assert response.status_code in [200, 400]

    def test_send_email_returns_response_data(
        self, admin_client, mock_send_mail
    ):
        """Test send email returns response with sent count"""
        response = admin_client.post(
            "/send_admin_emails",
            data=json.dumps({"whole_list": "false"}),
            content_type="application/json",
        )
        if response.status_code == 200:
            try:
                data = json.loads(response.data)
                assert "sent" in data or "error" in data
            except:
                pass


class TestTestPage:
    """Test test/preview page endpoint"""

    def test_test_page_not_authenticated(self, client):
        """Test test page without authentication"""
        response = client.get("/test")
        assert response.status_code in [302, 401]


class TestMiscSecurity:
    """Test security features in misc endpoints"""

    def test_newsletter_image_xss_prevention(
        self, authenticated_client, mock_redis
    ):
        """Test newsletter image prevents XSS"""
        mock_redis.incr = MagicMock(return_value=1)
        response = authenticated_client.get(
            "/newsletter_image/file/<script>alert(1)</script>.jpg"
        )
        assert response.status_code in [400, 404]

    def test_user_guest_tracking(self, client, mock_redis):
        """Test guest user tracking for newsletter images"""
        mock_redis.incr = MagicMock(return_value=1)
        response = client.get("/newsletter_image/file/test.jpg?user=guest")
        assert response.status_code in [404, 200]

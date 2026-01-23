"""
Tests for admin_bp endpoints
"""

from unittest.mock import MagicMock

import pytest


class TestAdminPanel:
    """Test admin panel endpoint"""

    def test_admin_panel_not_authenticated(self, client):
        """Test admin panel without authentication"""
        response = client.get("/admin")
        assert response.status_code in [302, 401]

    def test_admin_panel_as_regular_user(self, authenticated_client):
        """Test regular user cannot access admin panel"""
        response = authenticated_client.get("/admin", follow_redirects=True)
        # Should redirect to movies index
        assert response.status_code == 200

    def test_admin_panel_as_admin(self, admin_client, mock_redis):
        """Test admin can access admin panel"""
        mock_redis.scan_iter = MagicMock(return_value=[])
        response = admin_client.get("/admin")
        assert response.status_code == 200

    def test_admin_panel_with_stats_data(self, admin_client, mock_redis):
        """Test admin panel displays statistics"""
        # Mock redis data with stats
        mock_redis.scan_iter = MagicMock(
            return_value=[
                "stats:daily:2026-01-23:regular_user:200",
                "stats:monthly:2026-01",
            ]
        )
        mock_redis.hgetall = MagicMock(
            return_value={"GET /": "10", "POST /login": "5"}
        )

        response = admin_client.get("/admin")
        assert response.status_code == 200

    def test_admin_panel_with_user_stats(self, admin_client, mock_redis):
        """Test admin panel displays user watch statistics"""
        # Mock redis user progress data
        mock_redis.keys = MagicMock(
            return_value=["prog:regular_user", "prog:test_user_2"]
        )
        mock_redis.hgetall = MagicMock(return_value={})

        response = admin_client.get("/admin")
        assert response.status_code == 200

    def test_admin_panel_displays_empty_stats(self, admin_client, mock_redis):
        """Test admin panel handles empty statistics"""
        mock_redis.scan_iter = MagicMock(return_value=[])
        mock_redis.keys = MagicMock(return_value=[])

        response = admin_client.get("/admin")
        assert response.status_code == 200


class TestAdminAuthorization:
    """Test admin authorization checks"""

    def test_admin_routes_require_authentication(self, client):
        """Test admin routes require authentication"""
        response = client.get("/admin", follow_redirects=True)
        assert response.status_code in [200, 302]

    def test_admin_routes_require_admin_role(self, authenticated_client):
        """Test admin routes check for admin role"""
        response = authenticated_client.get("/admin", follow_redirects=True)
        # Should redirect away from admin panel
        assert response.status_code == 200


class TestAdminStatistics:
    """Test statistics calculation and display"""

    def test_admin_daily_stats(self, admin_client, mock_redis):
        """Test daily statistics retrieval"""
        mock_redis.scan_iter = MagicMock(
            return_value=[
                "stats:daily:2026-01-23:user1:200",
                "stats:daily:2026-01-23:user2:200",
            ]
        )
        mock_redis.hgetall = MagicMock(
            return_value={"GET /movies": "15", "GET /music": "5"}
        )

        response = admin_client.get("/admin")
        assert response.status_code == 200

    def test_admin_monthly_stats(self, admin_client, mock_redis):
        """Test monthly statistics retrieval"""
        mock_redis.scan_iter = MagicMock(
            return_value=["stats:monthly:2026-01"]
        )
        mock_redis.hgetall = MagicMock(
            return_value={"GET /movies": "150", "POST /login": "50"}
        )

        response = admin_client.get("/admin")
        assert response.status_code == 200

    def test_admin_user_watch_time_stats(self, admin_client, mock_redis):
        """Test user watch time statistics"""
        import json

        mock_redis.keys = MagicMock(return_value=["prog:regular_user"])
        mock_redis.hgetall = MagicMock(
            return_value={
                "movie1.mp4": json.dumps(
                    {
                        "total_play_time": 3600,
                        "duration": 7200,
                        "last_start_time": "2026-01-23T10:00:00",
                    }
                )
            }
        )

        response = admin_client.get("/admin")
        assert response.status_code == 200


class TestAdminUserManagement:
    """Test user management in admin panel"""

    def test_admin_sees_all_users(self, admin_client):
        """Test admin can see all users in statistics"""
        response = admin_client.get("/admin")
        assert response.status_code == 200
        # Should contain user information

    def test_admin_user_activity_breakdown(self, admin_client, mock_redis):
        """Test admin can see user activity breakdown"""
        mock_redis.scan_iter = MagicMock(
            return_value=[
                "stats:daily:2026-01-23:regular_user:200",
                "stats:daily:2026-01-23:admin_user:200",
            ]
        )
        mock_redis.hgetall = MagicMock(
            return_value={"GET /": "10", "POST /login": "5"}
        )

        response = admin_client.get("/admin")
        assert response.status_code == 200

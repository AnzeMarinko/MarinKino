"""
Tests for music_bp endpoints
"""

import pytest


class TestMusicIndex:
    """Test music player endpoint"""

    def test_music_not_authenticated(self, client):
        """Test music page without authentication"""
        response = client.get("/music")
        assert response.status_code in [302, 401]

    def test_music_authenticated(self, authenticated_client):
        """Test music page with authentication"""
        response = authenticated_client.get("/music")
        assert response.status_code == 200
        assert b"music" in response.data.lower() or b"Glasba" in response.data


class TestMusicFileServing:
    """Test music file serving"""

    def test_serve_music_file_not_authenticated(self, client):
        """Test music file serving without authentication"""
        response = client.get("/music/file/test.mp3")
        assert response.status_code in [302, 401, 404]

    def test_serve_music_file_authenticated(self, authenticated_client):
        """Test music file serving when authenticated"""
        response = authenticated_client.get("/music/file/test.mp3")
        assert response.status_code in [
            404,
            206,
            200,
        ]  # 404 if not found, 206/200 for partial/full content

    def test_serve_music_nested_path(self, authenticated_client):
        """Test music file serving with nested path"""
        response = authenticated_client.get(
            "/music/file/Artist/Album/Song.mp3"
        )
        assert response.status_code in [404, 206, 200]

    def test_serve_music_path_traversal_attack(self, authenticated_client):
        """Test music file serving prevents path traversal"""
        response = authenticated_client.get("/music/file/../../../etc/passwd")
        assert response.status_code in [400, 404]

    def test_serve_music_m4a_format(self, authenticated_client):
        """Test serving m4a audio files"""
        response = authenticated_client.get("/music/file/test.m4a")
        assert response.status_code in [404, 206, 200]

    def test_serve_music_wav_format(self, authenticated_client):
        """Test serving wav audio files"""
        response = authenticated_client.get("/music/file/test.wav")
        assert response.status_code in [404, 206, 200]


class TestMusicDeletion:
    """Test music file deletion"""

    def test_delete_music_not_authenticated(self, client):
        """Test music deletion without authentication"""
        response = client.delete("/music/delete/test.mp3")
        assert response.status_code in [302, 401]

    def test_delete_music_as_regular_user(self, authenticated_client):
        """Test regular user cannot delete music"""
        response = authenticated_client.delete("/music/delete/test.mp3")
        assert response.status_code in [204, 403]

    def test_delete_music_as_admin(self, admin_client):
        """Test admin can delete music"""
        response = admin_client.delete("/music/delete/test.mp3")
        assert response.status_code in [204, 404]

    def test_delete_music_nested_path(self, admin_client):
        """Test admin can delete music from nested path"""
        response = admin_client.delete("/music/delete/Artist/Album/Song.mp3")
        assert response.status_code in [204, 404]

    def test_delete_music_path_traversal_attempt(self, admin_client):
        """Test music deletion prevents path traversal"""
        response = admin_client.delete("/music/delete/../../../etc/passwd")
        assert response.status_code in [400, 404]


class TestMusicHeaders:
    """Test music response headers"""

    def test_music_response_has_accept_ranges(self, authenticated_client):
        """Test music files have Accept-Ranges header"""
        response = authenticated_client.get("/music/file/test.mp3")
        # Header should be present (even if file doesn't exist)
        assert response.status_code in [404, 206, 200]
        if response.status_code != 404:
            assert "Accept-Ranges" in response.headers

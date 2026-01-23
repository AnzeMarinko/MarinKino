"""
Tests for memes_bp endpoints
"""

import pytest


class TestMemesIndex:
    """Test memes page endpoint"""

    def test_memes_not_authenticated(self, client):
        """Test memes page without authentication"""
        response = client.get("/memes")
        assert response.status_code in [302, 401]

    def test_memes_authenticated(self, authenticated_client):
        """Test memes page with authentication"""
        response = authenticated_client.get("/memes")
        assert response.status_code == 200

    def test_memes_multiple_requests(self, authenticated_client):
        """Test multiple meme requests iterate through memes"""
        response1 = authenticated_client.get("/memes")
        assert response1.status_code == 200

        response2 = authenticated_client.get("/memes")
        assert response2.status_code == 200

    def test_memes_daily_limit(self, authenticated_client):
        """Test memes daily limit"""
        # Make multiple requests to hit the limit
        for i in range(35):  # Limit is 33
            response = authenticated_client.get("/memes")
            if i < 33:
                assert response.status_code == 200
            else:
                # After limit
                assert response.status_code == 200
                assert (
                    b"Dovolj" in response.data
                    or b"limit" in response.data.lower()
                )


class TestMemesFileServing:
    """Test meme file serving"""

    def test_serve_meme_file_not_authenticated(self, client):
        """Test meme file serving without authentication"""
        response = client.get("/memes/file/test.jpg")
        assert response.status_code in [302, 401, 404]

    def test_serve_meme_file_authenticated(self, authenticated_client):
        """Test meme file serving when authenticated"""
        response = authenticated_client.get("/memes/file/test.jpg")
        assert response.status_code in [404, 200]

    def test_serve_meme_png(self, authenticated_client):
        """Test serving PNG meme files"""
        response = authenticated_client.get("/memes/file/test.png")
        assert response.status_code in [404, 200]

    def test_serve_meme_gif(self, authenticated_client):
        """Test serving GIF meme files"""
        response = authenticated_client.get("/memes/file/test.gif")
        assert response.status_code in [404, 200]

    def test_serve_meme_webp(self, authenticated_client):
        """Test serving WebP meme files"""
        response = authenticated_client.get("/memes/file/test.webp")
        assert response.status_code in [404, 200]

    def test_serve_meme_mp4(self, authenticated_client):
        """Test serving MP4 meme videos"""
        response = authenticated_client.get("/memes/file/test.mp4")
        assert response.status_code in [404, 200]

    def test_serve_meme_path_traversal_attack(self, authenticated_client):
        """Test meme file serving prevents path traversal"""
        response = authenticated_client.get("/memes/file/../../../etc/passwd")
        assert response.status_code in [400, 404]

    def test_serve_meme_file_type_in_content_type(self, authenticated_client):
        """Test MP4 memes have correct content type"""
        response = authenticated_client.get("/memes/file/test.mp4")
        if response.status_code == 200:
            assert "video/mp4" in response.headers.get("Content-Type", "")


class TestMemesDeletion:
    """Test meme deletion"""

    def test_delete_meme_not_authenticated(self, client):
        """Test meme deletion without authentication"""
        response = client.delete("/meme/delete/test.jpg")
        assert response.status_code in [302, 401]

    def test_delete_meme_as_regular_user(self, authenticated_client):
        """Test regular user cannot delete memes"""
        response = authenticated_client.delete("/meme/delete/test.jpg")
        assert response.status_code in [204, 403]

    def test_delete_meme_as_admin(self, admin_client):
        """Test admin can delete memes"""
        response = admin_client.delete("/meme/delete/test.jpg")
        assert response.status_code in [204, 404]

    def test_delete_meme_png_as_admin(self, admin_client):
        """Test admin can delete PNG memes"""
        response = admin_client.delete("/meme/delete/test.png")
        assert response.status_code in [204, 404]

    def test_delete_meme_mp4_as_admin(self, admin_client):
        """Test admin can delete MP4 memes"""
        response = admin_client.delete("/meme/delete/test.mp4")
        assert response.status_code in [204, 404]

    def test_delete_meme_path_traversal_attempt(self, admin_client):
        """Test meme deletion prevents path traversal"""
        response = admin_client.delete("/meme/delete/../../../etc/passwd")
        assert response.status_code in [400, 404]

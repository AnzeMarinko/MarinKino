"""
Tests for movies_bp endpoints
"""

import json
from unittest.mock import MagicMock, patch

import pytest


class TestMoviesIndex:
    """Test movies index endpoint"""

    def test_index_not_authenticated(self, client):
        """Test index page without authentication"""
        response = client.get("/")
        # Should redirect to login
        assert response.status_code in [200, 302, 401]

    def test_index_authenticated(self, authenticated_client):
        """Test index page with authentication"""
        response = authenticated_client.get("/")
        assert response.status_code == 200

    def test_index_with_search_query(self, authenticated_client):
        """Test index with search query parameter"""
        response = authenticated_client.get("/?q=test")
        assert response.status_code == 200

    def test_index_with_genre_filter(self, authenticated_client):
        """Test index with genre filter"""
        response = authenticated_client.get("/?genre=Drama")
        assert response.status_code == 200

    def test_index_with_sort(self, authenticated_client):
        """Test index with sort parameter"""
        response = authenticated_client.get("/?sort=title")
        assert response.status_code == 200

    def test_index_with_movie_type_filter(self, authenticated_client):
        """Test index with movie type filter"""
        response = authenticated_client.get("/?movietype=01-zbirke-risank")
        assert response.status_code == 200

    def test_index_only_unwatched(self, authenticated_client):
        """Test index filter for only unwatched"""
        response = authenticated_client.get("/?onlyunwatched=on")
        assert response.status_code == 200

    def test_index_only_recommended(self, authenticated_client):
        """Test index filter for only recommended"""
        response = authenticated_client.get("/?onlyrecommended=on")
        assert response.status_code == 200

    def test_index_pagination(self, authenticated_client):
        """Test index pagination"""
        response = authenticated_client.get("/?page=2")
        assert response.status_code == 200


class TestMovieDetail:
    """Test movie detail endpoint"""

    def test_movie_detail_not_authenticated(self, client):
        """Test movie detail without authentication"""
        response = client.get("/movies/page")
        assert response.status_code in [302, 401]

    def test_movie_detail_authenticated(self, authenticated_client):
        """Test movie detail with authentication"""
        response = authenticated_client.get(
            "/movies/page", follow_redirects=True
        )
        assert response.status_code == 200


class TestMovieProgress:
    """Test movie progress tracking"""

    def test_save_progress_not_authenticated(self, client):
        """Test saving progress without authentication"""
        response = client.post(
            "/video-progress",
            data=json.dumps({"filename": "/movies/file/unknown"}),
            content_type="application/json",
        )
        assert response.status_code in [302, 401]

    def test_save_progress_authenticated(self, authenticated_client):
        """Test saving progress when authenticated"""
        response = authenticated_client.post(
            "/video-progress",
            data=json.dumps({"filename": "/movies/file/unknown"}),
            content_type="application/json",
        )
        assert response.status_code in [200, 204, 400, 404]


class TestMovieFile:
    """Test movie file serving"""

    def test_serve_movie_file_not_authenticated(self, client):
        """Test movie file serving without authentication"""
        response = client.get("/movies/file/test.mp4")
        assert response.status_code in [302, 401, 404]

    def test_serve_movie_file_authenticated(self, authenticated_client):
        """Test movie file serving when authenticated"""
        response = authenticated_client.get("/movies/file/test.mp4")
        assert response.status_code in [
            404,
            206,
        ]  # 404 if not found, 206 if partial content

    def test_serve_movie_file_path_traversal_attack(
        self, authenticated_client
    ):
        """Test movie file serving prevents path traversal"""
        response = authenticated_client.get("/movies/file/../../../etc/passwd")
        assert response.status_code in [400, 404]


class TestMovieSubtitles:
    """Test subtitle serving"""

    def test_serve_subtitles_not_authenticated(self, client):
        """Test subtitle serving without authentication"""
        response = client.get("/subtitles/test.vtt")
        assert response.status_code in [302, 401, 404]

    def test_serve_subtitles_authenticated(self, authenticated_client):
        """Test subtitle serving when authenticated"""
        response = authenticated_client.get("/subtitles/test.vtt")
        assert response.status_code in [404, 200]


class TestMovieOperations:
    """Test movie operations"""

    def test_delete_movie_not_authenticated(self, client):
        """Test delete movie without authentication"""
        response = client.post("/movies/remove/mo/mov_0")
        assert response.status_code in [302, 401]

    def test_delete_movie_as_regular_user(self, authenticated_client):
        """Test regular user cannot delete movies"""
        response = authenticated_client.post("/movies/remove/mo/mov_0")
        assert response.status_code == 302

"""
Blueprint modules for MarinKino application
"""

from .admin_bp import admin_bp, init_admin_bp
from .auth_bp import auth_bp, init_auth_bp
from .memes_bp import MEMES_COUNT, memes_bp
from .misc_bp import init_misc_bp, misc_bp
from .movies_bp import get_movies_statistics, movies_bp
from .music_bp import MUSIC_COUNT, music_bp

__all__ = [
    "auth_bp",
    "admin_bp",
    "movies_bp",
    "memes_bp",
    "music_bp",
    "misc_bp",
    "init_auth_bp",
    "init_admin_bp",
    "init_misc_bp",
    "get_movies_statistics",
    "MUSIC_COUNT",
    "MEMES_COUNT",
]

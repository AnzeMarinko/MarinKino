import logging
import os
from logging.handlers import RotatingFileHandler

from dotenv import load_dotenv

load_dotenv()
FILMS_ROOT = "data/movies"
FLASK_ENV = os.getenv("FLASK_ENV", "development")
LOG_DIR = os.getenv(
    "MARINKINO_LOG_DIR", os.path.join(os.getcwd(), "cache", "logs", "server")
)
os.makedirs(LOG_DIR, mode=0o750, exist_ok=True)
# Stable filename lets Fail2Ban follow failures across application restarts.
LOG_FILENAME = os.path.join(LOG_DIR, "server.log")
file_handler = RotatingFileHandler(
    LOG_FILENAME, maxBytes=5 * 1024 * 1024, backupCount=5, encoding="utf-8"
)
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - 1 - [%(levelname)s] - %(name)s: %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
    handlers=[file_handler, logging.StreamHandler()],
)
logging.getLogger("waitress.queue").setLevel(logging.WARNING)
log = logging.getLogger(__name__)

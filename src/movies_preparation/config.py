import logging
import os
from datetime import datetime

from dotenv import load_dotenv

# Naloži .env datoteko
load_dotenv()

FILMS_ROOT = "data/movies"
FLASK_ENV = os.getenv("FLASK_ENV", "development")

if FLASK_ENV == "production":
    LOG_DIR = "/app/cache/logs/server"
else:
    LOG_DIR = os.path.join(os.getcwd(), "cache", "logs", "server")

if not os.path.exists(LOG_DIR):
    try:
        os.makedirs(LOG_DIR)
    except OSError as e:
        print(f"Napaka pri ustvarjanju mape {LOG_DIR}: {e}")
else:
    try:
        files = sorted(
            [
                os.path.join(LOG_DIR, f)
                for f in os.listdir(LOG_DIR)
                if f"server_start_{FLASK_ENV}_" in f
            ]
        )
        for f in files[:-5]:
            os.remove(f)
    except OSError as e:
        print(f"Napaka pri praznenju mape {LOG_DIR}: {e}")

timestamp = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
LOG_FILENAME = os.path.join(LOG_DIR, f"server_start_{FLASK_ENV}_{timestamp}.log")

file_handler = logging.FileHandler(LOG_FILENAME, encoding="utf-8")
console_handler = logging.StreamHandler()

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - 1 - [%(levelname)s] - %(name)s: %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
    handlers=[file_handler, console_handler],
)
logging.getLogger("waitress.queue").setLevel(logging.WARNING)
log = logging.getLogger(__name__)

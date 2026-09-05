import logging
import os

os.umask(0)

from content_preparation import FILMS_ROOT, is_ffmpeg_installed
from content_preparation.interactive_pipeline import run_interactive_pipeline

log = logging.getLogger(__name__)

if __name__ == "__main__":
    if is_ffmpeg_installed():
        run_interactive_pipeline(FILMS_ROOT)
        log.info("\n✅ Končano!\n")
    else:
        log.error("❌ FFmpeg ni nameščen! Namesti ga in poskusi znova.")

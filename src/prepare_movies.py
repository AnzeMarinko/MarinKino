import logging

from movies_preparation import (
    FILMS_ROOT,
    check_folder,
    is_ffmpeg_installed,
    scrappe_chosen,
)

log = logging.getLogger(__name__)

if __name__ == "__main__":
    if is_ffmpeg_installed():
        scrappe_chosen()
        all_films = check_folder(FILMS_ROOT, only_collect_metadata=False)
        log.info("\n✅ Končano!\n")
    else:
        log.error("❌ FFmpeg ni nameščen! Namesti ga in poskusi znova.")

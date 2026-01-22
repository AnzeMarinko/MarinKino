import logging
from pathlib import Path

import tqdm

from .get_movie_metadata import MovieMetadata
from .subtitles import prepare_subtitles
from .video_converter import convert_videos, get_videos_list

log = logging.getLogger(__name__)


def check_folder(folder, only_collect_metadata=True):
    folder_path = Path(folder)
    output_films = []

    if (
        not only_collect_metadata
        and "06-the-chosen" not in folder_path.name.lower()
    ):
        videos = convert_videos(str(folder_path))

        if videos:
            metadata = MovieMetadata(str(folder_path))
            if len(videos) == 1:
                prepare_subtitles(str(folder_path), videos[0], metadata)

    if get_videos_list(str(folder_path)):
        output_films.append(MovieMetadata(str(folder_path)))

    subfolders = sorted(
        [f for f in folder_path.iterdir() if f.is_dir()], reverse=True
    )

    if subfolders:
        iterator = (
            tqdm.tqdm(subfolders, desc=f"Procesiram {folder_path.name}")
            if not only_collect_metadata
            else subfolders
        )

        for sub in iterator:
            output_films.extend(check_folder(str(sub), only_collect_metadata))

    return output_films

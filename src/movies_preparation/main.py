import logging
from pathlib import Path

import tqdm

from .get_movie_metadata import MovieMetadata
from .subtitles import prepare_subtitles
from .video_converter import convert_to_m3u8, convert_videos

log = logging.getLogger(__name__)


def check_film(film_folder, only_collect_metadata=True):
    if (
        not only_collect_metadata
        and "0x-neurejeni-filmi" in str(film_folder).lower()
    ):
        videos = convert_videos(str(film_folder))

        if videos:
            metadata = MovieMetadata(str(film_folder))
            if len(videos) == 1:
                prepare_subtitles(str(film_folder), videos[0], metadata)
        if ".collection" not in str(film_folder).lower() and len(videos) == 1:
            for video in videos:
                convert_to_m3u8(video)

    movie_data = MovieMetadata(str(film_folder))

    return movie_data


def check_folder(folder, only_collect_metadata=True):
    folder_path = Path(folder)
    output_films = []

    for subfolder in sorted(
        [f for f in folder_path.iterdir() if f.is_dir()], reverse=True
    ):
        film_folders = sorted(
            [f for f in subfolder.iterdir() if f.is_dir()], reverse=True
        )

        if film_folders:
            film_iterator = (
                tqdm.tqdm(film_folders, desc=f"Procesiram {subfolder.name}")
                if not only_collect_metadata
                else film_folders
            )
            for film in film_iterator:
                movie_data = check_film(film, only_collect_metadata)
                if movie_data:
                    output_films.append(movie_data)

    return output_films

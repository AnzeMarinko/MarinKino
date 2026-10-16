"""Read prepared movie metadata without importing download/ML tooling."""

import json
import logging
from pathlib import Path
from types import SimpleNamespace

from security_storage import read_json, safe_resolved_path

FILMS_ROOT = "data/movies"
log = logging.getLogger(__name__)


def check_folder(root):
    root = Path(root)
    if not root.is_dir():
        return []
    films = []
    for folder in sorted(root.glob("*/*"), reverse=True):
        if not folder.is_dir() or folder.is_symlink():
            continue
        metadata_file = folder / "readme.json"
        if not metadata_file.is_file():
            continue
        try:
            safe_resolved_path(root, str(metadata_file.relative_to(root)))
            if metadata_file.stat().st_size > 8 * 1024 * 1024:
                raise ValueError("Movie metadata exceeds size limit")
            data = read_json(metadata_file, {})
            if not isinstance(data, dict):
                raise ValueError("Invalid movie metadata")
        except (OSError, ValueError, json.JSONDecodeError):
            log.warning("Skipping invalid movie metadata: %s", folder.name)
            continue
        cover = folder / "cover_image.jpg"
        thumb = folder / "cover_thumb.jpg"
        players = data.get("Players", "")
        if isinstance(players, list):
            players = "; ".join(map(str, players))
        videos = sorted(
            file.name
            for file in folder.iterdir()
            if file.is_file()
            and not file.is_symlink()
            and file.suffix.lower() in {".avi", ".mp4", ".mkv", ".vob"}
        )
        streams = sorted(
            {
                str(file.relative_to(folder).parent)
                for file in folder.rglob("master.m3u8")
                if file.is_file()
                and not file.is_symlink()
                and file.resolve().is_relative_to(folder.resolve())
            }
        )
        subtitles = sorted(
            file.name
            for file in folder.glob("*.vtt")
            if file.is_file() and not file.is_symlink()
        )
        films.append(
            SimpleNamespace(
                folder=str(folder),
                cover=str(cover),
                thumbnail=str(thumb if thumb.is_file() else cover),
                title=data.get("Title") or folder.name,
                original_title=data.get("OriginalTitle", ""),
                year=data.get("Year", ""),
                plot=data.get("Plot - translated") or data.get("Plot", ""),
                players=str(players),
                runtimes=data.get("Runtimes", ""),
                runtimes_by_files=data.get("RuntimesByFiles", {}),
                slosinh="sinh" in folder.name.lower(),
                genres=data.get("Genres", []),
                video_files=videos,
                video_files_m3u8=streams,
                subtitles=subtitles,
                recommendation_level=data.get("recommendation_level", ""),
                user_notes=data.get("user_notes", {}),
                ratings=data.get("ratings", {}),
            )
        )
    return films

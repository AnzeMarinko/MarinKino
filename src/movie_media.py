"""One playable source per episode, shared by playback and downloads."""

from pathlib import PurePosixPath


def movie_sources(film):
    """Prefer prepared HLS over its same-named original without duplicates.

    An episode keeps its MP4-shaped ID after conversion, so saved progress
    and download names do not depend on the representation on disk.
    Paths remain relative to the movie folder; callers enforce access.
    """
    sources = {}
    for filename in sorted(film.get("video_files") or []):
        path = PurePosixPath(filename)
        key = str(path.with_suffix(""))
        sources.setdefault(
            key,
            {
                "id": filename,
                "path": filename,
                "is_hls": False,
                "title": path.stem,
            },
        )
    for directory in sorted(film.get("video_files_m3u8") or []):
        path = PurePosixPath(directory)
        key = str(path)
        title = path.name or PurePosixPath(film.get("folder", "film")).name
        sources[key] = {
            "id": key + ".mp4" if key != "." else title + ".mp4",
            "path": str(path / "master.m3u8"),
            "is_hls": True,
            "title": title,
        }
    return [sources[key] for key in sorted(sources)]

"""Prepare one bounded, disk-backed movie download at a time."""

import hashlib
import json
import os
import shutil
import subprocess
import tempfile
import time
import zipfile
from pathlib import Path
from threading import BoundedSemaphore
from urllib.parse import quote

from flask import make_response, send_file

from movie_media import movie_sources
from security_storage import locked_path, safe_resolved_path

MAX_ARCHIVE_BYTES = 4 * 1024**3
CACHE_LIMIT_BYTES = 8 * 1024**3
ARCHIVE_PREPARATION_SECONDS = 1800
_preparation = BoundedSemaphore(1)


class ArchivePreparationError(Exception):
    """A bounded preparation could not produce a downloadable archive."""

    def __init__(self, status, message="Priprava prenosa ni uspela."):
        super().__init__(message)
        self.status = status


def ready_archive(root, group, folder):
    directory = safe_resolved_path(root, f"{group}/{folder}")
    digest = hashlib.sha256(f"collection-v2:{directory}".encode()).hexdigest()
    target = Path("cache/downloads").resolve() / (digest + ".zip")
    try:
        if time.time() - target.stat().st_mtime <= 3600 and target.is_file():
            return target
    except FileNotFoundError:
        pass
    return None


def _archive_sources(film, directory):
    """Resolve each selected episode once and account for the entire input."""
    media = []
    paths = []
    for name in film["subtitles"]:
        path = Path(safe_resolved_path(directory, name))
        if path.is_file():
            paths.append((path, path.name))
    cover = directory / "cover_image.jpg"
    if cover.is_file() and not cover.is_symlink():
        paths.append((cover, "cover_image.jpg"))
    input_paths = {path for path, _ in paths}
    for source in movie_sources(film):
        path = Path(safe_resolved_path(directory, source["path"]))
        if not path.is_file():
            raise ArchivePreparationError(
                503,
                "Del zbirke ni na voljo. Osveži knjižnico in poskusi znova.",
            )
        media.append((source, path))
        if source["is_hls"]:
            stream_dir = path.parent
            input_paths.update(
                file
                for file in stream_dir.rglob("*")
                if file.is_file()
                and not file.is_symlink()
                and file.resolve().is_relative_to(directory)
                and not any(
                    part.startswith(".")
                    for part in file.relative_to(stream_dir).parts
                )
            )
        else:
            input_paths.add(path)
    if not media:
        raise ArchivePreparationError(404, "Ni videov za prenos.")
    return media, paths, sum(path.stat().st_size for path in input_paths)


def _remux_episode(playlist, converted, timeout):
    """Copy encoded streams locally; bound the whole collection's duration."""
    try:
        subprocess.run(
            [
                "ffmpeg",
                "-nostdin",
                "-v",
                "error",
                "-threads",
                "1",
                "-protocol_whitelist",
                "file,crypto,data",
                "-i",
                str(playlist),
                "-map",
                "0:v?",
                "-map",
                "0:a?",
                "-c",
                "copy",
                "-threads",
                "1",
                "-movflags",
                "+faststart",
                str(converted),
            ],
            check=True,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            timeout=timeout,
        )
    except (subprocess.SubprocessError, OSError) as error:
        raise ArchivePreparationError(
            503, "Dela zbirke trenutno ni mogoče pripraviti za prenos."
        ) from error


def prepare_archive(film, root, group, folder):
    if not _preparation.acquire(blocking=False):
        raise ArchivePreparationError(
            429, "Priprava prenosa že poteka. Poskusi pozneje."
        )
    try:
        directory = Path(safe_resolved_path(root, f"{group}/{folder}"))
        cache = Path("cache/downloads").resolve()
        cache.mkdir(parents=True, exist_ok=True)
        cache.chmod(0o755)
        digest = hashlib.sha256(
            f"collection-v2:{directory}".encode()
        ).hexdigest()
        target = cache / (digest + ".zip")
        with locked_path(cache / ".preparation"):
            now = time.time()
            archives = sorted(
                cache.glob("*.zip"), key=lambda file: file.stat().st_mtime
            )
            total = sum(file.stat().st_size for file in archives)
            for old in archives:
                if (
                    now - old.stat().st_mtime > 3600
                    or total > CACHE_LIMIT_BYTES
                ):
                    total -= old.stat().st_size
                    old.unlink(missing_ok=True)
            if not target.is_file():
                media, paths, source_size = _archive_sources(film, directory)
                if source_size > MAX_ARCHIVE_BYTES:
                    raise ArchivePreparationError(
                        413, "Film presega največjo velikost prenosa (4 GB)."
                    )
                if (
                    shutil.disk_usage(cache).free
                    < source_size * 3 + 256 * 1024**2
                ):
                    raise ArchivePreparationError(
                        503, "Za pripravo prenosa ni dovolj prostora."
                    )
                with tempfile.TemporaryDirectory(
                    prefix="build-", dir=cache
                ) as build:
                    build = Path(build)
                    deadline = time.monotonic() + ARCHIVE_PREPARATION_SECONDS
                    output_size = sum(path.stat().st_size for path, _ in paths)
                    for index, (source, source_path) in enumerate(media):
                        if source["is_hls"]:
                            remaining = deadline - time.monotonic()
                            if remaining <= 0:
                                raise ArchivePreparationError(
                                    503,
                                    "Priprava prenosa je trajala predolgo.",
                                )
                            converted = build / f"episode-{index}.mp4"
                            _remux_episode(source_path, converted, remaining)
                            name = (
                                folder + ".mp4"
                                if len(media) == 1
                                else source["id"]
                            )
                            paths.append((converted, name))
                            output_size += converted.stat().st_size
                        else:
                            paths.append((source_path, source["id"]))
                            output_size += source_path.stat().st_size
                        if output_size > MAX_ARCHIVE_BYTES:
                            raise ArchivePreparationError(
                                413,
                                "Zbirka presega omejitev prenosa (4 GB).",
                            )
                    staged = build / "archive.zip"
                    with zipfile.ZipFile(
                        staged, "w", zipfile.ZIP_STORED
                    ) as archive:
                        for path, name in paths:
                            archive.write(path, name)
                        public = {
                            key: film.get(key)
                            for key in (
                                "title",
                                "original_title",
                                "year",
                                "description",
                                "genres",
                                "players",
                                "runtimes",
                                "slosinh",
                                "recommendation_level",
                            )
                        }
                        archive.writestr(
                            "metadata.json",
                            json.dumps(public, ensure_ascii=False),
                        )
                    if staged.stat().st_size > MAX_ARCHIVE_BYTES:
                        raise ArchivePreparationError(
                            413, "Arhiv presega omejitev prenosa (4 GB)."
                        )
                    staged.chmod(0o644)
                    os.replace(staged, target)
        return target
    finally:
        _preparation.release()


def archive_response(film, root, group, folder, production=False):
    """Deliver an existing archive without preparing work on an HTTP thread."""
    target = ready_archive(root, group, folder)
    if target is None:
        return None
    if production:
        response = make_response()
        response.headers["X-Accel-Redirect"] = (
            "/protected_downloads/" + target.name
        )
        response.headers["Content-Type"] = "application/zip"
        # RFC5987 supports Unicode without response header injection.
        response.headers["Content-Disposition"] = (
            "attachment; filename*=UTF-8''" + quote(folder + ".zip", safe="")
        )
    else:
        response = send_file(
            target, as_attachment=True, download_name=folder + ".zip"
        )
    response.headers["Cache-Control"] = "private, no-store"
    return response


def build_archive_job(job):
    payload = job["payload"]
    prepare_archive(
        payload["film"], payload["root"], payload["group"], payload["folder"]
    )
    return {"group": payload["group"], "folder": payload["folder"]}


def archive_payload(film, root, group, folder):
    public_fields = (
        "title",
        "original_title",
        "year",
        "description",
        "genres",
        "players",
        "runtimes",
        "slosinh",
        "recommendation_level",
        "video_files",
        "subtitles",
        "video_files_m3u8",
    )
    return {
        "root": str(Path(root).resolve()),
        "group": group,
        "folder": folder,
        "film": {key: film.get(key) for key in public_fields},
    }

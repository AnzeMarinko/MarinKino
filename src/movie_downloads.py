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

from flask import abort, make_response, send_file

from security_storage import locked_path, safe_resolved_path

MAX_ARCHIVE_BYTES = 4 * 1024**3
CACHE_LIMIT_BYTES = 8 * 1024**3
_preparation = BoundedSemaphore(1)


def archive_response(film, root, group, folder, production=False):
    if not _preparation.acquire(blocking=False):
        abort(429, "Priprava prenosa že poteka. Poskusi pozneje.")
    try:
        directory = Path(safe_resolved_path(root, f"{group}/{folder}"))
        cache = Path("cache/downloads").resolve()
        cache.mkdir(parents=True, exist_ok=True)
        cache.chmod(0o755)
        digest = hashlib.sha256(str(directory).encode()).hexdigest()
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
                paths = []
                for name in film["video_files"] + film["subtitles"]:
                    path = Path(safe_resolved_path(directory, name))
                    if path.is_file():
                        paths.append((path, path.name))
                hls = (
                    film["video_files_m3u8"] if not film["video_files"] else []
                )
                source_size = sum(path.stat().st_size for path, _ in paths)
                if hls:
                    stream_dir = Path(safe_resolved_path(directory, hls[0]))
                    source_size += sum(
                        path.stat().st_size
                        for path in stream_dir.rglob("*")
                        if path.is_file()
                        and not path.is_symlink()
                        and path.resolve().is_relative_to(stream_dir.resolve())
                    )
                if source_size > MAX_ARCHIVE_BYTES:
                    abort(
                        413, "Film presega največjo velikost prenosa (4 GB)."
                    )
                if (
                    shutil.disk_usage(cache).free
                    < source_size * 3 + 256 * 1024**2
                ):
                    abort(503, "Za pripravo prenosa ni dovolj prostora.")
                with tempfile.TemporaryDirectory(
                    prefix="build-", dir=cache
                ) as build:
                    build = Path(build)
                    if hls:
                        playlist = safe_resolved_path(
                            directory, f"{hls[0]}/master.m3u8"
                        )
                        converted = build / "film.mp4"
                        try:
                            subprocess.run(
                                [
                                    "ffmpeg",
                                    "-nostdin",
                                    "-v",
                                    "error",
                                    "-protocol_whitelist",
                                    "file,crypto,data",
                                    "-i",
                                    playlist,
                                    "-map",
                                    "0:v?",
                                    "-map",
                                    "0:a?",
                                    "-c",
                                    "copy",
                                    "-movflags",
                                    "+faststart",
                                    str(converted),
                                ],
                                check=True,
                                stdout=subprocess.DEVNULL,
                                stderr=subprocess.DEVNULL,
                                timeout=1800,
                            )
                        except (subprocess.SubprocessError, OSError):
                            abort(
                                503,
                                "Filma trenutno ni mogoče pripraviti "
                                "za prenos.",
                            )
                        paths.append((converted, folder + ".mp4"))
                    cover = directory / "cover_image.jpg"
                    if cover.is_file() and not cover.is_symlink():
                        paths.append((cover, "cover_image.jpg"))
                    if (
                        sum(path.stat().st_size for path, _ in paths)
                        > MAX_ARCHIVE_BYTES
                    ):
                        abort(413)
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
                    staged.chmod(0o644)
                    os.replace(staged, target)
        if production:
            response = make_response()
            response.headers["X-Accel-Redirect"] = (
                "/protected_downloads/" + target.name
            )
            response.headers["Content-Type"] = "application/zip"
            # RFC5987 supports Unicode without response header injection.
            response.headers["Content-Disposition"] = (
                "attachment; filename*=UTF-8''"
                + quote(folder + ".zip", safe="")
            )
        else:
            response = send_file(
                target, as_attachment=True, download_name=folder + ".zip"
            )
        response.headers["Cache-Control"] = "private, no-store"
        return response
    finally:
        _preparation.release()

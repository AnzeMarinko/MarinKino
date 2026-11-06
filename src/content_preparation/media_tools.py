"""Small shared helpers for local media preparation."""

import os
import re
from pathlib import Path


def ffmpeg_command(command):
    """Bound decoder, encoder and filter threads on the shared RPi host."""
    threads = int(os.environ.get("MARINKINO_PREP_THREADS", "2"))
    if not 1 <= threads <= 32:
        raise ValueError("MARINKINO_PREP_THREADS mora biti med 1 in 32.")
    return (
        command[:1]
        + ["-nostdin", "-threads", str(threads), "-filter_threads", "1"]
        + command[1:-1]
        + ["-threads", str(threads), command[-1]]
    )


def archive_original(source):
    """Retain converted inputs outside media discovery, without copying GBs.

    Hard links are created exclusively on the same filesystem. A collision
    never overwrites an earlier source; unlink happens only after linking.
    The .source extension prevents library scanners publishing backups.
    """
    source = Path(source)
    archive = source.parent / ".originals"
    archive.mkdir(exist_ok=True)
    number = 0
    while True:
        suffix = f".{number}" if number else ""
        target = archive / f"{source.name}{suffix}.source"
        try:
            os.link(source, target, follow_symlinks=False)
        except FileExistsError:
            number += 1
            continue
        source.unlink()
        return target


def audio_hls_ready(folder):
    folder = Path(folder)
    playlist_path = folder / "index.m3u8"
    if not playlist_path.is_file() or not (folder / "metadata.json").is_file():
        return False
    playlist = playlist_path.read_text(encoding="utf-8")
    if not playlist.startswith("#EXTM3U") or "#EXT-X-ENDLIST" not in playlist:
        return False
    # single_file uses a byte range of stream.m4s for EXT-X-MAP; ordinary
    # fMP4 HLS can use a separate init.mp4. Follow the emitted playlist.
    references = re.findall(r'URI="([^"\n]+)"', playlist)
    references += [
        line.strip()
        for line in playlist.splitlines()
        if line.strip() and not line.startswith("#")
    ]
    if not references:
        return False
    for reference in references:
        file = folder / reference
        if (
            file.parent != folder
            or not file.is_file()
            or not file.stat().st_size
        ):
            return False
    return True

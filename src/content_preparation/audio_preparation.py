import json
import logging
import os
import shutil
import subprocess
import tempfile
from pathlib import Path

from mutagen.easyid3 import EasyID3
from mutagen.mp3 import MP3, HeaderNotFoundError

from music.recommendations import (
    analyze_audio_file,
    analyze_song_semantics,
    ensure_metadata_schema,
)
from security_storage import atomic_write_json

from .media_tools import audio_hls_ready, ffmpeg_command

log = logging.getLogger(__name__)


def run_ffmpeg(command):
    """Pomožna funkcija za izvajanje FFmpeg ukazov."""
    try:
        subprocess.run(
            ffmpeg_command(command),
            stdout=subprocess.DEVNULL,
            stderr=subprocess.PIPE,
            text=True,
            check=True,
        )
        return True
    except subprocess.CalledProcessError as e:
        log.error(f"❌ FFmpeg napaka: {e}")
        if e.stderr:
            log.error(e.stderr.strip())
        return False


def save_hls_metadata(mp3_path: Path, out_dir: Path, *, analyze=False):
    """Prebere ID3 oznake iz MP3 datoteke in jih shrani v metadata.json."""
    metadata = {
        "title": mp3_path.stem,
        "artist": "",
        "album": "",
        "duration": 0,
    }

    try:
        audio = MP3(str(mp3_path), ID3=EasyID3)
        title_tags = audio.get("title") or [mp3_path.stem]
        artist_tags = audio.get("artist") or []
        album_tags = audio.get("album") or []

        metadata["title"] = ", ".join(title_tags)
        metadata["artist"] = " - ".join(artist_tags)
        metadata["album"] = " - ".join(album_tags)
        metadata["duration"] = int(
            getattr(getattr(audio, "info", None), "length", 0)
        )
    except (HeaderNotFoundError, Exception) as e:
        log.warning(f"⚠️ Ni mogoče prebrati ID3 za {mp3_path}: {e}")

    existing = out_dir / "metadata.json"
    if existing.exists():
        metadata.update(json.loads(existing.read_text(encoding="utf-8")))
    metadata, _ = ensure_metadata_schema(metadata, out_dir)
    if not analyze:
        atomic_write_json(out_dir / "metadata.json", metadata, mode=0o640)
        return
    try:
        metadata.update(
            analyze_audio_file(mp3_path, mp3_path.parent.as_posix())
        )
    except (OSError, RuntimeError, ValueError) as error:
        log.warning("⚠️ Analiza zvoka ni uspela za %s: %s", mp3_path, error)
    semantic = analyze_song_semantics(
        metadata["title"], metadata["artist"], metadata["album"]
    )
    if semantic is not None:
        metadata["semantic_analysis"] = semantic
        metadata["semantic_analysis_version"] = 1

    # Shrani v JSON datoteko znotraj ustvarjene HLS mape
    json_path = out_dir / "metadata.json"
    atomic_write_json(json_path, metadata, mode=0o640)


def convert_mp3_to_hls(input_path: str, output_dir: str, *, analyze=False):
    """Publish a complete HLS set; retain MP3 for editing and recovery."""
    mp3_file = Path(input_path)
    out_dir = Path(output_dir)
    if audio_hls_ready(out_dir):
        log.info("Preskočeno, HLS že pripravljen: %s", mp3_file.name)
        return True
    if not mp3_file.is_file():
        raise FileNotFoundError(mp3_file)
    out_dir.mkdir(parents=True, exist_ok=True)
    # Build away from public filenames. The playlist is published last.
    with tempfile.TemporaryDirectory(prefix=".hls-", dir=out_dir) as temporary:
        tmp_dir = Path(temporary)
        return _convert_audio(mp3_file, out_dir, tmp_dir, analyze=analyze)


def _convert_audio(mp3_file, out_dir, tmp_dir, *, analyze):
    tmp_playlist = tmp_dir / "index.m3u8"
    cmd = [
        "ffmpeg",
        "-y",
        "-i",
        str(mp3_file),
        "-map",
        "0:a:0",
        "-vn",
        "-c:a",
        "aac",
        "-b:a",
        "128k",
        "-f",
        "hls",
        "-hls_time",
        "6",
        "-hls_playlist_type",
        "vod",
        "-hls_segment_type",
        "fmp4",
        "-hls_flags",
        "single_file",
        "-hls_segment_filename",
        str(tmp_dir / "stream.m4s"),
        str(tmp_playlist),
    ]

    if not run_ffmpeg(cmd):
        log.error("Pretvorba ni uspela; MP3 ohranjen: %s", mp3_file)
        return False
    existing_metadata = out_dir / "metadata.json"
    if existing_metadata.exists():
        shutil.copyfile(existing_metadata, tmp_dir / "metadata.json")
    save_hls_metadata(mp3_file, tmp_dir, analyze=analyze)
    if not audio_hls_ready(tmp_dir):
        log.error("HLS izhod ni popoln; MP3 ohranjen: %s", mp3_file)
        return False
    for file in sorted(
        tmp_dir.iterdir(), key=lambda path: path.name == "index.m3u8"
    ):
        if not file.name.startswith("."):
            os.replace(file, out_dir / file.name)
    log.info("Pripravljeno: %s → %s", mp3_file.name, out_dir / "index.m3u8")
    return True


def process_audio_folders(folders=None, *, analyze=False):
    folders = (
        folders
        if folders is not None
        else ["data/music", "data/radio-stories"]
    )
    files = sorted(
        path
        for folder in folders
        for path in Path(folder).rglob("*")
        if path.is_file()
        and path.suffix.lower() == ".mp3"
        and not any(
            part.startswith(".") for part in path.relative_to(folder).parts
        )
    )
    summary = {"prepared": 0, "skipped": 0, "failed": 0}
    for index, mp3_file in enumerate(files, 1):
        output = mp3_file.with_suffix("")
        log.info("[%s/%s] %s", index, len(files), mp3_file)
        if audio_hls_ready(output):
            summary["skipped"] += 1
            continue
        try:
            success = convert_mp3_to_hls(
                str(mp3_file), str(output), analyze=analyze
            )
        except (OSError, ValueError) as error:
            log.error("Ni pripravljeno: %s — %s", mp3_file, error)
            success = False
        summary["prepared" if success else "failed"] += 1
    log.info(
        "Glasba: %s pripravljenih, %s že pripravljenih, %s napak.",
        summary["prepared"],
        summary["skipped"],
        summary["failed"],
    )
    return summary


if __name__ == "__main__":
    process_audio_folders()

import json
import logging
import subprocess
from pathlib import Path

import tqdm
from mutagen.easyid3 import EasyID3
from mutagen.mp3 import MP3, HeaderNotFoundError

logging.basicConfig(level=logging.INFO)
log = logging.getLogger(__name__)


def run_ffmpeg(command):
    """Pomožna funkcija za izvajanje FFmpeg ukazov."""
    try:
        subprocess.run(
            command,
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


def save_hls_metadata(mp3_path: Path, out_dir: Path):
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

    # Shrani v JSON datoteko znotraj ustvarjene HLS mape
    json_path = out_dir / "metadata.json"
    with open(json_path, "w", encoding="utf-8") as f:
        json.dump(metadata, f, ensure_ascii=False, indent=2)


def convert_mp3_to_hls(input_path: str, output_dir: str):
    mp3_file = Path(input_path)
    out_dir = Path(output_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    playlist_path = out_dir / "index.m3u8"

    # Vedno zapišemo ali osvežimo metadata.json
    save_hls_metadata(mp3_file, out_dir)

    # Če HLS že obstaja, ne izvajamo ponovno FFmpeg-a, ampak le izbrišemo MP3
    if playlist_path.exists():
        log.info(f"⏭️ HLS že obstaja, brišem MP3: {input_path}")
        mp3_file.unlink()
        return

    cmd = [
        "ffmpeg",
        "-y",
        "-i",
        input_path,
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
        "6",  # dolžina posameznega segmenta v sekundah
        "-hls_playlist_type",
        "vod",  # VOD (Video/Audio on Demand)
        "-hls_segment_type",
        "fmp4",
        "-hls_fmp4_init_filename",
        "init.mp4",
        "-hls_segment_filename",
        str(out_dir / "segment_%03d.m4s"),
        str(playlist_path),
    ]

    if not run_ffmpeg(cmd):
        log.error(f"❌ Napaka pri konverziji: {input_path}")
    else:
        log.info(f"✅ Konverzija uspešna: {input_path} -> {playlist_path}")
        # Varno izbrišemo izvirno MP3 datoteko po uspešni konverziji
        mp3_file.unlink()


def process_audio_folders():
    for folder in tqdm.tqdm(
        [
            "data/music",
            "data/radio-stories",
        ],
        desc="Procesiram mape",
    ):
        for mp3_file in tqdm.tqdm(
            list(Path(folder).rglob("*.mp3")),
            desc=f"Procesiram datoteke v {folder}",
        ):
            output_directory = mp3_file.parent / f"{mp3_file.stem}"
            convert_mp3_to_hls(str(mp3_file), str(output_directory))


if __name__ == "__main__":
    process_audio_folders()

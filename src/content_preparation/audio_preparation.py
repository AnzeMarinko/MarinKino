import json
import logging
import shutil
import subprocess
from pathlib import Path

import tqdm
from mutagen.easyid3 import EasyID3
from mutagen.mp3 import MP3, HeaderNotFoundError

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
    playlist_path = out_dir / "index.m3u8"
    segment_file = out_dir / "stream.m4s"

    # Če sta obe datoteki že prisotni, velja, da je konverzija končana
    if playlist_path.exists() and segment_file.exists():
        if mp3_file.exists():
            mp3_file.unlink()
        return

    out_dir.mkdir(parents=True, exist_ok=True)
    save_hls_metadata(mp3_file, out_dir)

    # Začasna mapa za gradnjo HLS-a
    tmp_dir = out_dir / "_tmp"
    if tmp_dir.exists():
        shutil.rmtree(tmp_dir)
    tmp_dir.mkdir(parents=True, exist_ok=True)

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

    if run_ffmpeg(cmd):
        # Premaknemo uspele datoteke iz začasne mape v končno
        for file in tmp_dir.iterdir():
            shutil.move(str(file), str(out_dir / file.name))
        shutil.rmtree(tmp_dir)

        log.info(f"✅ Konverzija uspešna: {input_path} -> {playlist_path}")
        mp3_file.unlink()
    else:
        # Če konverzija spodleti, pobrišemo začasne datoteke
        if tmp_dir.exists():
            shutil.rmtree(tmp_dir)
        log.error(f"❌ Napaka pri konverziji (MP3 ohranjen): {input_path}")


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

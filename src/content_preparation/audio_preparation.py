import logging
import subprocess
from pathlib import Path

import tqdm

log = logging.getLogger(__name__)


def run_ffmpeg(command):
    """Pomožna funkcija za izvajanje FFmpeg ukazov."""
    try:
        subprocess.run(
            command,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            check=True,
        )
        return True
    except subprocess.CalledProcessError as e:
        log.error(f"❌ FFmpeg napaka: {e}")
        return False


def convert_mp3_to_hls(input_path: str, output_dir: str):
    out_dir = Path(output_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    playlist_path = out_dir / "index.m3u8"
    if playlist_path.exists():
        return

    cmd = [
        "ffmpeg",
        "-i",
        input_path,
        "-c:a",
        "aac",
        "-b:a",
        "128k",
        "-f",
        "hls",
        "-hls_time",
        "6",  # dolžina posameznega segmenta v sekundah
        "-hls_playlist_type",
        "vod",  # VOD (Video/Audio on Demand),
        "-hls_segment_type",
        "fmp4",
        "-hls_fmp4_init_filename",
        "init.mp4",
        "-hls_segment_filename",
        str(out_dir / "segment_%03d.ts"),
        str(playlist_path),
    ]
    if not run_ffmpeg(cmd):
        log.error(f"❌ Napaka pri konverziji: {input_path}")


def process_audio_folders():
    for folder in tqdm.tqdm(
        ["data/radio-stories", "data/music"], desc="Procesiram mape"
    ):
        for mp3_file in tqdm.tqdm(
            list(Path(folder).rglob("*.mp3")),
            desc=f"Procesiram datoteke v {folder}",
        ):
            output_directory = mp3_file.parent / f"{mp3_file.stem}"
            convert_mp3_to_hls(str(mp3_file), str(output_directory))


if __name__ == "__main__":
    process_audio_folders()

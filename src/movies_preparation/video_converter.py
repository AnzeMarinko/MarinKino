import logging
import subprocess
from pathlib import Path

from .helpers import remove

log = logging.getLogger(__name__)

SUPPORTED_EXTENSIONS = {".avi", ".mp4", ".mkv", ".vob", ".mov"}


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


def convert_to_mp4(input_path, output_path):
    """Unificirana funkcija za polno pretvorbo v MP4 (H.264 + AAC)."""
    log.info(f"🎬 Pretvarjam: {input_path.name} -> {output_path.name}")
    command = [
        "ffmpeg",
        "-y",
        "-i",
        str(input_path),
        "-c:v",
        "libx264",
        "-preset",
        "fast",
        "-crf",
        "20",
        "-c:a",
        "aac",
        "-ac",
        "2",
        "-b:a",
        "128k",
        "-movflags",
        "+faststart",
        str(output_path),
    ]
    if run_ffmpeg(command):
        remove(str(input_path))
        return True
    return False


def ensure_aac_audio(filepath):
    """Preveri kodek in po potrebi pretvori samo zvok v AAC brez izgube video kakovosti."""
    filepath = Path(filepath)
    cmd = [
        "ffprobe",
        "-v",
        "error",
        "-select_streams",
        "a:0",
        "-show_entries",
        "stream=codec_name",
        "-of",
        "default=noprint_wrappers=1:nokey=1",
        str(filepath),
    ]

    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.stdout.strip() == "aac":
        return

    temp_file = filepath.with_suffix(".tmp.mp4")
    log.info(f"🔊 Re-enkodiranje zvoka (AAC): {filepath.name}")

    command = [
        "ffmpeg",
        "-y",
        "-i",
        str(filepath),
        "-c:v",
        "copy",
        "-c:a",
        "aac",
        "-ac",
        "2",
        "-b:a",
        "128k",
        "-movflags",
        "+faststart",
        str(temp_file),
    ]

    if run_ffmpeg(command):
        temp_file.replace(filepath)


def get_videos_list(folder):
    """Vrne seznam Path objektov za podprte video datoteke."""
    p = Path(folder)
    return [
        f
        for f in p.iterdir()
        if f.is_file() and f.suffix.lower() in SUPPORTED_EXTENSIONS
    ]


def convert_videos(folder):
    folder_path = Path(folder)
    videos = sorted(get_videos_list(folder_path))

    if not videos:
        return []

    # 1. faza: Poskrbi, da so vsi obstoječi MP4 v AAC formatu
    for video in videos:
        if video.suffix.lower() == ".mp4":
            ensure_aac_audio(video)

    final_output = folder_path / f"{folder_path.name}.mp4"

    # 2. faza: Logika združevanja ali pretvorbe
    if ".Collection" in folder_path.name:
        # Za zbirke samo pretvori posamezne datoteke v MP4, ne združuj
        for video in videos:
            if video.suffix.lower() != ".mp4":
                convert_to_mp4(video, video.with_suffix(".mp4"))

    elif len(videos) > 1:
        # Združevanje več datotek
        log.info(f"🔄 Združujem {len(videos)} videov v {final_output.name}...")
        temp_mp4s = []

        for v in videos:
            target = v.with_suffix(".temp_conv.mp4")
            if convert_to_mp4(v, target):
                temp_mp4s.append(target)

        # Ustvari temp_list za concat
        list_file = folder_path / "temp_list.txt"
        with list_file.open("w", encoding="utf-8") as f:
            for tmp in temp_mp4s:
                f.write(f"file '{tmp.name}'\n")

        concat_cmd = [
            "ffmpeg",
            "-y",
            "-f",
            "concat",
            "-safe",
            "0",
            "-i",
            str(list_file),
            "-c",
            "copy",
            str(final_output),
        ]

        if run_ffmpeg(concat_cmd):
            for tmp in temp_mp4s:
                remove(str(tmp))
            remove(str(list_file))

    elif len(videos) == 1:
        # Samo ena datoteka
        video = videos[0]
        if video.suffix.lower() != ".mp4":
            convert_to_mp4(video, final_output)
        else:
            video.rename(final_output)

    return get_videos_list(folder)

import os
import subprocess
from .helpers import remove
import logging

def convert_single_file(input_file, output_file):
    """Uporabi ffmpeg za konverzijo v MP4 format."""
    command = [
        "ffmpeg", "-i", input_file,
        "-c:v", "libx264", "-preset", "fast", "-crf", "20",
        "-c:a", "aac", "-ac", "2", "-b:a", "128k",
        "-movflags", "+faststart",
        output_file
    ]
    try:
        subprocess.run(command, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, check=True)
        remove(input_file)
    except subprocess.CalledProcessError as e:
        logging.error(f"❌ Napaka pri pretvorbi {input_file}: {e}")

def concat_and_convert(files, new_file):
    temp_files = []
    for f, _ in sorted(files):
        temp_mp4 = f + ".mp4"
        convert_single_file(f, temp_mp4)
        temp_files.append(temp_mp4)

    with open("temp_list.txt", "w", encoding="utf-8") as f:
        for temp in temp_files:
            f.write(f"file '{temp}'\n")

    concat_command = ["ffmpeg", "-f", "concat", "-safe", "0", "-i", "temp_list.txt", "-c", "copy", new_file]
    subprocess.run(concat_command, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, check=True)

    for temp in temp_files:
        remove(temp)

    os.remove("temp_list.txt")
    
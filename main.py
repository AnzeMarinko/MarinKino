import os
import json
import tqdm
import subprocess

from priprava_filmov.config import FILMS_ROOT, IZJEME, CACHE_ROOT
from priprava_filmov.helpers import is_ffmpeg_installed, remove
from priprava_filmov.video_converter import concat_and_convert, convert_single_file
from priprava_filmov.download_subtitles import get_subtitles
from priprava_filmov.translate_subtitles import translate
from priprava_filmov.rescale_captions import rescale_captions, extract_audio
from priprava_filmov.get_movie_metadata import MovieMetadata
from priprava_filmov.the_chosen_scrapper import scrappe_chosen

def convert_audio_to_aac(filepath):
    """Uporabi ffmpeg za konverzijo v MP4 format."""
    cmd = [
        "ffprobe", "-v", "error", "-select_streams", "a:0",
        "-show_entries", "stream=codec_name",
        "-of", "default=noprint_wrappers=1:nokey=1", filepath
    ]
    result = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
    codec = result.stdout.strip()

    if codec == "aac":
        return None

    temp_filepath = filepath + ".tmp.mp4"
    print(f"Pretvarjam: {filepath} → {temp_filepath}")
    command = [
        "ffmpeg", "-i", filepath,
        "-c:v", "copy",
        "-c:a", "aac", "-ac", "2", "-b:a", "128k",
        "-movflags", "+faststart",
        "-y",
        temp_filepath
    ]
    try:
        subprocess.run(command, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, check=True)
        os.replace(temp_filepath, filepath)
    except Exception:
        if os.path.exists(temp_filepath):
            os.remove(temp_filepath)
    

def convert_srt_to_vtt(srt_path):
    with open(srt_path, 'r', encoding='utf-8') as srt_file, open(srt_path[:-5] + srt_path[-5:].replace(".srt", ".vtt"), 'w', encoding='utf-8') as vtt_file:
        vtt_file.write("WEBVTT\n\n")
        for line in srt_file:
            # Zamenjaj vejico z decimalno piko
            vtt_file.write(line.replace(',', '.'))


def check_folder(folder, only_collect_metadata=True):
    """Preveri in preimenuje podnapise v enakem imeniku kot video."""

    files = [(os.path.join(folder, f), f.split(".")[-1]) for f in os.listdir(folder) if os.path.isfile(os.path.join(folder, f))]
    videos = [f for f in files if f[1].lower() in {"avi", "mp4", "mkv", "vob"} and os.path.basename(f[0]) not in IZJEME]
    subtitles = [f[0] for f in files if f[1].lower() == "srt"]

    if not only_collect_metadata and "06-the-chosen" not in folder:
        for video, form in videos:
            if form == "mp4":
                with open("tmp_current_file.txt", "w") as f:
                    f.write(video)
                convert_audio_to_aac(video)
        if os.path.exists("tmp_current_file.txt"):
            remove("tmp_current_file.txt")

        new_file = os.path.join(folder, os.path.basename(folder) + ".mp4")
        if videos and not os.path.exists(new_file):
            if len(videos) > 1 and len(videos) < 7 and len(set(f[1] for f in videos)) == 1 and "Odprava.Zelenega.Zmaja.1976" not in folder:
                print(f"🔄 Združujem {len(videos)} videoposnetkov v {new_file}...")
                concat_and_convert(videos, new_file)
            elif len(videos) == 1:
                input_file, ext = videos[0]
                if ext.lower() != "mp4":
                    print(f"🎬 Pretvarjam {input_file} -> {new_file}")
                    convert_single_file(input_file, new_file)
                elif not os.path.exists(new_file):
                    os.rename(input_file, new_file)
            else:    # for collections, to leave separate files
                for f, end in videos:
                    new_file = f.replace("." + end, ".mp4")
                    if not os.path.exists(new_file):
                        if end not in "mp4":
                            print(f"🎬 Pretvarjam {f} -> {new_file}")
                            convert_single_file(f, new_file)

        files = [(os.path.join(folder, f), f.split(".")[-1]) for f in os.listdir(folder) if os.path.isfile(os.path.join(folder, f))]
        videos = [f for f in files if f[1].lower() in {"avi", "mp4", "mkv", "vob"}]

        if len(videos) == 1:
                    
            if len(subtitles) == 1:
                if "subtitles-SloSubs.srt".lower() not in subtitles[0].lower():
                    print(f"🌍 Prevajam {folder}")
                    new_file = os.path.join(folder, "subtitles.srt")
                    os.rename(subtitles[0], new_file)
                    translate(new_file)
            elif len(subtitles) > 1:
                if os.path.join(folder, "subtitles.srt") in subtitles or os.path.join(folder, "subtitles-SloSubs-auto.srt") not in subtitles or len(subtitles) > 2:
                    print(f"⚠️⚠️ Več podnapisov v mapi: {folder}")
            
            if "slosinh" not in os.path.basename(folder).lower() and "slovenski-filmi" not in folder:
                extract_audio(folder, videos[0][0])
            for subtitle in os.listdir(folder):
                if subtitle.split(".")[-1].lower() == "srt":
                    rescale_captions(folder, os.path.join(folder, subtitle), videos[0][0])
                    convert_srt_to_vtt(os.path.join(folder, subtitle))

            # add subtitles if needed
            if len(subtitles) == 0:
                film_name = os.path.basename(folder).lower()
                if "slosinh" not in film_name and "slovenski-filmi" not in folder:
                    print(f"Pridobivam podnapise za: {folder}")
                    if os.path.exists(os.path.join(folder, "readme.json")):
                        with open(os.path.join(folder, "readme.json"), "r") as f:
                            metadata = json.loads(f.read())
                        get_subtitles(metadata["Title"], metadata["Year"], metadata["imdb_id"], folder)

        par_folder = os.sep.join(folder.split(os.sep)[:-1])
        if videos:
            folder_name = os.path.basename(folder)
            aux_folder_name = folder_name.lower().split("sub")
            if len(aux_folder_name) > 1:
                if aux_folder_name[1] not in ["", "s"]:
                    print(aux_folder_name)
                else:
                    new_folder_name = ".".join(folder_name.split(".")[:-1])
                    folder = os.path.join(par_folder, new_folder_name)
                    os.rename(os.path.join(par_folder, folder_name), folder)

            folder_name = os.path.basename(folder)
            new_folder_name = ".".join([s.capitalize() for s in folder_name.replace("-", ".").split(".")]).replace("sinh", "Sinh")
            if new_folder_name != folder_name:
                folder = os.path.join(par_folder, new_folder_name)
                os.rename(os.path.join(par_folder, folder_name), folder)

    output_films = []
    if len(videos) or "Collection" in folder:
        output_films.append(MovieMetadata(folder))

    subfolders = [os.path.join(folder, f) for f in sorted(os.listdir(folder), reverse=True) if os.path.isdir(os.path.join(folder, f))]
    if subfolders:
        if only_collect_metadata:
            for f in subfolders:
                output_films += check_folder(f, only_collect_metadata)
        else:
            for f in tqdm.tqdm(subfolders):
                output_films += check_folder(f, only_collect_metadata)
    return output_films 


if __name__ == "__main__":
    if is_ffmpeg_installed():
        scrappe_chosen()
        all_films = check_folder(FILMS_ROOT, only_collect_metadata=False)
        print("\n✅ Končano!\n")
    else:
        print("❌ FFmpeg ni nameščen! Namesti ga in poskusi znova.")

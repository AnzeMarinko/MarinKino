import datetime
import logging
import os
import pickle
import subprocess

import matplotlib.pyplot as plt
import numpy as np
import pysrt
from numba import njit
from scipy.io import wavfile
from scipy.optimize import differential_evolution

log = logging.getLogger(__name__)

_model, _utils = None, None


def get_pipeline():
    global _model
    global _utils
    if _model is None:
        import torch

        torch.backends.nnpack.enabled = False
        torch.set_num_threads(1)

        _model, _utils = torch.hub.load(
            repo_or_dir="snakers4/silero-vad",
            model="silero_vad",
            trust_repo=True,
        )
    return _model, _utils


TARGET_RATE = 100


def time_to_timestamp(t):
    return t.hour * 3600 + t.minute * 60 + t.second + t.microsecond / 1_000_000


def extract_subtitles(srt_file):
    subs = pysrt.open(srt_file)
    out_subs = []
    for sub in subs:
        out_subs.append(
            (
                time_to_timestamp(sub.start.to_time()),
                time_to_timestamp(sub.end.to_time()),
                sub.text,
            )
        )
    return out_subs


def convert_srt_to_vtt(srt_path):
    with (
        open(srt_path, "r", encoding="utf-8") as srt_file,
        open(
            srt_path[:-5] + srt_path[-5:].replace(".srt", ".vtt"),
            "w",
            encoding="utf-8",
        ) as vtt_file,
    ):
        vtt_file.write("WEBVTT\n\n")
        for line in srt_file:
            # Zamenjaj vejico z decimalno piko
            vtt_file.write(line.replace(",", "."))


def extract_audio(folder, video_path):

    voice_file = os.path.join(folder, ".detected-voice-activity.pkl")
    if not os.path.exists(voice_file):
        log.info(f"⚙ Zaznavam govor: {video_path}")
        wav_file = "output.wav"
        if os.path.exists(wav_file):
            os.remove(wav_file)

        subprocess.run(
            [
                "ffmpeg",
                "-i",
                video_path,
                "-vn",
                "-acodec",
                "pcm_s16le",
                "-ar",
                "16000",
                "-ac",
                "1",
                wav_file,
            ],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            check=True,
        )

        sr, audio = wavfile.read(wav_file)
        assert sr == 16000

        model, utils = get_pipeline()
        (get_speech_timestamps, _, _, _, _) = utils

        data = get_speech_timestamps(audio, model, sampling_rate=sr)
        DOWNSAMPLE_RATE = int(16000 / TARGET_RATE)
        reshaped = np.abs(
            audio[: len(audio) // DOWNSAMPLE_RATE * DOWNSAMPLE_RATE]
        ).reshape(-1, DOWNSAMPLE_RATE)
        envelope = reshaped.max(axis=1)
        envelope = envelope / (np.max(envelope) + 1e-9)

        speech = np.zeros(len(envelope))

        for s in data:
            start = int((s["start"] / sr) * TARGET_RATE)
            if start >= len(speech):
                continue
            end = min(int((s["end"] / sr) * TARGET_RATE), len(speech))
            speech[start:end] = np.log10(np.linspace(1, 0.2, end - start)) + 1

        with open(voice_file, "wb") as f:
            pickle.dump({"audio": envelope, "speech": speech}, f)

        if os.path.exists(wav_file):
            os.remove(wav_file)

    with open(voice_file, "rb") as f:
        voice_result = pickle.load(f)
        audio, speech = voice_result["audio"], voice_result["speech"]

    return audio, speech


# Formatiranje časa za SRT datoteko
def format_time(seconds):
    timestamp = str(datetime.timedelta(seconds=round(seconds, 3))).replace(
        ".", ","
    )[:-3]
    return ("0" if "0:" == timestamp[:2] else "") + timestamp


# Ustvarjanje SRT datoteke
def generate_srt(shift, scale, transcription_data, output_file):
    with open(output_file, "w", encoding="UTF-8") as srt_file:
        for i, (start, end, text) in enumerate(transcription_data):
            srt_file.write(f"{i + 1}\n")
            srt_file.write(
                f"{format_time(start * scale + shift)} --> {format_time(end * scale + shift)}\n"
            )
            srt_file.write(f"{text}\n\n")


# Glavna funkcija za izvleček podnapisov
def aux_rescale_captions(subtitles, speech):
    np_subtitles = np.array(
        [
            [s, e]
            for s, e, text in subtitles
            if (
                len(text) > 0
                and sum(c in text[0] + text[-1] for c in "[]{}()") < 2
            )
        ]
    )

    @njit
    def compute_score(a, b):
        aux_np_subtitles = np.clip(
            (a * np_subtitles + b) * TARGET_RATE, 0, len(speech) - 1
        )
        subtitle_score = 0.0
        for i in range(aux_np_subtitles.shape[0]):
            start_id, end_id = int(aux_np_subtitles[i, 0]), int(
                aux_np_subtitles[i, 1]
            )
            if end_id > start_id:
                subtitle_score += np.sum(
                    np.log10(np.linspace(1, 0.2, end_id - start_id))
                    + 1 * speech[start_id:end_id]
                )
        return subtitle_score

    def aux_get_subtitle_audio(a, b):
        aux_np_subtitles = np.clip(
            (a * np_subtitles + b) * TARGET_RATE, 0, len(speech) - 1
        )
        subtitle_audio = np.zeros_like(speech)
        for i in range(aux_np_subtitles.shape[0]):
            start_id, end_id = int(aux_np_subtitles[i, 0]), int(
                aux_np_subtitles[i, 1]
            )
            if end_id > start_id:
                weights = np.log10(np.linspace(1, 0.2, end_id - start_id)) + 1
                subtitle_audio[start_id:end_id] = weights
        return subtitle_audio

    current_score = compute_score(1, 0)

    def objective(params):
        a, b = params
        return -compute_score(a, b)

    bounds = [(0.93, 1.07), (-15, 15)]
    res = differential_evolution(objective, bounds, x0=[1.0, 0.0])
    best_a, best_b = res.x
    best_score = -res.fun

    log.info(
        f"Scale: {best_a * 100:.3f} %, Shift: {best_b:.3f} s, "
        f"Score improvement: {(best_score / current_score - 1) * 100:.2f} %"
    )

    return best_a, best_b, aux_get_subtitle_audio


def rescale_subtitles(folder, subtitle_path, video_path, plot=False):
    file_name = os.path.basename(subtitle_path)
    original_file = subtitle_path.replace(
        file_name, "." + file_name + ".original"
    )
    if not os.path.exists(original_file):
        audio, speech = extract_audio(folder, video_path)
        subtitles = extract_subtitles(subtitle_path)
        if subtitles and len(subtitles) >= 200:
            log.info(f"⚙ Poravnavam podnapise: {video_path}")
            scale, shift, aux_get_subtitle_audio = aux_rescale_captions(
                subtitles, speech
            )
            if abs(scale - 1) < 0.05 and abs(shift) < 10:
                generate_srt(0, 1, subtitles, original_file)
                last_sub_end = subtitles[-1][1]
                subtitles.append(
                    (
                        last_sub_end + 1,
                        last_sub_end + 20,
                        f"Podnapisi avtomatsko raztegnjeni za "
                        f"{(scale-1) * 100:.1f} %\nin zamaknjeni "
                        f"za {shift:.1f} sekund.",
                    )
                )
                generate_srt(shift, scale, subtitles, subtitle_path)
                if plot:
                    plt.figure()
                    plt.plot(audio, label="audio")
                    plt.plot(
                        aux_get_subtitle_audio(1, 0) * 0.8,
                        label="subtitles",
                    )
                    plt.plot(
                        aux_get_subtitle_audio(scale, shift) * 0.7,
                        label="best subtitles",
                    )
                    plt.plot(speech * 0.6, label="speech")
                    plt.legend()
                    plt.title(os.path.basename(folder).replace(".", " "))
                    plt.show()
        else:
            log.warning(f"Empy subtitles: {folder}")
    convert_srt_to_vtt(subtitle_path)

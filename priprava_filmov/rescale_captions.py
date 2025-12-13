import datetime
import os
import subprocess
import pysrt
from scipy.io import wavfile
import numpy as np
from numba import njit
import webrtcvad
import pickle
from scipy.optimize import differential_evolution
import matplotlib.pyplot as plt
import warnings
warnings.filterwarnings("ignore", category=UserWarning, module="webrtcvad")

TARGET_RATE = 100

def time_to_timestamp(t):
    return t.hour * 3600 + t.minute * 60 + t.second + t.microsecond / 1_000_000

def extract_subtitles(srt_file):
    subs = pysrt.open(srt_file)
    out_subs = []
    for sub in subs:
        out_subs.append((time_to_timestamp(sub.start.to_time()), time_to_timestamp(sub.end.to_time()), sub.text))
    return out_subs

def extract_audio(video_path):
    wav_file = "output.wav"
    if os.path.exists(wav_file):
        os.remove(wav_file)

    subprocess.run([
        "ffmpeg", "-i", video_path,
        "-vn",
        "-acodec", "pcm_s16le",
        "-ar", "16000",
        "-ac", "1",
        wav_file
    ], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, check=True)

    sr, data = wavfile.read(wav_file)
    assert sr == 16000

    # ---- downsample amplitude envelope (kot prej)
    DOWNSAMPLE_RATE = int(16000 / TARGET_RATE)
    reshaped = np.abs(data[:len(data)//DOWNSAMPLE_RATE * DOWNSAMPLE_RATE]).reshape(-1, DOWNSAMPLE_RATE)
    envelope = reshaped.max(axis=1)
    envelope = envelope / (np.max(envelope) + 1e-9)

    # ---- WebRTC VAD
    vad = webrtcvad.Vad(2)  # 0–3 (2 je dober kompromis)
    frame_ms = 30
    frame_len = int(16000 * frame_ms / 1000)

    speech = np.zeros(len(envelope))

    for i in range(0, len(data) - frame_len, frame_len):
        frame = data[i:i+frame_len]
        pcm = frame.astype(np.int16).tobytes()

        if vad.is_speech(pcm, 16000):
            start = int((i / 16000) * TARGET_RATE)
            end = int(((i + frame_len) / 16000) * TARGET_RATE)
            speech[start:end] = 1.0

    # ---- rahlo zgladi robove (kot tvoj fade)
    for i in range(1, len(speech)):
        if speech[i] and not speech[i-1]:
            speech[i:i+5] *= np.linspace(0.3, 1, 5)

    return envelope, speech

# Formatiranje časa za SRT datoteko
def format_time(seconds):
    timestamp = str(datetime.timedelta(seconds=round(seconds, 3))).replace(".", ",")[:-3]
    return ("0" if "0:" == timestamp[:2] else "") + timestamp

# Ustvarjanje SRT datoteke
def generate_srt(shift, scale, transcription_data, output_file):
    with open(output_file, 'w', encoding="UTF-8") as srt_file:
        for i, (start, end, text) in enumerate(transcription_data):
            srt_file.write(f"{i + 1}\n")
            srt_file.write(f"{format_time(start * scale + shift)} --> {format_time(end * scale + shift)}\n")
            srt_file.write(f"{text}\n\n")

# Glavna funkcija za izvleček podnapisov
def aux_rescale_captions(subtitles, speech):
    np_subtitles = np.array([[s, e] for s, e, text in subtitles if (len(text) > 0 and sum(c in text[0]+text[-1] for c in "[]{}()") < 2)])

    @njit
    def compute_score(a, b):
        aux_np_subtitles = np.clip((a * np_subtitles + b) * TARGET_RATE, 0, len(speech)-1)
        subtitle_score = 0.0
        for i in range(aux_np_subtitles.shape[0]):
            start_id, end_id = int(aux_np_subtitles[i, 0]), int(aux_np_subtitles[i, 1])
            if end_id > start_id:
                subtitle_score += np.sum(np.log10(np.linspace(1, 0.2, end_id - start_id)) + 1 * speech[start_id:end_id])
        return subtitle_score
    
    def aux_get_subtitle_audio(a, b):
        aux_np_subtitles = np.clip((a * np_subtitles + b) * TARGET_RATE, 0, len(speech)-1)
        subtitle_audio = np.zeros_like(speech)
        for i in range(aux_np_subtitles.shape[0]):
            start_id, end_id = int(aux_np_subtitles[i, 0]), int(aux_np_subtitles[i, 1])
            if end_id > start_id:
                weights = np.log10(np.linspace(1, 0.2, end_id - start_id)) + 1
                subtitle_audio[start_id:end_id] = weights
        return subtitle_audio

    current_score = compute_score(1, 0)

    def objective(params):
        a, b = params
        return -compute_score(a, b)

    bounds = [(0.9, 1.1), (-90, 90)]
    res = differential_evolution(objective, bounds, x0=[1.0, 0.0])
    best_a, best_b = res.x
    best_score = -res.fun

    print(f"Scale: {best_a * 100:.3f} %, Shift: {best_b:.3f} s, Score improvement: {(best_score / current_score - 1) * 100:.2f} %")

    return best_a, best_b, aux_get_subtitle_audio


def rescale_captions(folder, subtitle_path, video_path, plot=False):
    file_name = os.path.basename(subtitle_path)
    original_file = subtitle_path.replace(file_name, "." + file_name + ".original")
    if not os.path.exists(original_file):
        voice_file = os.path.join(folder, ".detected-voice-activity.pkl")
        if not os.path.exists(voice_file):
            print(f"⚙ Zaznavam govor: {video_path}")
            audio, speech = extract_audio(video_path)
            with open(voice_file, "wb") as f:
                pickle.dump({"audio": audio, "speech": speech}, f)
        else:
            with open(voice_file, "rb") as f:
                voice_result = pickle.load(f)
                audio, speech = voice_result["audio"], voice_result["speech"]
        subtitles = extract_subtitles(subtitle_path)
        if subtitles:
            if len(subtitles) < 200:
                return None
            print(f"⚙ Poravnavam podnapise: {video_path}")
            scale, shift, aux_get_subtitle_audio = aux_rescale_captions(subtitles, speech)
            if abs(scale - 1) < 0.01:
                generate_srt(0, 1, subtitles, original_file)
                last_sub_end = subtitles[-1][1]
                subtitles.append((last_sub_end+1, last_sub_end+20, f"Podnapisi avtomatsko raztegnjeni za {(scale-1) * 100:.2f} % in zamaknjeni za {shift:.3f} sekund."))
                generate_srt(shift, scale, subtitles, subtitle_path)
                return None
            if plot:
                plt.figure()
                plt.plot(audio, label="audio")
                plt.plot(aux_get_subtitle_audio(1, 0) * 0.8, label="subtitles")
                plt.plot(aux_get_subtitle_audio(scale, shift) * 0.7, label="best subtitles")
                plt.plot(speech * 0.6, label="speech")
                plt.legend()
                plt.title(os.path.basename(folder).replace(".", " "))
                plt.show()
            return audio, subtitles, speech
        else:
            print("Empy subtitles:", folder)


"""Music metadata, audio analysis, recommendation, and transitions.

FFmpeg decodes source audio to PCM; optional librosa derives normalized
features, tempo, silence boundaries, and chroma-template chord estimates.
"""

from __future__ import annotations

import json
import math
import os
import random
import subprocess
import tempfile
from pathlib import Path
from typing import Any, Mapping, Protocol, Sequence

import requests

_CACHE: dict[str, tuple[int, dict[str, Any]]] = {}
_AUDIO_ANALYSIS_VERSION = 1
_LIBROSA_ANALYSIS_VERSION = 1
_GEMINI_SEMANTIC_ANALYSIS_VERSION = "1.0"
_SAMPLE_RATE = 22050

_DEFAULT_FEATURES = {
    "tempo": 0.5,
    "energy": 0.5,
    "mood": 0.5,
    "instruments": 0.5,
}
_DEFAULT_SEMANTIC = {
    "mood": 0.5,
    "spirituality": 0.5,
    "calmness": 0.5,
    "energy": 0.5,
    "lyrical_depth": 0.5,
    "tags": [],
    "suitable_for": [],
}
_CHROMATIC_NOTES = {
    "C": 0,
    "B#": 0,
    "C#": 1,
    "DB": 1,
    "D": 2,
    "D#": 3,
    "EB": 3,
    "E": 4,
    "FB": 4,
    "E#": 5,
    "F": 5,
    "F#": 6,
    "GB": 6,
    "G": 7,
    "G#": 8,
    "AB": 8,
    "A": 9,
    "A#": 10,
    "BB": 10,
    "B": 11,
    "CB": 11,
}


class _RandomSource(Protocol):
    def choice(
        self, sequence: Sequence[Mapping[str, Any]]
    ) -> Mapping[str, Any]: ...

    def choices(
        self,
        population: Sequence[Mapping[str, Any]],
        weights: Sequence[float],
        k: int,
    ) -> list[Mapping[str, Any]]: ...


def _metadata_path(hls_dir: str | os.PathLike[str]) -> Path:
    return Path(hls_dir).expanduser().resolve() / "metadata.json"


def _default_metadata(hls_dir: str | os.PathLike[str]) -> dict[str, Any]:
    path = Path(hls_dir).expanduser().resolve()
    return {
        "audio_features": dict(_DEFAULT_FEATURES),
        "start_chord": "",
        "end_chord": "",
        "folder_path": path.parent.as_posix(),
        "silence_start_ms": 0,
        "silence_end_ms": 0,
    }


def ensure_metadata_schema(
    metadata: Mapping[str, Any] | None,
    hls_dir: str | os.PathLike[str],
) -> tuple[dict[str, Any], bool]:
    """Return metadata with recommendation fields and whether it changed."""
    result = dict(metadata or {})
    changed = False

    semantic = result.get("semantic_analysis")
    if isinstance(semantic, Mapping):
        normalized_semantic = dict(semantic)
        result["semantic_analysis"] = normalized_semantic

    features = result.get("audio_features")
    if isinstance(features, Sequence) and not isinstance(
        features, (str, bytes)
    ):
        features = {
            f"feature_{index}": value for index, value in enumerate(features)
        }
        result["audio_features"] = features
        changed = True
    elif not isinstance(features, Mapping):
        result.pop("audio_features", None)
    else:
        result["audio_features"] = dict(features)

    for key in ("start_chord", "end_chord", "folder_path"):
        value = result.get(key)
        if value is not None and not isinstance(value, str):
            result.pop(key, None)
            changed = True

    for key in ("silence_start_ms", "silence_end_ms"):
        value = result.get(key)
        if value is not None and (
            not isinstance(value, (int, float)) or value < 0
        ):
            result.pop(key, None)
            changed = True
        elif isinstance(value, float) and not value.is_integer():
            result[key] = round(value)
            changed = True

    return result, changed


def _runtime_metadata(
    metadata: Mapping[str, Any], hls_dir: Path
) -> dict[str, Any]:
    """Add neutral values only to the in-memory metadata copy."""
    result = dict(metadata)
    defaults = _default_metadata(hls_dir)
    features = result.get("audio_features")
    if not isinstance(features, Mapping):
        result["audio_features"] = dict(defaults["audio_features"])
    else:
        result["audio_features"] = {
            **_DEFAULT_FEATURES,
            **dict(features),
        }
    semantic = result.get("semantic_analysis")
    result["semantic_analysis"] = {
        **_DEFAULT_SEMANTIC,
        **(dict(semantic) if isinstance(semantic, Mapping) else {}),
    }
    for key in ("start_chord", "end_chord", "folder_path"):
        result.setdefault(key, defaults[key])
    for key in ("silence_start_ms", "silence_end_ms"):
        result.setdefault(key, defaults[key])
    return result


def _clamp_score(value: Any) -> float:
    try:
        return max(0.0, min(1.0, float(value)))
    except (TypeError, ValueError):
        return 0.5


def _parse_gemini_json(text: str) -> dict[str, Any]:
    cleaned = text.strip()
    if cleaned.startswith("```"):
        cleaned = cleaned.split("\n", 1)[-1]
        cleaned = cleaned.rsplit("```", 1)[0].strip()
    parsed = json.loads(cleaned)
    if not isinstance(parsed, Mapping):
        raise ValueError("Gemini odgovor ni JSON objekt")
    result = {}
    for key in ("mood", "spirituality", "calmness", "energy", "lyrical_depth"):
        if key in parsed:
            result[key] = _clamp_score(parsed[key])
    for key in ("tags", "suitable_for"):
        value = parsed.get(key, [])
        result[key] = (
            [str(item)[:80] for item in value[:20]]
            if isinstance(value, list)
            else []
        )
    return result


def analyze_song_semantics(
    title: str,
    artist: str = "",
    album: str = "",
) -> dict[str, Any] | None:
    """Ask Gemini for cached playlist semantics from public song metadata."""
    token = os.getenv("GEMINI_TOKEN", "").strip()
    if not token:
        return None
    model = os.getenv("GEMINI_MODEL", "gemini-2.5-flash")
    prompt = (
        "Analyze this song for smart playlist matching. Use only the title, "
        "artist, and album; do not invent factual claims. Return JSON only "
        "with numeric fields from 0.0 to 1.0: mood, spirituality, "
        "calmness, energy, lyrical_depth, plus string arrays tags and "
        "suitable_for.\n"
        f"Title: {title}\nArtist: {artist}\nAlbum: {album}"
    )
    try:
        response = requests.post(
            "https://generativelanguage.googleapis.com/v1beta/models/"
            f"{model}:generateContent",
            params={"key": token},
            json={
                "contents": [{"parts": [{"text": prompt}]}],
                "generationConfig": {
                    "temperature": 0.1,
                    "responseMimeType": "application/json",
                },
            },
            timeout=30,
        )
        response.raise_for_status()
        candidates = response.json().get("candidates", [])
        text = candidates[0]["content"]["parts"][0]["text"]
        return _parse_gemini_json(text)
    except (
        OSError,
        KeyError,
        TypeError,
        ValueError,
        requests.RequestException,
    ) as error:
        print(f"Error during Gemini semantic analysis: {error}")
        return None


def _audio_source(hls_dir: Path) -> Path | None:
    for name in ("source.mp3", "index.m3u8", "master.m3u8"):
        candidate = hls_dir / name
        if candidate.exists():
            return candidate
    return None


def _configured_backend() -> str:
    backend = os.getenv("AUDIO_ANALYZER", "auto").lower()
    if backend not in {"numpy", "librosa", "auto"}:
        return "numpy"
    if backend == "auto":
        try:
            import librosa  # noqa: F401
        except ImportError:
            return "numpy"
        return "librosa"
    return backend


def _decode_audio(audio_path: Path) -> Any:
    command = [
        "ffmpeg",
        "-v",
        "error",
        "-i",
        str(audio_path),
        "-map",
        "0:a:0",
        "-ac",
        "1",
        "-ar",
        str(_SAMPLE_RATE),
        "-f",
        "f32le",
        "-",
    ]
    completed = subprocess.run(
        command,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=False,
    )
    if completed.returncode != 0 or not completed.stdout:
        raise RuntimeError(completed.stderr.decode(errors="replace"))
    import numpy as np

    return np.frombuffer(completed.stdout, dtype=np.float32)


def _silence_bounds(samples: Any) -> tuple[int, int]:
    import numpy as np

    if samples.size == 0:
        return 0, 0
    frame_size = max(1, int(_SAMPLE_RATE * 0.02))
    frame_count = samples.size // frame_size
    if frame_count == 0:
        return 0, 0
    frames = samples[: frame_count * frame_size].reshape(
        frame_count, frame_size
    )
    rms = np.sqrt(np.mean(frames * frames, axis=1))
    threshold = max(0.0005, float(np.max(rms)) * 0.03)
    active = rms >= threshold
    if not np.any(active):
        duration = int(samples.size * 1000 / _SAMPLE_RATE)
        return duration, duration
    first = int(np.argmax(active))
    last = int(active.size - np.argmax(active[::-1]) - 1)
    start_ms = int(first * frame_size * 1000 / _SAMPLE_RATE)
    end_ms = int(
        (samples.size - (last + 1) * frame_size) * 1000 / _SAMPLE_RATE
    )
    return start_ms, max(0, end_ms)


def _estimate_tempo(samples: Any) -> float:
    import numpy as np

    frame_size = int(_SAMPLE_RATE * 0.02)
    hop = int(_SAMPLE_RATE * 0.01)
    if samples.size < frame_size * 4:
        return 0.5
    usable = samples[: ((samples.size - frame_size) // hop) * hop + frame_size]
    frames = np.lib.stride_tricks.sliding_window_view(usable, frame_size)[
        ::hop
    ]
    energy = np.sqrt(np.mean(frames * frames, axis=1))
    onset = np.maximum(0, np.diff(energy, prepend=energy[0]))
    onset -= onset.mean()
    if not np.any(onset > 0):
        return 0.5
    correlation = np.correlate(onset, onset, mode="full")[len(onset) - 1 :]
    min_lag = max(1, int(60 / 200 / 0.01))
    max_lag = min(len(correlation) - 1, int(60 / 40 / 0.01))
    if max_lag <= min_lag:
        return 0.5
    lag = min_lag + int(np.argmax(correlation[min_lag:max_lag]))
    bpm = 60 / (lag * 0.01)
    return float(np.clip((bpm - 40) / 160, 0, 1))


def _chroma(samples: Any) -> Any:
    import numpy as np

    frame_size = 4096
    hop = 2048
    if samples.size < frame_size:
        return np.zeros(12)
    window = np.hanning(frame_size)
    chroma = np.zeros(12)
    frequencies = np.fft.rfftfreq(frame_size, 1 / _SAMPLE_RATE)
    midi = np.rint(69 + 12 * np.log2(np.maximum(frequencies, 1) / 440))
    valid = (frequencies >= 65) & (frequencies <= 2000)
    classes = (midi.astype(int) % 12)[valid]
    for start in range(0, samples.size - frame_size + 1, hop):
        spectrum = np.abs(
            np.fft.rfft(samples[start : start + frame_size] * window)
        )
        for note_class in range(12):
            chroma[note_class] += float(
                spectrum[valid][classes == note_class].sum()
            )
    total = float(chroma.sum())
    return chroma / total if total else chroma


def _estimate_chord_from_chroma(chroma: Any) -> str:
    import numpy as np

    if not np.any(chroma):
        return ""
    roots = (
        "C",
        "C#",
        "D",
        "D#",
        "E",
        "F",
        "F#",
        "G",
        "G#",
        "A",
        "A#",
        "B",
    )
    best_name = ""
    best_score = -float("inf")
    for root, name in enumerate(roots):
        for quality, template in (
            (
                "maj",
                (1.0, 0.1, 0.8, 0.1, 0.9, 0.1, 0.1, 0.8, 0.1, 0.1, 0.1, 0.1),
            ),
            (
                "min",
                (1.0, 0.1, 0.8, 0.1, 0.1, 0.9, 0.1, 0.8, 0.1, 0.1, 0.1, 0.1),
            ),
        ):
            score = sum(
                chroma[(index + root) % 12] * template[index]
                for index in range(12)
            )
            if score > best_score:
                best_score = score
                best_name = f"{name}{quality}"
    return best_name


def _estimate_chord(samples: Any) -> str:
    return _estimate_chord_from_chroma(_chroma(samples))


def _normalized(value: float, minimum: float, maximum: float) -> float:
    if maximum <= minimum:
        return 0.5
    return max(0.0, min(1.0, (value - minimum) / (maximum - minimum)))


def _analyze_with_librosa(
    samples: Any,
    folder_path: str | None,
) -> dict[str, Any]:
    """Analyze PCM through optional librosa algorithms."""
    import librosa
    import numpy as np

    if samples.size == 0:
        raise RuntimeError("librosa ni dobila vzorcev zvoka")
    onset = librosa.onset.onset_strength(y=samples, sr=_SAMPLE_RATE)
    tempo = float(
        np.asarray(
            librosa.feature.tempo(onset_envelope=onset, sr=_SAMPLE_RATE)
        ).reshape(-1)[0]
    )
    rms = float(np.mean(librosa.feature.rms(y=samples)))
    centroid = float(
        np.mean(librosa.feature.spectral_centroid(y=samples, sr=_SAMPLE_RATE))
    )
    chroma = librosa.feature.chroma_stft(
        y=samples, sr=_SAMPLE_RATE, n_fft=4096, hop_length=2048
    )
    silence_start_ms, silence_end_ms = _silence_bounds(samples)
    duration = max(1, round(samples.size / _SAMPLE_RATE))
    start_sample = min(
        samples.size, int(silence_start_ms * _SAMPLE_RATE / 1000)
    )
    end_sample = max(
        start_sample, samples.size - int(silence_end_ms * _SAMPLE_RATE / 1000)
    )
    if end_sample <= start_sample:
        start_sample = 0
        end_sample = samples.size
    start_frame = start_sample // 2048
    end_frame = end_sample // 2048
    start_slice = chroma[:, start_frame : min(end_frame, start_frame + 172)]
    end_slice = chroma[:, max(start_frame, end_frame - 172) : end_frame]
    start_chroma = (
        np.mean(start_slice, axis=1)
        if start_slice.shape[1]
        else np.mean(chroma, axis=1)
    )
    end_chroma = (
        np.mean(end_slice, axis=1)
        if end_slice.shape[1]
        else np.mean(chroma, axis=1)
    )
    start_chord = _estimate_chord_from_chroma(start_chroma)
    end_chord = _estimate_chord_from_chroma(end_chroma)
    return {
        "audio_features": {
            "tempo": _normalized(tempo, 40, 200),
            "energy": float(np.clip(rms * 4, 0, 1)),
            "mood": float(np.clip(centroid / 4000, 0, 1)),
            "instruments": float(
                np.clip(
                    np.mean(
                        librosa.feature.spectral_contrast(
                            y=samples, sr=_SAMPLE_RATE
                        )
                    )
                    / 50,
                    0,
                    1,
                )
            ),
        },
        "bpm": tempo,
        "start_chord": start_chord,
        "end_chord": end_chord,
        "folder_path": folder_path or "",
        "silence_start_ms": silence_start_ms,
        "silence_end_ms": silence_end_ms,
        "duration": duration,
        "analysis_backend": "librosa",
        "audio_analysis_version": _LIBROSA_ANALYSIS_VERSION,
    }


def analyze_audio_file(
    audio_path: str | os.PathLike[str],
    folder_path: str | None = None,
) -> dict[str, Any]:
    """Compute features using configured librosa or NumPy backend."""
    path = Path(audio_path).expanduser().resolve()
    backend = _configured_backend()
    samples = _decode_audio(path)
    if backend == "librosa":
        try:
            return _analyze_with_librosa(
                samples, folder_path or path.parent.as_posix()
            )
        except (ImportError, OSError, RuntimeError, ValueError):
            if backend == "librosa":
                raise
    import numpy as np

    start_ms, end_ms = _silence_bounds(samples)
    duration_ms = int(samples.size * 1000 / _SAMPLE_RATE)
    rms = float(np.sqrt(np.mean(samples * samples)))
    clipped = float(np.mean(np.abs(samples) > 0.95))
    spectrum = np.abs(
        np.fft.rfft(samples[: min(samples.size, _SAMPLE_RATE * 30)])
    )
    spectral_centroid = float(
        np.average(
            np.fft.rfftfreq(spectrum.size * 2 - 2, 1 / _SAMPLE_RATE),
            weights=spectrum,
        )
        if spectrum.sum()
        else 0
    )
    first = samples[min(samples.size, int(start_ms * _SAMPLE_RATE / 1000)) :]
    last_end = max(0, samples.size - int(end_ms * _SAMPLE_RATE / 1000))
    last = samples[max(0, last_end - _SAMPLE_RATE * 8) : last_end]
    return {
        "audio_features": {
            "tempo": _estimate_tempo(samples),
            "energy": float(np.clip(rms * 4, 0, 1)),
            "mood": float(np.clip(spectral_centroid / 4000, 0, 1)),
            "instruments": float(np.clip(1 - clipped, 0, 1)),
        },
        "start_chord": _estimate_chord(first[: _SAMPLE_RATE * 8]),
        "end_chord": _estimate_chord(last),
        "folder_path": folder_path or path.parent.as_posix(),
        "silence_start_ms": start_ms,
        "silence_end_ms": end_ms,
        "duration": max(1, round(duration_ms / 1000)),
        "analysis_backend": "numpy",
        "audio_analysis_version": _AUDIO_ANALYSIS_VERSION,
    }


def _write_metadata_atomically(
    path: Path, metadata: Mapping[str, Any]
) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, temporary_name = tempfile.mkstemp(
        prefix=f".{path.name}.", dir=path.parent, text=True
    )
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as output:
            json.dump(metadata, output, ensure_ascii=False, indent=2)
            output.write("\n")
            output.flush()
            os.fsync(output.fileno())
        os.replace(temporary_name, path)
    finally:
        if os.path.exists(temporary_name):
            os.unlink(temporary_name)


def load_cached_metadata(
    hls_dir: str | os.PathLike[str], enrich: bool = True
) -> dict[str, Any]:
    """Load HLS metadata and cache it until metadata.json changes."""
    path = _metadata_path(hls_dir)
    try:
        mtime_ns = path.stat().st_mtime_ns
    except FileNotFoundError:
        metadata, _ = ensure_metadata_schema({}, path.parent)
        return _runtime_metadata(metadata, path.parent)

    cache_key = str(path)
    requested_backend = _configured_backend()
    cached = _CACHE.get(cache_key)
    if (
        cached
        and cached[0] == mtime_ns
        and cached[1].get("analysis_backend") == requested_backend
    ):
        return _runtime_metadata(cached[1], path.parent)

    try:
        with path.open("r", encoding="utf-8") as source:
            raw = json.load(source)
        if not isinstance(raw, Mapping):
            raise ValueError("metadata.json mora vsebovati JSON objekt")
    except (OSError, json.JSONDecodeError, ValueError):
        raw = {}

    metadata, changed = ensure_metadata_schema(raw, path.parent)
    source = _audio_source(path.parent)
    needs_analysis = metadata.get("analysis_backend") != requested_backend
    if enrich and source and needs_analysis:
        try:
            metadata.update(
                analyze_audio_file(source, metadata.get("folder_path"))
            )
            changed = True
        except (OSError, RuntimeError, ValueError) as error:
            metadata["audio_analysis_error"] = str(error)
            changed = True

    requested_semantic_analysis_version = _GEMINI_SEMANTIC_ANALYSIS_VERSION
    needs_semantic_analysis = (
        metadata.get("semantic_analysis_version")
        != requested_semantic_analysis_version
    )
    if enrich and needs_semantic_analysis:
        semantic = analyze_song_semantics(
            metadata.get("title", ""),
            metadata.get("artist", ""),
            metadata.get("album", ""),
        )
        if semantic is not None:
            metadata["semantic_analysis"] = semantic
            metadata["semantic_analysis_version"] = (
                requested_semantic_analysis_version
            )
            changed = True

    if enrich and changed:
        _write_metadata_atomically(path, metadata)
        mtime_ns = path.stat().st_mtime_ns
    _CACHE[cache_key] = (mtime_ns, dict(metadata))
    return _runtime_metadata(metadata, path.parent)


def _numeric_features(song: Mapping[str, Any]) -> list[float]:
    features = song.get("audio_features", {})
    if isinstance(features, Mapping):
        values = features.values()
    elif isinstance(features, Sequence) and not isinstance(
        features, (str, bytes)
    ):
        values = features
    else:
        return []
    return [
        float(value) for value in values if isinstance(value, (int, float))
    ]


def _feature_distance(
    song_a: Mapping[str, Any], song_b: Mapping[str, Any]
) -> float:
    values_a = _numeric_features(song_a)
    values_b = _numeric_features(song_b)
    if not values_a and not values_b:
        return 0.0
    if not values_a or not values_b or len(values_a) != len(values_b):
        return 1.0
    norm_a = math.sqrt(sum(value * value for value in values_a))
    norm_b = math.sqrt(sum(value * value for value in values_b))
    if norm_a == 0 or norm_b == 0:
        return 0.0 if values_a == values_b else 1.0
    cosine = sum(a * b for a, b in zip(values_a, values_b)) / (norm_a * norm_b)
    return min(1.0, max(0.0, 1.0 - cosine))


def _note_number(chord: Any) -> int | None:
    if not isinstance(chord, str) or not chord.strip():
        return None
    note = chord.strip().upper().replace("♭", "B").replace("♯", "#")
    note = note[:2] if len(note) > 1 and note[1] in "#B" else note[:1]
    return _CHROMATIC_NOTES.get(note)


def _chord_distance(chord_a: Any, chord_b: Any) -> float:
    note_a = _note_number(chord_a)
    note_b = _note_number(chord_b)
    if note_a is None or note_b is None:
        return 1.0 if chord_a != chord_b else 0.0
    steps = abs(note_a - note_b)
    return min(steps, 12 - steps) / 6.0


def _folder_distance(folder_a: Any, folder_b: Any) -> float:
    parts_a = Path(str(folder_a or "")).parts
    parts_b = Path(str(folder_b or "")).parts
    if parts_a == parts_b:
        return 0.0
    common = 0
    for left, right in zip(parts_a, parts_b):
        if left != right:
            break
        common += 1
    maximum = max(len(parts_a), len(parts_b), 1)
    return min(1.0, (maximum - common) / maximum)


def _semantic_distance(
    song_a: Mapping[str, Any], song_b: Mapping[str, Any]
) -> float:
    semantic_a = song_a.get("semantic_analysis", {})
    semantic_b = song_b.get("semantic_analysis", {})
    if not isinstance(semantic_a, Mapping) or not isinstance(
        semantic_b, Mapping
    ):
        return 0.0
    keys = ("mood", "spirituality", "calmness", "energy", "lyrical_depth")
    return sum(
        abs(
            _clamp_score(semantic_a.get(key))
            - _clamp_score(semantic_b.get(key))
        )
        for key in keys
    ) / len(keys)


def calculate_distance(
    song_a: Mapping[str, Any],
    song_b: Mapping[str, Any],
    weights: Mapping[str, float] | None = None,
) -> float:
    """Calculate weighted audio, harmonic, and folder distance."""
    weights = weights or {}
    audio_weight = float(weights.get("audio", weights.get("features", 1.0)))
    chord_weight = float(weights.get("chord", weights.get("harmony", 1.0)))
    folder_weight = float(weights.get("folder", 1.0))
    semantic_weight = float(weights.get("semantic", 0.0))
    return (
        audio_weight * _feature_distance(song_a, song_b)
        + chord_weight
        * _chord_distance(song_a.get("end_chord"), song_b.get("start_chord"))
        + folder_weight
        * _folder_distance(
            song_a.get("folder_path"), song_b.get("folder_path")
        )
        + semantic_weight * _semantic_distance(song_a, song_b)
    )


def select_next_song(
    current_song: Mapping[str, Any] | None,
    playlist: Sequence[Mapping[str, Any]],
    randomness_weight: float = 0.1,
    mode: str = "similar",
    rng: _RandomSource | None = None,
) -> Mapping[str, Any] | None:
    """Select a song according to mode, excluding current except in repeat."""
    if not playlist:
        return None
    rng_source: _RandomSource = rng or random  # type: ignore[assignment]
    current_id = current_song.get("id") if current_song else None
    if mode == "repeat":
        return current_song
    candidates = [song for song in playlist if song.get("id") != current_id]
    if not candidates:
        return current_song if current_song else playlist[0]
    if mode == "sequential":
        if current_id is None:
            return candidates[0]
        current_index = next(
            (
                index
                for index, song in enumerate(playlist)
                if song.get("id") == current_id
            ),
            -1,
        )
        return (
            playlist[(current_index + 1) % len(playlist)]
            if current_index >= 0
            else candidates[0]
        )
    if mode == "uniform_random":
        return rng_source.choice(candidates)

    temperature = min(1.0, max(0.1, float(randomness_weight)))
    distances = [
        calculate_distance(
            current_song or {},
            song,
            {"semantic": 0.2},
        )
        for song in candidates
    ]
    scores = [-distance / temperature for distance in distances]
    maximum = max(scores)
    probabilities = [math.exp(score - maximum) for score in scores]
    return rng_source.choices(candidates, weights=probabilities, k=1)[0]


def calculate_transition_parameters(
    current_song: Mapping[str, Any],
    next_song: Mapping[str, Any],
    crossfade_duration_ms: int = 3000,
) -> dict[str, int]:
    """Return client-side trim and crossfade timing in milliseconds."""
    crossfade = max(0, int(crossfade_duration_ms))
    current_end_silence = max(
        0, int(current_song.get("silence_end_ms", 0) or 0)
    )
    next_start_silence = max(0, int(next_song.get("silence_start_ms", 0) or 0))
    current_duration = max(
        0, int(float(current_song.get("duration", 0) or 0) * 1000)
    )
    next_duration = max(
        0, int(float(next_song.get("duration", 0) or 0) * 1000)
    )
    crossfade = min(
        crossfade, current_duration or crossfade, next_duration or crossfade
    )
    return {
        "start_time_ms": next_start_silence,
        "switch_time_ms": max(
            0, current_duration - current_end_silence - crossfade
        ),
        "crossfade_duration_ms": crossfade,
        "fade_out_duration_ms": crossfade,
        "fade_in_duration_ms": crossfade,
    }

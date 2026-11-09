"""Identify, select and normalize existing local subtitle tracks."""

import logging
import os
import re
from functools import lru_cache
from pathlib import Path

from langdetect import PROFILES_DIRECTORY, DetectorFactory, LangDetectException

from .media_tools import archive_original
from .subtitle_encoding import read_subtitle

log = logging.getLogger(__name__)

_LANGUAGES = {
    "sl": "sl",
    "slv": "sl",
    "slo": "sl",
    "slovenian": "sl",
    "slovene": "sl",
    "slovenski": "sl",
    "slosubs": "sl",
    "en": "en",
    "eng": "en",
    "english": "en",
    "ensubs": "en",
    "de": "de",
    "deu": "de",
    "ger": "de",
    "german": "de",
    "fr": "fr",
    "fra": "fr",
    "fre": "fr",
    "french": "fr",
    "hr": "hr",
    "hrv": "hr",
    "croatian": "hr",
    "sr": "sr",
    "srp": "sr",
    "serbian": "sr",
    "it": "it",
    "ita": "it",
    "italian": "it",
    "es": "es",
    "spa": "es",
    "spanish": "es",
}


class SubtitleSelectionRequiredError(ValueError):
    def __init__(self, groups):
        self.groups = groups
        super().__init__(
            "Izberi po en podnapis za vsak jezik z več različicami."
        )


def _language_from_name(name):
    standardized = re.fullmatch(
        r"subtitles-([a-z]{2}(?:-[a-z]{2})?)subs"
        r"(?:[-._ ].*)?",
        name.lower(),
    )
    if standardized:
        language = standardized.group(1)
        if language in _detector_factory().get_lang_list():
            return language
    tokens = re.findall(r"[a-z]+", name.lower())
    found = {
        _LANGUAGES[key]
        for token in tokens
        for key in (token, token[:-4] if token.endswith("subs") else token)
        if key in _LANGUAGES
    }
    return next(iter(found)) if len(found) == 1 else None


@lru_cache(maxsize=1)
def _detector_factory():
    factory = DetectorFactory()
    factory.load_profile(PROFILES_DIRECTORY)
    factory.seed = 0
    return factory


def _detect_language(path):
    content = read_subtitle(path)
    text = re.sub(r"<[^>]*>|\{[^}]*\}", " ", content)
    text = "\n".join(
        line
        for line in text.splitlines()
        if "-->" not in line
        and not re.fullmatch(r"\s*\d+\s*", line)
        and not line.startswith("WEBVTT")
    )
    if sum(char.isalpha() for char in text) < 40:
        raise ValueError(
            f"Jezika podnapisa {path.name} ni mogoče zanesljivo določiti."
        )
    try:
        detector = _detector_factory().create()
        detector.append(text)
        results = detector.get_probabilities()
    except LangDetectException as error:
        raise ValueError(
            f"Jezika podnapisa {path.name} ni mogoče zanesljivo določiti."
        ) from error
    if not results or results[0].prob < 0.9:
        raise ValueError(
            f"Jezika podnapisa {path.name} ni mogoče zanesljivo določiti."
        )
    return results[0].lang


def _tracks(folder):
    grouped = {}
    for path in sorted(folder.iterdir()):
        if path.name.startswith(".") or path.suffix.lower() not in {
            ".srt", ".vtt"
        }:
            continue
        if path.is_symlink():
            raise ValueError(f"Podnapis {path.name} je simbolična povezava.")
        if path.is_file():
            grouped.setdefault(path.stem, []).append(path)
    tracks = []
    for stem, files in grouped.items():
        if any(path.stat().st_size == 0 for path in files):
            raise ValueError(f"Podnapis {stem} je prazen; preveri datoteko.")
        names = {path.suffix.lower() for path in files}
        if len(names) != len(files):
            raise ValueError(f"Dvoumna imena podnapisov: {stem}.")
        source = next(
            (p for p in files if p.suffix.lower() == ".srt"), files[0]
        )
        language = _language_from_name(stem) or _detect_language(source)
        tracks.append((language, source.name, files))
    return tracks


def subtitle_stem(name, language, keep_downloaded=True):
    label = "Slo" if language == "sl" else language
    auto = (
        "-auto"
        if re.search(r"(?i)(?:^|[._ -])auto(?:$|[._ -])", name)
        else ""
    )
    downloaded = (
        "-Downloaded"
        if keep_downloaded
        and re.search(r"(?i)(?:^|[._ -])downloaded(?:$|[._ -])", name)
        else ""
    )
    return f"subtitles-{label}Subs{auto}{downloaded}"


def aligned_subtitle_path(path):
    path = Path(path)
    language = _language_from_name(path.stem) or _detect_language(path)
    return path.with_name(
        subtitle_stem(path.stem, language, keep_downloaded=False) + ".srt"
    )


def normalize_subtitles(folder, selection=None):
    """Return present languages and filename changes without overwriting."""
    folder = Path(folder)
    tracks = _tracks(folder)
    groups = {}
    for language, name, _files in tracks:
        groups.setdefault(language, []).append(name)
    duplicates = {
        lang: names for lang, names in groups.items() if len(names) > 1
    }
    if duplicates:
        if selection is None:
            raise SubtitleSelectionRequiredError(duplicates)
        if not isinstance(selection, dict) or set(selection) != set(
            duplicates
        ):
            raise ValueError(
                "Za vsak jezik z več podnapisi izberi eno različico."
            )
        if any(
            selection[lang] not in names for lang, names in duplicates.items()
        ):
            raise ValueError("Izbrani podnapis ne obstaja več; osveži izbor.")

    kept = [
        track
        for track in tracks
        if track[0] not in duplicates or selection[track[0]] == track[1]
    ]
    discarded = [track for track in tracks if track not in kept]
    discarded_paths = {path for _, _, files in discarded for path in files}
    moves = []
    for language, name, files in kept:
        stem = Path(name).stem
        new_stem = subtitle_stem(stem, language)
        targets = [folder / (new_stem + path.suffix.lower()) for path in files]
        for source, target in zip(files, targets):
            if source != target:
                if os.path.lexists(target) and target not in discarded_paths:
                    raise ValueError(
                        f"Ciljno ime podnapisa {target.name} je že zasedeno."
                    )
                backup = folder / ("." + source.name + ".original")
                backup_target = folder / ("." + target.name + ".original")
                if backup.exists() and os.path.lexists(backup_target):
                    raise ValueError(
                        f"Ciljno ime varnostne kopije {backup_target.name} "
                        "je že zasedeno."
                    )
                moves.append((source, target, backup, backup_target))
    for _language, name, files in discarded:
        for path in files:
            backup = folder / ("." + path.name + ".original")
            if backup.exists():
                archive_original(backup)
            archive_original(path)
        log.info("Neizbrani podnapis umaknjen v .originals: %s", name)

    changes = {}
    for source, target, backup, backup_target in moves:
        os.link(source, target, follow_symlinks=False)
        source.unlink()
        changes[source.name] = target.name
        if backup.exists():
            os.link(backup, backup_target, follow_symlinks=False)
            backup.unlink()
    return {language for language, _, _ in kept}, changes


def normalize_subtitles_interactive(folder):
    try:
        return normalize_subtitles(folder)
    except SubtitleSelectionRequiredError as error:
        selection = {}
        for language, names in error.groups.items():
            print(f"Več podnapisov za jezik {language}:")
            for index, name in enumerate(names, 1):
                print(f"  {index}. {name}")
            choice = input("Številka podnapisa za ohranitev: ").strip()
            if not choice.isdigit() or not 1 <= int(choice) <= len(names):
                raise ValueError(
                    "Neveljaven izbor podnapisa; prenos ustavljen."
                )
            selection[language] = names[int(choice) - 1]
        return normalize_subtitles(folder, selection)

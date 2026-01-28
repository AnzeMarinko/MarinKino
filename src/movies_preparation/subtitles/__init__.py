import logging
import os
from pathlib import Path

from .download_subtitles import get_subtitles
from .rescale_captions import (
    extract_audio,
    rescale_subtitles,
)
from .translate_subtitles import translate

log = logging.getLogger(__name__)


def prepare_subtitles(folder, video_file, metadata):
    folder_path = Path(folder)
    video_path = Path(video_file)
    folder_name_lower = folder_path.name.lower()

    # Preverimo, če gre za slovensko vsebino
    is_slovenian_content = (
        "slosinh" in folder_name_lower or "slovenski-filmi" in str(folder_path)
    )

    # Prenos podnapisov, če jih ni
    existing_srts = list(folder_path.glob("*.srt"))

    # Ekstrakcija zvoka (če je potrebna za kasnejšo sinhronizacijo/rescale)
    if not is_slovenian_content:
        extract_audio(str(folder_path), str(video_path))

    # Urejanje in prevajanje
    if len(existing_srts) == 1:
        srt = existing_srts[0]
        # Prevajamo samo, če še ni prevedeno (nima "slosubs" v imenu)
        if "slosubs" not in srt.name.lower():
            log.info(f"🌍 Prevajam: {srt.name}")
            standard_name = folder_path / "subtitles.srt"
            srt.rename(standard_name)
            translate(str(standard_name))
            # Osvežimo seznam, ker se je ime spremenilo/dodal se je nov
            existing_srts = list(folder_path.glob("*.srt"))

    if (
        (
            not existing_srts
            or (
                "0x-neurejeni-filmi" in folder
                and "SloSubs-auto" in "".join(metadata.subtitles)
            )
        )
        and not is_slovenian_content
        and metadata.imdb_id
    ):
        log.info(f"🔍 Pridobivam podnapise za: {folder_path.name}")
        try:
            get_subtitles(
                metadata.title,
                metadata.year,
                metadata.imdb_id,
                str(folder_path),
                languages=["sl"] if existing_srts else ["sl", "en"],
            )
            # Ponovno osvežimo seznam po prenosu
            existing_srts = list(folder_path.glob("*.srt"))
        except Exception as e:
            log.error(f"❌ Napaka pri branju metapodatkov ali prenosu: {e}")

    elif (
        (
            # "0x-neurejeni-filmi" in folder and  # TODO to nekoč odkomentiraj, ko bodo povsod tudi angleški podnapisi
            "SloSubs" in "".join(metadata.subtitles)
            and "enSubs" not in "".join(metadata.subtitles)
        )
        and not is_slovenian_content
        and metadata.imdb_id
    ):
        log.info(f"🔍 Pridobivam angleške podnapise za: {folder_path.name}")
        try:
            get_subtitles(
                metadata.title,
                metadata.year,
                metadata.imdb_id,
                str(folder_path),
                languages=["en"],
                num=1,
            )
            os.rename(
                f"{folder_path}/subtitle0.en.srt",
                f"{folder_path}/subtitles-enSubs.srt",
            )
            # Ponovno osvežimo seznam po prenosu
            existing_srts = list(folder_path.glob("*.srt"))
        except Exception as e:
            log.error(f"❌ Napaka pri branju metapodatkov ali prenosu: {e}")

    elif not is_slovenian_content and metadata.imdb_id:
        # Preverimo sumljive situacije z več podnapisi
        has_main = any(s.name == "subtitles.srt" for s in existing_srts)
        has_slo = any("slosubs" in s.name.lower() for s in existing_srts)
        has_en = any("ensubs" in s.name.lower() for s in existing_srts)

        if has_main or not has_slo or not has_en or len(existing_srts) > 2:
            log.warning(
                f"⚠️ Več podnapisov ({len(existing_srts)}) v mapi: {folder_path.name}"
            )

    # Rescale (izvedemo na vseh SRT datotekah v mapi)
    for srt in folder_path.glob("*.srt"):
        log.debug(f"📏 Prilagajam merilo (rescale): {srt.name}")
        rescale_subtitles(str(folder_path), str(srt), str(video_path))

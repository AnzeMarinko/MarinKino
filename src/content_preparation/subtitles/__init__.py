import logging
from pathlib import Path

from .download_subtitles import DOWNLOADED_MARKER, get_subtitles
from .rescale_captions import (
    apply_alignment,  # noqa: F401
    extract_audio,
    propose_alignment,  # noqa: F401
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

    existing_joined = "".join([str(f) for f in existing_srts])
    ensubs_missing = "enSubs" not in existing_joined
    slosubs_missing = "SloSubs" not in existing_joined
    is_series = ".S1E" in folder_path.name
    if (
        (ensubs_missing or slosubs_missing)
        and not is_slovenian_content
        and metadata.imdb_id
        and not is_series
    ):
        log.info(f"🔍 Pridobivam podnapise za: {folder_path.name}")
        try:
            get_subtitles(
                metadata.title,
                metadata.year,
                metadata.imdb_id,
                str(folder_path),
                languages=(["sl"] if slosubs_missing else [])
                + (["en"] if ensubs_missing else []),
            )
            # Ponovno osvežimo seznam po prenosu
            existing_srts = list(folder_path.glob("*.srt"))
        except Exception as e:
            log.error(f"❌ Napaka pri branju metapodatkov ali prenosu: {e}")

    elif not is_slovenian_content and metadata.imdb_id and not is_series:
        # Preverimo sumljive situacije z več podnapisi
        has_main = any(s.name == "subtitles.srt" for s in existing_srts)

        if (
            has_main
            or slosubs_missing
            or ensubs_missing
            or len(existing_srts) > 2
        ):
            log.warning(
                f"⚠️ Več podnapisov ({len(existing_srts)}) v mapi:"
                f" {folder_path.name}"
            )

    # Rescale (samo na podnapisih, ki smo jih sami prenesli)
    for srt in folder_path.glob(f"*{DOWNLOADED_MARKER}.srt"):
        log.debug(f"📏 Prilagajam merilo (rescale): {srt.name}")
        rescale_subtitles(str(folder_path), str(srt), str(video_path))

"""Interaktivni terminalski cevovod za pripravo novih filmov.

Za vsak film v `data/movies/0x-neurejeni-filmi` uporabnika vprašamo za
potrditev/izbiro na vsakem koraku (pretvorba videa, metapodatki, podnapisi,
poravnava, prevod). Preskočen ali končan korak/film vedno nadaljuje z
naslednjim.
"""

import json
import logging
from pathlib import Path

from .audio_preparation import process_audio_folders
from .browser_preview import (
    preview_and_confirm_alignment,
    show_subtitle_excerpts_gallery,
)
from .get_movie_metadata import MovieMetadata
from .subtitles import (
    DOWNLOADED_MARKER,
    apply_alignment,
    get_subtitles,
    propose_alignment,
    translate,
)
from .video_converter import convert_to_m3u8, convert_videos, get_videos_list

log = logging.getLogger(__name__)

INCOMING_FOLDER_NAME = "0x-neurejeni-filmi"


def ask_yes_no(prompt, default=True):
    suffix = "(Y/n)" if default else "(y/N)"
    answer = input(f"{prompt} {suffix}: ").strip().lower()
    if not answer:
        return default
    return answer.startswith("y")


def _readme_path(folder):
    return Path(folder) / "readme.json"


def _load_readme(folder):
    path = _readme_path(folder)
    if path.exists():
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    return {}


def _save_readme(folder, data):
    with open(_readme_path(folder), "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=4)


def _mark_confirmed(folder, key):
    data = _load_readme(folder)
    data.setdefault("confirmed", {})[key] = True
    _save_readme(folder, data)


def _alignment_backup_path(srt):
    """Ista poimenovalna konvencija kot v `apply_alignment` - obstoj te
    datoteke pomeni, da je bil ta podnapis že poravnan."""
    return srt.with_name("." + srt.name + ".original")


def _needs_subtitle_check(folder):
    existing = list(folder.glob("*.srt"))
    joined = "".join(f.name for f in existing)
    is_slovenian = (
        "slosinh" in folder.name.lower() or "slovenski-filmi" in str(folder)
    )
    is_series = ".S1E" in folder.name
    if is_slovenian or is_series:
        return False
    return "enSubs" not in joined or "SloSubs" not in joined


def _needs_subtitle_selection(folder):
    return len(list(folder.glob("*.srt"))) > 1


def _needs_alignment(folder):
    return any(
        not _alignment_backup_path(srt).exists()
        for srt in folder.glob(f"*{DOWNLOADED_MARKER}.srt")
    )


def _needs_translation(folder):
    srts = list(folder.glob("*.srt"))
    if not srts:
        return False
    return not any("slosubs" in s.name.lower() for s in srts)


def _has_existing_hls(folder):
    return bool(next(Path(folder).rglob("*master.m3u8"), None))


def step_convert_videos(folder):
    """KORAK 1: pretvorba videov (zbirka vs. združi v en mp4 + izvleci
    podnapise + pretvori v m3u8 se izvede kasneje v process_single_movie)."""
    videos = get_videos_list(folder)
    is_collection = ".collection" in folder.name.lower()
    if not videos:
        if _has_existing_hls(folder):
            log.info(
                f"ℹ️ HLS že obstaja za '{folder.name}', preskačem korak "
                "pretvorbe videa."
            )
            return folder, is_collection
        log.warning(f"⚠️ Ni video datotek v: {folder.name}")
        return None

    if len(videos) > 1 and not is_collection:
        is_collection = ask_yes_no(
            f"Mapa '{folder.name}' ima {len(videos)} video datotek - "
            "je to ZBIRKA (npr. risanke, epizode)?",
            default=False,
        )
        if is_collection:
            renamed = folder.with_name(f"{folder.name}.Collection")
            folder.rename(renamed)
            folder = renamed

    if not ask_yes_no(f"Pretvorim video datoteke za '{folder.name}'?"):
        log.info(f"⏭️ Preskočen film: {folder.name}")
        return None

    convert_videos(
        str(folder), collection=is_collection, merge=not is_collection
    )
    return folder, is_collection


def step_fetch_metadata(folder):
    """KORAK 2: pridobi/potrdi metapodatke (naslov, IMDb ID, opis ...)."""
    has_cached = _readme_path(folder).exists()
    if not has_cached:
        if not ask_yes_no(f"Pridobim metapodatke za '{folder.name}'?"):
            log.info("⏭️ Preskočen korak metapodatkov.")
            return None
    elif not ask_yes_no(
        f"Ponovno preverim/posodobim metapodatke za '{folder.name}'?",
        default=False,
    ):
        log.info("ℹ️ Uporabljam že obstoječe metapodatke.")

    # MovieMetadata ob obstoječem readme.json samo prebere keširane
    # podatke (brez novih vprašanj), zato lahko podnapise urejamo naprej
    # tudi, če uporabnik metapodatkov ni želel znova potrjevati.
    metadata = MovieMetadata(str(folder))
    if not metadata.imdb_id:
        log.info(
            "ℹ️ Brez potrjenega IMDb ID koraki s podnapisi ne bodo izvedeni."
        )
    return metadata


def step_check_download_subtitles(folder, metadata):
    """KORAK 3: preveri jezik podnapisov in po potrebi potegni manjkajoče."""
    existing = list(folder.glob("*.srt"))
    joined = "".join(f.name for f in existing)
    ensubs_missing = "enSubs" not in joined
    slosubs_missing = "SloSubs" not in joined
    is_slovenian = (
        "slosinh" in folder.name.lower() or "slovenski-filmi" in str(folder)
    )
    is_series = ".S1E" in folder.name

    if is_slovenian or is_series or not (ensubs_missing or slosubs_missing):
        log.info("ℹ️ Podnapisi so že v redu, samodejni prenos ni potreben.")
        return

    missing_langs = []
    if slosubs_missing:
        missing_langs.append("slovenski")
    if ensubs_missing:
        missing_langs.append("angleški")

    if not ask_yes_no(
        f"Manjkajo {' in '.join(missing_langs)} podnapisi za "
        f"'{folder.name}'. Potegnem manjkajoče?"
    ):
        log.info("⏭️ Preskočen prenos podnapisov.")
        return

    languages = (["sl"] if slosubs_missing else []) + (
        ["en"] if ensubs_missing else []
    )
    try:
        get_subtitles(
            metadata.title,
            metadata.year,
            metadata.imdb_id,
            str(folder),
            languages=languages,
        )
    except Exception as e:
        log.error(f"❌ Napaka pri prenosu podnapisov: {e}")


def step_select_subtitles(folder):
    """KORAK 4: grafično izberi, kateri podnapisi so pravi."""
    subtitle_files = sorted(folder.glob("*.srt"))
    if len(subtitle_files) <= 1:
        return
    if not ask_yes_no(
        f"Najdenih {len(subtitle_files)} podnapisov - grafično izberem, "
        "katere obdržimo?"
    ):
        return

    show_subtitle_excerpts_gallery(subtitle_files)
    for i, s in enumerate(subtitle_files, start=1):
        print(f"  {i}. {s.name}")
    choice = input(
        "Vnesi številke podnapisov za OBDRŽATI (npr. 1,3) ali Enter za vse: "
    ).strip()
    if not choice:
        return

    keep_indexes = {int(x) for x in choice.split(",") if x.strip().isdigit()}
    for i, s in enumerate(subtitle_files, start=1):
        if i not in keep_indexes:
            s.unlink(missing_ok=True)
            s.with_suffix(".vtt").unlink(missing_ok=True)
            log.info(f"🗑️ Odstranjen podnapis: {s.name}")


def step_align_subtitles(folder, video_path):
    """KORAK 5: poravnaj SAMO prenešene podnapise, ki še niso poravnani."""
    downloaded_srts = [
        srt
        for srt in sorted(folder.glob(f"*{DOWNLOADED_MARKER}.srt"))
        if not _alignment_backup_path(srt).exists()
    ]
    if not downloaded_srts:
        return

    for srt in downloaded_srts:
        if not ask_yes_no(
            f"Poravnam prenešene podnapise '{srt.name}' glede na govor v videu?"  # noqa: E501
        ):
            log.info(f"⏭️ Preskočena poravnava: {srt.name}")
            continue

        proposal = propose_alignment(str(folder), str(srt), str(video_path))
        if proposal is None:
            log.warning(f"⚠️ Premalo vrstic za poravnavo: {srt.name}")
            continue

        video_rel_path = video_path.relative_to(folder).as_posix()
        outcome = preview_and_confirm_alignment(
            folder, video_rel_path, proposal, srt.name
        )
        if outcome["confirmed"]:
            proposal["scale"] = outcome["scale"]
            proposal["shift"] = outcome["shift"]
            apply_alignment(proposal, str(srt))
            log.info(f"✅ Poravnava potrjena: {srt.name}")
        else:
            log.info(f"⏭️ Poravnava preklicana: {srt.name}")


def step_translate_missing_slovenian(folder):
    """KORAK 6: prevedi podnapise, kjer manjka slovenski prevod."""
    srts = sorted(folder.glob("*.srt"))
    if not srts or any("slosubs" in s.name.lower() for s in srts):
        return

    source = next((s for s in srts if "slosubs" not in s.name.lower()), None)
    if not source:
        return

    if ask_yes_no(
        f"Manjka slovenski prevod - prevedem '{source.name}' v slovenščino?"
    ):
        try:
            translate(str(source))
        except Exception as e:
            log.error(f"❌ Napaka pri prevajanju: {e}")
    else:
        log.info("⏭️ Preskočeno prevajanje.")


def process_single_movie(folder):
    folder = Path(folder)
    print(f"\n{'=' * 60}\n🎬 {folder.name}\n{'=' * 60}")

    result = step_convert_videos(folder)
    if result is None:
        return
    folder, is_collection = result

    videos = get_videos_list(folder)
    if not videos and not _has_existing_hls(folder):
        log.warning(f"⚠️ Ni video datotek po pretvorbi v: {folder.name}")
        return

    metadata = step_fetch_metadata(folder)

    # Podnapise lahko urejamo tudi, če je video že pretvorjen v HLS
    # (takrat surova video datoteka ne obstaja več).
    single_hls_dir = (
        metadata.video_files_m3u8[0]
        if metadata and len(metadata.video_files_m3u8) == 1
        else None
    )
    can_process_subtitles = (
        not is_collection
        and metadata
        and metadata.imdb_id
        and (len(videos) == 1 or (not videos and single_hls_dir))
    )
    if can_process_subtitles:
        video_path = (
            videos[0] if videos else folder / single_hls_dir / "master.m3u8"
        )

        if _needs_subtitle_check(folder):
            step_check_download_subtitles(folder, metadata)
            _mark_confirmed(folder, "subtitles_checked")

        if _needs_subtitle_selection(folder):
            step_select_subtitles(folder)
            _mark_confirmed(folder, "subtitles_selected")

        if _needs_alignment(folder):
            step_align_subtitles(folder, video_path)
            _mark_confirmed(folder, "subtitles_aligned")

        if _needs_translation(folder):
            step_translate_missing_slovenian(folder)
            _mark_confirmed(folder, "subtitles_translated")
    else:
        log.info(
            "ℹ️ Koraki s podnapisi se preskočijo (zbirka ali brez IMDb ID)."
        )

    for video in get_videos_list(folder):
        log.info(f"📦 Ustvarjam HLS (m3u8) za: {video.name}")
        convert_to_m3u8(str(video))


def run_interactive_pipeline(films_root):
    # KORAK 0: procesiranje audio datotek (glasba/radijske zgodbe)
    if ask_yes_no("Obdelam zvočne datoteke (glasba/radijske zgodbe)?"):
        process_audio_folders()

    incoming_root = Path(films_root) / INCOMING_FOLDER_NAME
    incoming_root.mkdir(parents=True, exist_ok=True)

    film_folders = sorted(f for f in incoming_root.iterdir() if f.is_dir())
    if not film_folders:
        log.info(f"ℹ️ Ni novih filmov za obdelavo v {incoming_root}")

    for folder in film_folders:
        try:
            process_single_movie(folder)
        except Exception as e:
            log.error(f"❌ Napaka pri obdelavi '{folder.name}': {e}")

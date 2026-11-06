import json
import logging
import os
import re
import shutil
import subprocess
import tempfile
from pathlib import Path

from .media_tools import archive_original, ffmpeg_command

log = logging.getLogger(__name__)

SUPPORTED_EXTENSIONS = {".avi", ".mp4", ".mkv", ".vob", ".mov", ".webm"}


def run_ffmpeg(command):
    """Pomožna funkcija za izvajanje FFmpeg ukazov."""
    try:
        subprocess.run(
            ffmpeg_command(command),
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            check=True,
        )
        return True
    except subprocess.CalledProcessError as e:
        log.error(f"❌ FFmpeg napaka: {e}")
        return False


def vtt_to_srt(vtt_path: Path, srt_path: Path):
    """Pretvori zunanjo VTT datoteko v SRT format."""
    try:
        content = vtt_path.read_text(encoding="utf-8")
        content = re.sub(r"^WEBVTT\s*\n*", "", content)
        content = re.sub(r"(\d{2}:\d{2}:\d{2})\.(\d{3})", r"\1,\2", content)
        srt_path.write_text(content.strip() + "\n", encoding="utf-8")
        log.info(f"📝 Pretvori podnapise: {vtt_path.name} -> {srt_path.name}")
        return True
    except Exception as e:
        log.error(f"❌ Napaka pri pretvorbi VTT v SRT ({vtt_path.name}): {e}")
        return False


def extract_subtitles_to_srt(video_path: Path, base_srt_path: Path):
    """Ekstrahira vse vgrajene podnapise v ločene SRT datoteke."""
    probe_cmd = [
        "ffprobe",
        "-v",
        "error",
        "-select_streams",
        "s",
        "-show_entries",
        "stream=index:stream_tags=language,title",
        "-of",
        "json",
        str(video_path),
    ]

    try:
        result = subprocess.run(
            probe_cmd, capture_output=True, text=True, check=True
        )
        data = json.loads(result.stdout)
    except Exception as e:
        log.error(
            f"❌ Napaka pri branju metapodatkov iz {video_path.name}: {e}"
        )
        return False

    streams = data.get("streams", [])
    if not streams:
        log.info(f"ℹ️ {video_path.name} ne vsebuje vgrajenih podnapisov.")
        return False

    base_srt_path.parent.mkdir(parents=True, exist_ok=True)
    log.info(
        f"📂 Najdenih {len(streams)} podnapisov v {video_path.name}. "
        "Začenjam ekstrakcijo..."
    )

    files = []

    # 2. Gremo čez vsako najdeno sled podnapisov
    for i, stream in enumerate(streams):
        stream_index = stream.get(
            "index"
        )  # Absolutni indeks v FFmpeg (npr. 2, 3...)

        # Poskusimo dobiti jezik (npr. 'sl', 'en'), sicer uporabimo indeks
        tags = stream.get("tags", {})
        lang = re.sub(
            r"[^a-zA-Z0-9_-]", "_", tags.get("language", f"track_{i + 1}")
        )
        title = re.sub(r"[^a-zA-Z0-9_-]", "_", tags.get("title", ""))

        # Sestavimo unikatno ime za vsak podnapis
        # Primer: film.sl.srt ali film.eng.srt
        suffix = f".{lang}"
        if title:
            suffix += f"_{title}"
        if suffix in files:
            suffix += f"_{i + 1}"  # Dodamo indeks, če je ime že uporabljeno
        files.append(suffix)

        srt_output_path = base_srt_path.with_suffix(f"{suffix}.srt")
        if srt_output_path.exists():
            continue

        # FFmpeg ukaz za ekstrakcijo specifične sledi
        #  (mapira se točno določen indeks stream-a)
        extract_cmd = [
            "ffmpeg",
            "-y",
            "-i",
            str(video_path),
            "-map",
            f"0:{stream_index}",
            "-c:s",
            "srt",
            str(srt_output_path),
        ]

        log.info(
            f"📝 Ekstrahiram sled {stream_index} -> {srt_output_path.name}"
        )

        try:
            subprocess.run(
                extract_cmd,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                check=True,
            )
        except subprocess.CalledProcessError:
            log.error(
                f"❌ Ni uspelo ekstrahirati podnapisa "
                f"z indeksom {stream_index}"
            )

    return True


def convert_to_mp4(input_path: Path, output_path: Path):
    """
    Enotna vstopna točka za obdelavo vseh video datotek.

    1. Če je datoteka že MP4, uporabi 'ensure_aac_audio' za morebitne popravke
       videa/zvoka na sami datoteki, nato jo preimenuje
       v končno ime (output_path).
    2. Če je datoteka drugega formata (MKV, AVI...), jo pretvori v MP4.
    """
    input_path = Path(input_path)
    output_path = Path(output_path)

    # --- SCENARIJ 1: Datoteka je že MP4 ---
    if input_path.suffix.lower() == ".mp4":
        log.info(
            f"📱 Datoteka {input_path.name} je že MP4."
            " Preverjam združljivost..."
        )

        # Popravimo avdio/video parametre znotraj obstoječega MP4 datoteke
        if not ensure_aac_audio(input_path):
            return False

        # Če se ciljna pot razlikuje od trenutne,
        # datoteko varno prestavimo/preimenujemo
        if input_path != output_path:
            if output_path.exists():
                raise FileExistsError(f"Cilj že obstaja: {output_path}")
            try:
                # Ustvarimo ciljno mapo, če slučajno še ne obstaja
                output_path.parent.mkdir(parents=True, exist_ok=True)
                input_path.rename(output_path)
                log.info(
                    f"✅ MP4 datoteka uspešno prestavljena na "
                    f"končno mesto: {output_path.name}"
                )
            except Exception as e:
                log.error(f"❌ Napaka pri preimenovanju MP4 datoteke: {e}")
                return False
        return True

    destination = output_path
    if destination.exists():
        raise FileExistsError(f"Cilj že obstaja: {destination}")
    output_path = destination.with_name(f".{destination.stem}.converting.mp4")

    # --- SCENARIJ 2: Datoteka NI MP4 (MKV, AVI, MOV...) ---
    log.info(
        f"🎬 Pretvarjam vsebnik v MP4: {input_path.name} -> {output_path.name}"
    )

    # Ekstrakcija podnapisov zraven novega videa (preden se karkoli pobriše)
    srt_output_path = destination.with_suffix(".srt")
    extract_subtitles_to_srt(input_path, srt_output_path)

    # Preverimo video kodek in barvni profil izvorne datoteke s ffprobe
    probe_cmd = [
        "ffprobe",
        "-v",
        "error",
        "-select_streams",
        "v:0",
        "-show_entries",
        "stream=codec_name,pix_fmt",
        "-of",
        "json",
        str(input_path),
    ]

    can_copy_video = False
    try:
        result = subprocess.run(
            probe_cmd, capture_output=True, text=True, check=True
        )
        probe_data = json.loads(result.stdout)

        if "streams" in probe_data and len(probe_data["streams"]) > 0:
            stream = probe_data["streams"][0]
            codec = stream.get("codec_name", "").lower()
            pix_fmt = stream.get("pix_fmt", "").lower()

            log.info(f"🔍 Zaznan video format: {codec} ({pix_fmt})")

            # Hitro kopiranje (remux) je varno samo za standarden
            # 8-bitni H.264 video
            if codec == "h264" and pix_fmt in ("yuv420p", "yuvj420p"):
                can_copy_video = True

    except Exception as e:
        log.warning(
            f"⚠️ ffprobe ni uspel analizirati videa ({e})."
            " Izvedena bo polna pretvorba."
        )

    # FAST PATH: Hitro kopiranje videa, če je kompatibilen, zvok pa v AAC
    if can_copy_video:
        log.info(
            "⚡️ Video je kompatibilen! Kopiram video in pretvarjam le zvok..."
        )
        fast_command = [
            "ffmpeg",
            "-y",
            "-i",
            str(input_path),
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
            str(output_path),
        ]

        if run_ffmpeg(fast_command):
            log.info("✅ Hitro kopiranje uspešno končano!")
            output_path.replace(destination)
            archive_original(input_path)
            return True
        else:
            log.warning(
                "⚠️ Hitro kopiranje je spodletelo. Preklapljam na polno "
                "pretvorbo..."
            )

    # FALLBACK PATH: Polna pretvorba (H.264 8-bit + AAC)
    log.info("⚙️ Začenjam polno pretvorbo videa in zvoka (H.264 + AAC)...")
    full_command = [
        "ffmpeg",
        "-y",
        "-i",
        str(input_path),
        "-c:v",
        "libx264",
        "-pix_fmt",
        "yuv420p",
        "-preset",
        "fast",
        "-crf",
        "22",
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

    if run_ffmpeg(full_command):
        log.info("✅ Uspešna polna pretvorba v varen MP4.")
        output_path.replace(destination)
        archive_original(input_path)
        return True

    output_path.unlink(missing_ok=True)
    return False


def ensure_aac_audio(filepath):
    """
    Skrbi za obstoječe MP4 datoteke.
    1. Preveri, ali je video varen za splet (H.264 8-bit).
    Če ni, ga polno pretvori.
    2. Preveri, ali ima datoteka vključen faststart (moov atom na začetku).
    3. Če je video v redu, a zvok ni AAC ali manjka faststart,
    hitro popravi brez polne pretvorbe videa.
    """
    filepath = Path(filepath)

    # Vključimo 'format' v show_entries, da dobimo splošne podatke o vsebniku
    probe_cmd = [
        "ffprobe",
        "-v",
        "error",
        "-show_entries",
        "stream=codec_name,pix_fmt,codec_type:format=format_name,is_streamable",  # noqa E501
        "-of",
        "json",
        str(filepath),
    ]

    video_ok = False
    audio_is_aac = False
    is_faststart = False

    try:
        result = subprocess.run(
            probe_cmd, capture_output=True, text=True, check=True
        )
        probe_data = json.loads(result.stdout)

        # 1. Preverjanje tokov (streams)
        for stream in probe_data.get("streams", []):
            codec_type = stream.get("codec_type")
            codec_name = stream.get("codec_name", "").lower()

            if codec_type == "video":
                pix_fmt = stream.get("pix_fmt", "").lower()
                if codec_name == "h264" and pix_fmt in ("yuv420p", "yuvj420p"):
                    video_ok = True

            elif codec_type == "audio":
                if codec_name == "aac":
                    audio_is_aac = True

        # 2. Preverjanje faststart (iščemo 'is_streamable' v format podatkih)
        # FFprobe vrne 'is_streamable': '1' (ali true v JSON), če je moov
        #  na začetku
        format_info = probe_data.get("format", {})
        # Alternativno: nekateri FFprobe sistemi vrnejo 'is_streamable'
        # kot niz "true"/"1"
        is_streamable = format_info.get("is_streamable")
        if is_streamable in (1, "1", "true", True):
            is_faststart = True

    except Exception as e:
        log.error(f"❌ Napaka pri analizi MP4 datoteke {filepath.name}: {e}")
        return False

    # Če je vse že popolno optimizirano, končamo
    if video_ok and audio_is_aac and is_faststart:
        log.info(
            f"ℹ️ MP4 datoteka je že optimalna za splet "
            f"(vključno s faststart): {filepath.name}"
        )
        return True

    # Če video NI kompatibilen, polna pretvorba (ta že vključuje +faststart)
    if not video_ok:
        log.warning(
            "⚠️ MP4 vsebuje nezdružljiv video format. Začenjam polno "
            f"popravilo: {filepath.name}"
        )
        temp_file = filepath.with_suffix(".tmp.mp4")
        extract_subtitles_to_srt(filepath, filepath)

        command = [
            "ffmpeg",
            "-y",
            "-i",
            str(filepath),
            "-c:v",
            "libx264",
            "-pix_fmt",
            "yuv420p",
            "-preset",
            "fast",
            "-crf",
            "22",
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
            archive_original(filepath)
            temp_file.replace(filepath)
            log.info("✅ MP4 uspešno polno pretvorjen v združljiv format.")
            return True
        temp_file.unlink(missing_ok=True)
        return False

    # Če je video OK, a zvok NI AAC ALI pa manjka samo faststart
    # Tukaj uporabimo hitro kopiranje videa (-c:v copy)
    if not audio_is_aac or not is_faststart:
        action_msg = (
            "Popravljam samo zvok (AAC)"
            if not audio_is_aac
            else "Dodajam faststart indeks"
        )
        if not audio_is_aac and not is_faststart:
            action_msg = "Popravljam zvok in dodajam faststart"

        log.info(f"🔊 {action_msg} za MP4: {filepath.name}")
        temp_file = filepath.with_suffix(".tmp.mp4")
        extract_subtitles_to_srt(filepath, filepath)

        # Če je zvok že AAC, ga samo kopiramo, sicer ga prekodiramo
        audio_codec = "copy" if audio_is_aac else "aac"

        command = [
            "ffmpeg",
            "-y",
            "-i",
            str(filepath),
            "-c:v",
            "copy",  # Video samo kopiramo (instantno)
            "-c:a",
            audio_codec,  # Zvok kopiramo ali pretvorimo v AAC
        ]

        # Če prekodiramo zvok, dodamo parametre za kakovost
        if audio_codec == "aac":
            command.extend(["-ac", "2", "-b:a", "128k"])

        # Vedno dodamo faststart na koncu
        command.extend(["-movflags", "+faststart", str(temp_file)])

        if run_ffmpeg(command):
            archive_original(filepath)
            temp_file.replace(filepath)
            log.info("✅ Hitra optimizacija uspešno zaključena.")
            return True
        temp_file.unlink(missing_ok=True)
        return False


def get_videos_list(folder):
    """Vrne seznam Path objektov za podprte video datoteke."""
    p = Path(folder)
    return [
        f
        for f in p.iterdir()
        if f.is_file()
        and not f.name.startswith(".")
        and f.suffix.lower() in SUPPORTED_EXTENSIONS
        and not f.name.endswith((".tmp.mp4", ".temp_conv.mp4"))
    ]


def convert_videos(folder, merge=False, collection=False):
    folder_path = Path(folder)
    videos = sorted(get_videos_list(folder_path))

    if not videos:
        return []

    final_output = folder_path / f"{folder_path.name}.mp4"

    if collection or ".collection" in folder_path.name.lower():
        for video in videos:
            if not convert_to_mp4(video, video.with_suffix(".mp4")):
                raise RuntimeError(f"Pretvorba ni uspela: {video.name}")

    elif (
        merge and len(videos) > 1 and "series" not in str(folder_path).lower()
    ):
        log.info(f"Združujem {len(videos)} delov v {final_output.name} …")
        # Stage links, not source renames: a failed part leaves every input
        # available for the next run and never publishes a partial movie.
        with tempfile.TemporaryDirectory(
            prefix=".merge-", dir=folder_path
        ) as temporary:
            staging = Path(temporary)
            parts = []
            for index, video in enumerate(videos):
                extract_subtitles_to_srt(video, video.with_suffix(".srt"))
                linked = staging / f"source-{index}{video.suffix}"
                os.link(video, linked)
                target = staging / f"part-{index}.mp4"
                if not convert_to_mp4(linked, target):
                    raise RuntimeError(
                        f"Pretvorba dela ni uspela: {video.name}"
                    )
                parts.append(target)
            list_file = staging / "concat.txt"
            list_file.write_text(
                "".join(f"file '{part.name}'\n" for part in parts),
                encoding="utf-8",
            )
            merged = staging / "merged.mp4"
            if not run_ffmpeg(
                [
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
                    str(merged),
                ]
            ):
                raise RuntimeError(
                    "Združevanje ni uspelo; vsi izvori so ohranjeni."
                )
            for video in videos:
                archive_original(video)
            merged.replace(final_output)

    elif len(videos) == 1:
        video = videos[0]
        if not convert_to_mp4(video, final_output):
            raise RuntimeError(f"Pretvorba ni uspela: {video.name}")

    return get_videos_list(folder)


def convert_to_m3u8(video_path):
    """
    Spremeni klasičen MP4 film v HLS format (master.m3u8) z ločenimi tokovi.
    Zastavice -movflags fragmentirajo začasne MP4 datoteke, da niso
    več 'faststart'.
    """
    abs_original = os.path.abspath(video_path)
    original = Path(abs_original)

    if not original.exists():
        log.error(f"Datoteka ne obstaja: {original}")
        return False

    # Ustvarimo mapo z imenom brez .mp4
    mapa = Path(os.path.abspath(original.with_suffix("")))
    mapa.mkdir(parents=True, exist_ok=True)

    destination = mapa
    if all(
        (destination / name).is_file() and (destination / name).stat().st_size
        for name in ("master.m3u8", "video.ts", "audio.ts")
    ):
        log.info("HLS že obstaja: %s", destination)
        return True
    temporary = tempfile.TemporaryDirectory(prefix=".hls-", dir=destination)
    mapa = Path(temporary.name)

    # Začasne datoteke (fragmentirane)
    tmp_video = mapa / "tmp_raw_video.mp4"
    tmp_audio = mapa / "tmp_raw_audio.mp4"

    # Končni izhodi v mapi
    out_video = mapa / "video.ts"
    out_audio = mapa / "audio.ts"
    master_dash = mapa / "master.mpd"
    master_hls = mapa / "master.m3u8"

    if master_hls.exists():
        log.info(f"ℹ️ HLS že obstaja za {original.name}. Preskočim pretvorbo.")
        return True

    # FFmpeg parametri za fragmentiran MP4
    # (prepreči faststart/buffer napake v Shaka)
    frag_opts = ["-movflags", "empty_moov+default_base_moof+frag_keyframe"]

    try:
        # ==========================================
        # KORAK 1: Preverjanje video kodeka in višine prek ffprobe
        # ==========================================
        log.info("🔍 Preverjam video kodek...")
        probe_codec_cmd = [
            "ffprobe",
            "-v",
            "error",
            "-select_streams",
            "v:0",
            "-show_entries",
            "stream=codec_name",
            "-of",
            "default=noprint_wrappers=1:nokey=1",
            abs_original,
        ]
        probe_codec_res = subprocess.run(
            probe_codec_cmd, capture_output=True, text=True, check=True
        )
        video_codec = probe_codec_res.stdout.strip()

        # Nastavitve za primarni video (HD oz. originalna kakovost)
        if video_codec != "h264":
            log.warning(
                f"⚠️ Kodek je '{video_codec}'. Prekodiram video v H.264..."
            )
            video_transcode_args = [
                "-c:v",
                "libx264",
                "-preset",
                "veryfast",
                "-crf",
                "26",
            ]
        else:
            log.info("🎬 Kopiram video tok...")
            video_transcode_args = ["-c:v", "copy", "-map", "0:v:0"]

        # ==========================================
        # KORAK 2: FFmpeg Demuxing & Kodiranje (Fragmentiran MP4 izhod)
        # ==========================================
        # 2a. Primarni video (Originalna ločljivost)
        subprocess.run(
            ffmpeg_command(
                ["ffmpeg", "-y", "-i", abs_original, "-an"]
                + video_transcode_args
                + frag_opts
                + [str(tmp_video)]
            ),
            check=True,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )

        # 2b. avdio del
        log.info("🎵 Kopiram zvočni tok...")
        subprocess.run(
            ffmpeg_command(
                [
                    "ffmpeg",
                    "-y",
                    "-i",
                    abs_original,
                    "-vn",
                    "-c:a",
                    "copy",
                    "-map",
                    "0:a:0",
                ]
                + frag_opts
                + [str(tmp_audio)]
            ),
            check=True,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )

        # ==========================================
        # KORAK 3: Shaka Packager pakira v HLS
        # ==========================================
        log.info("📦 Shaka Packager pakira v HLS...")

        shaka_in_video = str(tmp_video).replace(",", "\\,")
        shaka_in_audio = str(tmp_audio).replace(",", "\\,")
        shaka_out_video = str(out_video).replace(",", "\\,")
        shaka_out_audio = str(out_audio).replace(",", "\\,")
        shaka_master_dash = str(master_dash).replace(",", "\\,")
        shaka_master_hls = str(master_hls).replace(",", "\\,")

        # Priprava bazičnega klica
        packager_cmd = ["packager"]

        # Dodamo HD video
        packager_cmd.append(
            f"in={shaka_in_video},stream=video,output={shaka_out_video},format=mp4"  # noqa E501
        )

        # Prvi avdio tok
        packager_cmd.append(
            f"in={shaka_in_audio},stream=audio,output={shaka_out_audio},format=mp4"  # noqa E501
        )

        # Dodamo izhodne poti
        packager_cmd.extend(
            [
                "--mpd_output",
                shaka_master_dash,
                "--hls_master_playlist_output",
                shaka_master_hls,
            ]
        )

        # Ustvarimo začasno mapo na NVMe disku za Shaka Packager buffer
        shaka_tmp_dir = mapa / "shaka_tmp"
        shaka_tmp_dir.mkdir(exist_ok=True)

        # Pripravimo okoljske spremenljivke s preusmeritvijo začasne mape
        custom_env = os.environ.copy()
        custom_env["TMPDIR"] = str(shaka_tmp_dir)

        try:
            subprocess.run(
                packager_cmd,
                check=True,
                capture_output=True,
                text=True,
                env=custom_env,  # Prisilimo Shako, da piše na NVMe
            )
        finally:
            # Varno počistimo Shaka začasni direktorij takoj ko konča
            # (uspešno ali ne)
            if shaka_tmp_dir.exists():
                shutil.rmtree(shaka_tmp_dir, ignore_errors=True)

        # ==========================================
        # KORAK 4: Popravilo absolutnih poti v master.m3u8 v relativne
        # ==========================================
        if master_hls.exists():
            log.info(
                "🛠️ Popravljam absolutne poti v master.m3u8 v relativne..."
            )
            vsebina = master_hls.read_text(encoding="utf-8")
            pot_mape = str(mapa) + "/"
            popravljena_vsebina = vsebina.replace(pot_mape, "")
            master_hls.write_text(popravljena_vsebina, encoding="utf-8")

        # ==========================================
        # KORAK 5: Čiščenje
        # ==========================================
        log.info("🧹 Čiščenje začasnih datotek...")
        master_dash.unlink(missing_ok=True)
        tmp_video.unlink(missing_ok=True)
        tmp_audio.unlink(missing_ok=True)
        if (
            not master_hls.is_file()
            or not out_video.is_file()
            or not out_audio.is_file()
        ):
            raise RuntimeError(
                "HLS izhod ni popoln; izvorni video ostane ohranjen."
            )
        # Publish segments and child playlists before the master playlist.
        for output in sorted(
            mapa.iterdir(), key=lambda path: path.name == "master.m3u8"
        ):
            output.replace(destination / output.name)
        archive_original(original)
        (original.parent / ".detected-voice-activity.pkl").unlink(
            missing_ok=True
        )
        log.info(f"🎉 Uspešno ustvarjen HLS za film: {original.name}")
        return True

    except subprocess.CalledProcessError as e:
        log.error("❌ Napaka med izvajanjem zunanjega procesa!")
        log.error(f"STDOUT: {e.stdout}")
        log.error(f"STDERR: {e.stderr}")
        master_dash.unlink(missing_ok=True)
        tmp_video.unlink(missing_ok=True)
        tmp_audio.unlink(missing_ok=True)
        if mapa.exists():
            shutil.rmtree(mapa, ignore_errors=True)
        return False
    except Exception as e:
        log.error(f"❌ Splošna napaka: {e}")
        master_dash.unlink(missing_ok=True)
        tmp_video.unlink(missing_ok=True)
        tmp_audio.unlink(missing_ok=True)
        if mapa.exists():
            shutil.rmtree(mapa, ignore_errors=True)
        return False
    finally:
        temporary.cleanup()

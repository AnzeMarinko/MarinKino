import json
import logging
import os
import re
import subprocess
from pathlib import Path

from .helpers import remove

log = logging.getLogger(__name__)

SUPPORTED_EXTENSIONS = {".avi", ".mp4", ".mkv", ".vob", ".mov"}


def run_ffmpeg(command):
    """Pomožna funkcija za izvajanje FFmpeg ukazov."""
    try:
        subprocess.run(
            command,
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
        # Odstranimo WEBVTT glavo
        content = re.sub(r"^WEBVTT\s*\n*", "", content)
        # Zamenjamo pike v časovnih oznakah z vejicami
        content = re.sub(r"(\d{2}:\d{2}:\d{2})\.(\d{3})", r"\1,\2", content)
        srt_path.write_text(content.strip() + "\n", encoding="utf-8")
        log.info(f"📝 Pretvori podnapise: {vtt_path.name} -> {srt_path.name}")
        return True
    except Exception as e:
        log.error(f"❌ Napaka pri pretvorbi VTT v SRT ({vtt_path.name}): {e}")
        return False


def extract_subtitles_to_srt(video_path: Path, base_srt_path: Path):
    """
    Poišče vse sledi podnapisov v MKV/videu in vsako posebej
    ekstrahira v svojo .srt datoteko z oznako jezika in indeksa.
    """
    if base_srt_path.parent.exists():
        return True
    base_srt_path.parent.mkdir(parents=True, exist_ok=True)
    # 1. Pridobimo podatke o vseh podnapisih z ffprobe (v JSON formatu)
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
        lang = tags.get("language", f"track_{i + 1}")
        title = tags.get("title", "").replace(" ", "_")

        # Sestavimo unikatno ime za vsak podnapis
        # Primer: film.sl.srt ali film.eng.srt
        suffix = f".{lang}"
        if title:
            suffix += f"_{title}"
        if suffix in files:
            suffix += f"_{i + 1}"  # Dodamo indeks, če je ime že uporabljeno
        files.append(suffix)

        srt_output_path = base_srt_path.with_suffix(f"{suffix}.srt")

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
        ensure_aac_audio(input_path)

        # Če se ciljna pot razlikuje od trenutne,
        # datoteko varno prestavimo/preimenujemo
        if input_path != output_path:
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

    # --- SCENARIJ 2: Datoteka NI MP4 (MKV, AVI, MOV...) ---
    log.info(
        f"🎬 Pretvarjam vsebnik v MP4: {input_path.name} -> {output_path.name}"
    )

    # Ekstrakcija podnapisov zraven novega videa (preden se karkoli pobriše)
    srt_output_path = output_path.with_suffix("") / "subtitles.srt"
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
            # remove(str(input_path))  # Odkomentiraj po testiranju
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
        # remove(str(input_path))  # Odkomentiraj po testiranju
        return True

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
        "stream=codec_name,pix_fmt,codec_type:format=format_name",
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
        return

    # Če je vse že popolno optimizirano, končamo
    if video_ok and audio_is_aac and is_faststart:
        log.info(
            f"ℹ️ MP4 datoteka je že optimalna za splet "
            f"(vključno s faststart): {filepath.name}"
        )
        return

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
            temp_file.replace(filepath)
            log.info("✅ MP4 uspešno polno pretvorjen v združljiv format.")
        return

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
            temp_file.replace(filepath)
            log.info("✅ Hitra optimizacija uspešno zaključena.")

    # Če je video OK, a zvok NI AAC (npr. MP4 z DTS ali AC3 zvokom),
    # prekodiramo SAMO zvok
    if not audio_is_aac:
        log.info(f"🔊 Popravljam samo zvok (AAC) za MP4: {filepath.name}")
        temp_file = filepath.with_suffix(".tmp.mp4")

        # Shranimo podnapise pred spremembo
        extract_subtitles_to_srt(filepath, filepath)

        command = [
            "ffmpeg",
            "-y",
            "-i",
            str(filepath),
            "-c:v",
            "copy",  # Video samo kopiramo (brez izgub, instantno)
            "-c:a",
            "aac",  # Zvok pretvorimo v AAC
            "-ac",
            "2",
            "-b:a",
            "128k",
            "-movflags",
            "+faststart",
            str(temp_file),
        ]

        if run_ffmpeg(command):
            temp_file.replace(filepath)
            log.info("✅ Zvok uspešno popravljen.")


def get_videos_list(folder):
    """Vrne seznam Path objektov za podprte video datoteke."""
    p = Path(folder)
    return [
        f
        for f in p.iterdir()
        if f.is_file() and f.suffix.lower() in SUPPORTED_EXTENSIONS
    ]


def convert_videos(folder):
    folder_path = Path(folder)
    videos = sorted(get_videos_list(folder_path))

    if not videos:
        return []

    # 1. faza: Poskrbi, da so vsi obstoječi MP4 v AAC formatu
    for video in videos:
        if video.suffix.lower() == ".mp4":
            ensure_aac_audio(video)

    final_output = folder_path / f"{folder_path.name}.mp4"

    # 2. faza: Logika združevanja ali pretvorbe
    if ".Collection" in folder_path.name:
        # Za zbirke samo pretvori posamezne datoteke v MP4, ne združuj
        for video in videos:
            if video.suffix.lower() != ".mp4":
                convert_to_mp4(video, video.with_suffix(".mp4"))

    elif len(videos) > 1 and "series" not in str(folder_path).lower():
        # Združevanje več datotek
        log.info(f"🔄 Združujem {len(videos)} videov v {final_output.name}...")
        # zdruzi le izrecno izbrane mape, da ne bo združeval vseh po defaultu
        if folder in []:
            temp_mp4s = []

            for v in videos:
                target = v.with_suffix(".temp_conv.mp4")
                if convert_to_mp4(v, target):
                    temp_mp4s.append(target)

            # Ustvari temp_list za concat
            list_file = folder_path / "temp_list.txt"
            with list_file.open("w", encoding="utf-8") as f:
                for tmp in temp_mp4s:
                    f.write(f"file '{tmp.name}'\n")

            concat_cmd = [
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
                str(final_output),
            ]

            if run_ffmpeg(concat_cmd):
                for tmp in temp_mp4s:
                    remove(str(tmp))
                remove(str(list_file))

    elif len(videos) == 1:
        # Samo ena datoteka
        video = videos[0]
        if video.suffix.lower() != ".mp4":
            convert_to_mp4(video, final_output)
        else:
            video.rename(final_output)

    return get_videos_list(folder)


def convert_to_m3u8(video_path):
    """
    Spremeni klasičen MP4 film v HLS format (master.m3u8) z ločenimi tokovi.
    Zastavice -movflags fragmentirajo začasne MP4 datoteke, da niso
    več 'faststart'.

    Če je višina videa > 480p, ustvari dodatno 480p LD različico
    za slabe povezave,
    sicer pa obdrži le eno (originalno) kvaliteto.
    """
    is_chosen_series = "the-chosen-series" in str(video_path).lower()
    abs_original = os.path.abspath(video_path)
    original = Path(abs_original)

    if not original.exists():
        log.error(f"Datoteka ne obstaja: {original}")
        return False

    if is_chosen_series and "_Slo" in original.name:
        return False

    second_audio_path = None
    if is_chosen_series:
        second_audio_candidate = original.with_name(
            original.stem.replace("_Eng", "_Slo") + original.suffix
        )
        if second_audio_candidate.exists():
            second_audio_path = second_audio_candidate

    # Ustvarimo mapo z imenom brez .mp4
    mapa = Path(os.path.abspath(original.with_suffix("")))
    if is_chosen_series:
        mapa = mapa.with_name(mapa.name.replace("_Eng", ""))
    mapa.mkdir(parents=True, exist_ok=True)

    # Začasne datoteke (fragmentirane)
    tmp_video_hd = mapa / "tmp_raw_video_hd.mp4"
    tmp_video_ld = mapa / "tmp_raw_video_ld.mp4"
    tmp_audio1 = mapa / "tmp_raw_audio1.mp4"
    tmp_audio2 = mapa / "tmp_raw_audio2.mp4"

    # Končni izhodi v mapi
    out_video_hd = mapa / "video.mp4"
    out_video_ld = mapa / "video_ld.mp4"
    out_audio1 = mapa / "audio.mp4"
    out_audio2 = mapa / "audio2.mp4"
    master_dash = mapa / "master.mpd"
    master_hls = mapa / "master.m3u8"

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

        log.info("📏 Preverjam višino videa...")
        probe_height_cmd = [
            "ffprobe",
            "-v",
            "error",
            "-select_streams",
            "v:0",
            "-show_entries",
            "stream=height",
            "-of",
            "default=noprint_wrappers=1:nokey=1",
            abs_original,
        ]
        probe_height_res = subprocess.run(
            probe_height_cmd, capture_output=True, text=True, check=True
        )

        try:
            video_height = int(probe_height_res.stdout.strip())
            log.info(f"📏 Višina originalnega videa: {video_height}px")
        except ValueError:
            log.warning(
                "⚠️ Ni mogoče zaznati višine videa. "
                "Privzeto omogočam LD različico."
            )
            video_height = 1080

        # Ali je smiselno ustvariti 720p LD različico?
        needs_ld = video_height > 720

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
            video_transcode_args = ["-c:v", "copy"]

        # ==========================================
        # KORAK 2: FFmpeg Demuxing & Kodiranje (Fragmentiran MP4 izhod)
        # ==========================================
        # 2a. Primarni video (Originalna ločljivost)
        subprocess.run(
            ["ffmpeg", "-y", "-i", abs_original, "-an"]
            + video_transcode_args
            + frag_opts
            + [str(tmp_video_hd)],
            check=True,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )

        # 2b. Sekundarni video (480p LD) - samo če je original večji od 480p
        if needs_ld:
            log.info("📉 Ustvarjam 480p video različico za slabe povezave...")
            ld_transcode_args = [
                "-c:v",
                "libx264",
                "-preset",
                "veryfast",
                "-vf",
                "scale=854:-2",
                "-crf",
                "33",
                "-maxrate",
                "500k",
                "-bufsize",
                "1000k",
            ]
            subprocess.run(
                ["ffmpeg", "-y", "-i", abs_original, "-an"]
                + ld_transcode_args
                + frag_opts
                + [str(tmp_video_ld)],
                check=True,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )

        # 2c. Prvi avdio del
        log.info("🎵 Kopiram prvi zvočni tok...")
        subprocess.run(
            ["ffmpeg", "-y", "-i", abs_original, "-vn", "-c:a", "copy"]
            + frag_opts
            + [str(tmp_audio1)],
            check=True,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )

        # 2d. Drugi avdio del (če obstaja)
        has_second_audio = False
        if second_audio_path:
            abs_second_audio = os.path.abspath(second_audio_path)
            if Path(abs_second_audio).exists():
                log.info("🎵 Kopiram drugi zvočni tok...")
                subprocess.run(
                    [
                        "ffmpeg",
                        "-y",
                        "-i",
                        abs_second_audio,
                        "-vn",
                        "-c:a",
                        "copy",
                    ]
                    + frag_opts
                    + [str(tmp_audio2)],
                    check=True,
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL,
                )
                has_second_audio = True
            else:
                log.warning(
                    f"⚠️ Drugi avdio vir ne obstaja: {second_audio_path}"
                )

        # ==========================================
        # KORAK 3: Shaka Packager pakira v HLS
        # ==========================================
        log.info("📦 Shaka Packager pakira v HLS...")

        shaka_in_video_hd = str(tmp_video_hd).replace(",", "\\,")
        shaka_in_audio1 = str(tmp_audio1).replace(",", "\\,")
        shaka_out_video_hd = str(out_video_hd).replace(",", "\\,")
        shaka_out_audio1 = str(out_audio1).replace(",", "\\,")
        shaka_master_dash = str(master_dash).replace(",", "\\,")
        shaka_master_hls = str(master_hls).replace(",", "\\,")

        # Priprava bazičnega klica
        packager_cmd = ["packager"]

        # Dodamo HD video
        packager_cmd.append(
            f"in={shaka_in_video_hd},stream=video,output={shaka_out_video_hd},format=mp4"
        )

        # Dodamo LD video le, če smo ga ustvarili
        if needs_ld:
            shaka_in_video_ld = str(tmp_video_ld).replace(",", "\\,")
            shaka_out_video_ld = str(out_video_ld).replace(",", "\\,")
            packager_cmd.append(
                f"in={shaka_in_video_ld},stream=video,output={shaka_out_video_ld},format=mp4"
            )

        # Prvi avdio tok
        packager_cmd.append(
            f"in={shaka_in_audio1},stream=audio,output={shaka_out_audio1},format=mp4"
            + ("" if not has_second_audio else ",language=eng")
        )

        # Drugi avdio tok
        if has_second_audio:
            shaka_in_audio2 = str(tmp_audio2).replace(",", "\\,")
            shaka_out_audio2 = str(out_audio2).replace(",", "\\,")
            packager_cmd.append(
                f"in={shaka_in_audio2},stream=audio,output={shaka_out_audio2},format=mp4,language=slo"
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

        subprocess.run(
            packager_cmd, check=True, capture_output=True, text=True
        )

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
        tmp_video_hd.unlink(missing_ok=True)
        tmp_video_ld.unlink(missing_ok=True)
        tmp_audio1.unlink(missing_ok=True)
        if has_second_audio:
            tmp_audio2.unlink(missing_ok=True)

        log.info(f"🎉 Uspešno ustvarjen HLS za film: {original.name}")
        return True

    except subprocess.CalledProcessError as e:
        log.error("❌ Napaka med izvajanjem zunanjega procesa!")
        log.error(f"STDOUT: {e.stdout}")
        log.error(f"STDERR: {e.stderr}")
        tmp_video_hd.unlink(missing_ok=True)
        tmp_video_ld.unlink(missing_ok=True)
        tmp_audio1.unlink(missing_ok=True)
        if has_second_audio:
            tmp_audio2.unlink(missing_ok=True)
        return False
    except Exception as e:
        log.error(f"❌ Splošna napaka: {e}")
        tmp_video_hd.unlink(missing_ok=True)
        tmp_video_ld.unlink(missing_ok=True)
        tmp_audio1.unlink(missing_ok=True)
        if has_second_audio:
            tmp_audio2.unlink(missing_ok=True)
        return False

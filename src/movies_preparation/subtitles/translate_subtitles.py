import logging
import os

import chardet
import gemini_srt_translator as gst
from langdetect import detect

from ..helpers import remove

log = logging.getLogger(__name__)

GEMINI_API_KEY = os.getenv("GEMINI_TOKEN")

gst.gemini_api_key = GEMINI_API_KEY


def translate(
    input_srt_file,
    target_language="sl",
    target_language_short_name="Slo",
    target_language_long_name="Slovenian",
    retry=1,
):
    try:
        # Preverimo kodiranje vhodne datoteke
        with open(input_srt_file, "rb") as file:
            vsebina = file.read()
            rezultat = chardet.detect(vsebina)
            trenutna_kodna_tabela = rezultat["encoding"]

        # Preberemo vsebino v pravilnem kodiranju
        with open(input_srt_file, "r", encoding=trenutna_kodna_tabela) as file:
            tekst = file.read()

        if trenutna_kodna_tabela != "utf-8":
            with open(input_srt_file, "w", encoding="utf-8") as file:
                file.write(tekst)

        # Zaznaj jezik podnapisov
        detected_lang = detect(tekst)
        if detected_lang == target_language:
            log.info("✅ Podnapisi so že v ciljnem jeziku.")
            output_srt_file = input_srt_file.replace(
                ".srt", f"-{target_language_short_name}Subs.srt"
            )
            with open(output_srt_file, "w", encoding="utf-8") as file:
                file.write(tekst)
            remove(input_srt_file)
        else:
            log.info(
                f"🌍 Prevajam {input_srt_file} iz {detected_lang} v {target_language} ...\n"
            )
            gst.gemini_api_key = GEMINI_API_KEY
            gst.target_language = target_language_long_name
            gst.input_file = input_srt_file
            output_srt_file = input_srt_file.replace(
                ".srt", f"-{target_language_short_name}Subs-auto.srt"
            )
            gst.output_file = output_srt_file

            gst.translate()
            os.rename(
                input_srt_file,
                input_srt_file.replace(".srt", f"-{detected_lang}Subs.srt"),
            )
            log.info(f"✅ Prevod zaključen: {output_srt_file}")

        return {
            "input_language": detected_lang,
            "input_file": input_srt_file,
            "output_language": target_language,
            "output_file": output_srt_file,
        }

    except Exception as e:
        if retry:
            os.chmod(input_srt_file, 0o777)
            return translate(
                input_srt_file,
                target_language,
                target_language_short_name,
                target_language_long_name,
                retry=0,
            )
        log.error(f"❌ Napaka pri prevajanju {input_srt_file}: {e}")
        return None

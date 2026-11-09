import re


def webvtt_to_srt(content):
    content = re.sub(r"^WEBVTT\s*\n*", "", content)
    content = re.sub(r"(\d{2}:\d{2}:\d{2})\.(\d{3})", r"\1,\2", content)
    return content.strip() + "\n"

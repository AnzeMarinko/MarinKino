"""Convert local subtitle files without modifying their source encoding."""

import logging
import os
import tempfile
from pathlib import Path

import chardet

log = logging.getLogger(__name__)


def read_subtitle(path):
    path = Path(path)
    data = path.read_bytes()
    try:
        return data.decode("utf-8-sig")
    except UnicodeDecodeError:
        encoding = chardet.detect(data)["encoding"]
        if not encoding:
            raise ValueError(f"Kodiranja podnapisa {path} ni mogoče zaznati.")
        try:
            content = data.decode(encoding)
        except (LookupError, UnicodeDecodeError) as error:
            raise ValueError(
                f"Podnapisa {path} ni mogoče prebrati s kodiranjem {encoding}."
            ) from error
        log.info("Podnapis %s uporablja kodiranje %s.", path.name, encoding)
        return content


def convert_srt_to_vtt(srt_path):
    source = Path(srt_path)
    target = source.with_suffix(".vtt")
    content = read_subtitle(source)
    lines = content.replace("\r\n", "\n").replace("\r", "\n").splitlines(
        keepends=True
    )
    converted = "WEBVTT\n\n" + "".join(
        line.replace(",", ".") if "-->" in line else line for line in lines
    )
    if target.exists():
        existing = target.read_bytes()
        complete = converted.encode("utf-8")
        # Older failed conversions could leave a valid-looking partial file.
        if existing == complete or not complete.startswith(existing):
            return str(target)

    descriptor, temporary = tempfile.mkstemp(
        prefix=f".{target.name}.", suffix=".tmp", dir=target.parent
    )
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8", newline="") as file:
            os.fchmod(
                file.fileno(),
                target.stat().st_mode & 0o777 if target.exists() else 0o644,
            )
            file.write(converted)
        os.replace(temporary, target)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)
    return str(target)

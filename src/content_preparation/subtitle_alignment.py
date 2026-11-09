"""Publish aligned subtitles without overwriting existing files."""

import os
import shutil
import tempfile
from pathlib import Path

from .media_tools import archive_original
from .subtitle_encoding import convert_srt_to_vtt
from .subtitle_inventory import aligned_subtitle_path


def alignment_backup(path):
    path = Path(path)
    return path.with_name("." + path.name + ".original")


def finalize_alignment(path, aligned_path=None, backup_original=True):
    """Publish SRT, matching VTT and backup before removing pending files."""
    source = Path(path)
    target = aligned_subtitle_path(source)
    target_vtt = target.with_suffix(".vtt")
    target_backup = alignment_backup(target)
    old_backup = alignment_backup(source)
    old_vtt = source.with_suffix(".vtt")

    if source == target:
        raise ValueError(f"Podnapis {source.name} nima oznake za poravnavo.")
    outputs = [target, target_vtt]
    if backup_original or old_backup.exists():
        outputs.append(target_backup)
    for output in outputs:
        if os.path.lexists(output):
            raise FileExistsError(f"Ciljna datoteka že obstaja: {output}")

    with tempfile.TemporaryDirectory(
        prefix=".subtitle-aligned-", dir=source.parent
    ) as directory:
        staged = Path(directory) / "aligned.srt"
        shutil.copyfile(aligned_path or source, staged)
        staged.chmod(source.stat().st_mode & 0o777)
        staged_vtt = Path(convert_srt_to_vtt(staged))
        staged_vtt.chmod(source.stat().st_mode & 0o777)
        staged_backup = Path(directory) / "original.srt"
        if backup_original or old_backup.exists():
            shutil.copyfile(
                old_backup if old_backup.exists() else source, staged_backup
            )
            staged_backup.chmod(source.stat().st_mode & 0o777)

        published = []
        staged_outputs = [(staged, target), (staged_vtt, target_vtt)]
        if staged_backup.exists():
            staged_outputs.append((staged_backup, target_backup))
        try:
            for item, output in staged_outputs:
                os.link(item, output)
                published.append(output)
            if old_vtt.exists():
                archive_original(old_vtt)
        except OSError:
            for output in published:
                output.unlink()
            raise

    source.unlink()
    if old_backup.exists():
        old_backup.unlink()
    return target

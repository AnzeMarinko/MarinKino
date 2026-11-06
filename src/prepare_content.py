"""Inspect or prepare local media. --dry-run never imports media services."""

import argparse
import logging
import os
import shutil
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
VIDEO_EXTENSIONS = {".avi", ".mp4", ".mkv", ".vob", ".mov", ".webm"}


def parser():
    command = argparse.ArgumentParser(
        description="Priprava filmov, glasbe in otroškega radia.",
        epilog="Brez možnosti: obstoječi interaktivni postopek.",
    )
    command.add_argument(
        "--kind",
        choices=("all", "movies", "music", "radio"),
        default="all",
        help="Vrsta vsebin (privzeto: all).",
    )
    command.add_argument(
        "--folder",
        type=Path,
        help="Obdelaj samo to mapo znotraj izbrane vrste vsebin.",
    )
    command.add_argument(
        "--dry-run",
        action="store_true",
        help="Prikaži datoteke, prostor in orodja; brez sprememb ali omrežja.",
    )
    command.add_argument(
        "--check", action="store_true", help="Samo preveri potrebna orodja."
    )
    command.add_argument(
        "--threads",
        type=int,
        default=2,
        choices=range(1, 33),
        metavar="1–32",
        help="Največ niti FFmpeg za kodiranje/dekodiranje (privzeto: 2).",
    )
    command.add_argument(
        "--analyze",
        action="store_true",
        help="Vključi počasnejšo analizo glasbe in semantike pri novih HLS.",
    )
    return command


def selected_roots(args):
    roots = {
        "movies": REPO_ROOT / "data/movies/0x-neurejeni-filmi",
        "music": REPO_ROOT / "data/music",
        "radio": REPO_ROOT / "data/radio-stories",
    }
    if args.folder:
        if args.kind == "all":
            raise ValueError(
                "Ob --folder izberi --kind movies, music ali radio."
            )
        folder = args.folder.resolve()
        if not folder.is_dir():
            raise ValueError(f"Mapa ne obstaja: {folder}")
        if not folder.is_relative_to(roots[args.kind].resolve()):
            raise ValueError(f"Mapa mora biti znotraj {roots[args.kind]}.")
        return {args.kind: folder}
    return roots if args.kind == "all" else {args.kind: roots[args.kind]}


def inspect_plan(roots):
    print("Načrt priprave (izvorne datoteke se ohranijo):")
    for kind, folder in roots.items():
        extensions = VIDEO_EXTENSIONS if kind == "movies" else {".mp3"}
        files = sorted(
            path
            for path in folder.rglob("*")
            if path.is_file()
            and not path.is_symlink()
            and path.suffix.lower() in extensions
            and not any(
                part.startswith(".") for part in path.relative_to(folder).parts
            )
        )
        size = sum(path.stat().st_size for path in files)
        print(
            f"\n{kind}: {folder} — {len(files)} datotek, "
            f"{size / 2**30:.2f} GiB"
        )
        for path in files:
            print(f"  {path.relative_to(folder)}")
        disk_path = folder
        while not disk_path.exists():
            disk_path = disk_path.parent
        free = shutil.disk_usage(disk_path).free / 2**30
        print(
            f"  Prosto: {free:.1f} GiB; pretvorba potrebuje dodaten prostor."
        )
        if not folder.exists():
            print("  Mapa še ne obstaja; ni vsebine za pripravo.")


def check_tools(roots):
    required = ["ffmpeg", "ffprobe"]
    if "movies" in roots:
        required.append("packager")
    missing = []
    for name in required:
        executable = shutil.which(name)
        print(f"{name}: {executable or 'MANJKA'}")
        if executable is None:
            missing.append(name)
    return missing


def main(argv=None):
    command = parser()
    args = command.parse_args(argv)
    try:
        roots = selected_roots(args)
    except ValueError as error:
        command.error(str(error))
    if not args.check:
        inspect_plan(roots)
    missing = check_tools(roots)
    if args.dry_run or args.check:
        return 1 if missing and args.check else 0
    if missing:
        print(
            "Namesti manjkajoča orodja pred pripravo. "
            "Navodila: docs/adding_data.md"
        )
        return 1

    os.umask(0o027)
    os.environ["MARINKINO_PREP_THREADS"] = str(args.threads)
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    try:
        if args.kind in ("music", "radio"):
            from content_preparation.audio_preparation import (
                process_audio_folders,
            )

            result = process_audio_folders(
                list(roots.values()), analyze=args.analyze
            )
            return 1 if result["failed"] else 0
        from content_preparation.interactive_pipeline import (
            run_interactive_pipeline,
        )

        result = run_interactive_pipeline(
            REPO_ROOT / "data/movies",
            include_audio=args.kind == "all",
            movie_folders=[args.folder.resolve()] if args.folder else None,
            analyze_audio=args.analyze,
        )
        return 1 if result else 0
    except ImportError as error:
        print(
            f"Manjka pripravljalna odvisnost: {error}. "
            "Uporabi uv sync --extra preparation."
        )
        return 1
    except KeyboardInterrupt:
        print(
            "\nPrekinjeno. Izvori ostanejo ohranjeni; "
            "dokončane HLS se pri ponovitvi preskočijo."
        )
        return 130


if __name__ == "__main__":
    raise SystemExit(main())

"""Build an immutable static release and deterministic precompressed files."""

import argparse
import gzip
import hashlib
import shutil
from pathlib import Path

COMPRESSIBLE = {".css", ".js", ".svg", ".txt", ".webmanifest"}


def package_static(directory: Path, manifest: Path) -> str:
    files = sorted(
        path
        for path in directory.rglob("*")
        if path.is_file()
        and path.relative_to(directory).parts[0] != "v"
        and path.suffix != ".gz"
    )
    digest = hashlib.sha256()
    for path in files:
        if path.is_symlink():
            raise ValueError(
                f"Static release cannot contain symlinks: {path.name}"
            )
        relative = path.relative_to(directory).as_posix()
        digest.update(relative.encode() + b"\0")
        digest.update(hashlib.sha256(path.read_bytes()).digest())
    version = digest.hexdigest()
    release = directory / "v" / version
    for source in files:
        destination = release / source.relative_to(directory)
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(source, destination)
        if source.suffix in COMPRESSIBLE:
            compressed = gzip.compress(
                source.read_bytes(), compresslevel=9, mtime=0
            )
            if len(compressed) < source.stat().st_size:
                source.with_name(source.name + ".gz").write_bytes(compressed)
                destination.with_name(destination.name + ".gz").write_bytes(
                    compressed
                )
    manifest.write_text(version + "\n", encoding="ascii")
    return version


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("directory", type=Path)
    parser.add_argument("manifest", type=Path)
    args = parser.parse_args()
    print(package_static(args.directory, args.manifest))

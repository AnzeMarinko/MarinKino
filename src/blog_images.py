"""Decode blog uploads and encode browser-compatible, oriented images."""

import argparse
import hashlib
import json
import math
import os
import re
import tempfile
import warnings
from dataclasses import dataclass
from functools import lru_cache
from io import BytesIO
from pathlib import Path
from uuid import uuid4

from PIL import Image, ImageCms, ImageOps, UnidentifiedImageError
from pillow_heif import register_heif_opener
from werkzeug.utils import secure_filename

register_heif_opener(thumbnails=False)

MAX_UPLOAD_BYTES = 30 * 1024 * 1024
MAX_GALLERY_REQUEST_BYTES = 40 * 1024 * 1024
MAX_IMAGE_PIXELS = 50_000_000
FORMATS = ("JPEG", "PNG", "WEBP", "GIF", "BMP", "TIFF", "HEIF", "AVIF")
IMAGE_DIRECTORY = Path(__file__).resolve().parent.parent / "data/blog_images"
RESPONSIVE_WIDTHS = (480, 960, 1600)
RESPONSIVE_VERSION = 1


class ImageUploadError(ValueError):
    """Upload or crop error that can be displayed without losing the draft."""


@dataclass
class BlogImage:
    data: bytes
    extension: str
    mimetype: str


def crop_image(image, crop):
    try:
        x, y, width, height = [
            float(crop[key]) for key in ("x", "y", "w", "h")
        ]
        if not all(math.isfinite(value) for value in (x, y, width, height)):
            raise ValueError
        if (
            not 0 <= x < 1
            or not 0 <= y < 1
            or not 0 < width <= 1
            or not 0 < height <= 1
            or x + width > 1.00001
            or y + height > 1.00001
        ):
            raise ValueError
    except (KeyError, TypeError, ValueError):
        raise ImageUploadError(
            "Izrez slike ni veljaven. Ponovno izberi izrez."
        ) from None
    image_width, image_height = image.size
    left = min(image_width - 1, round(x * image_width))
    top = min(image_height - 1, round(y * image_height))
    right = min(image_width, max(left + 1, round((x + width) * image_width)))
    bottom = min(
        image_height, max(top + 1, round((y + height) * image_height))
    )
    return image.crop((left, top, right, bottom))


def prepare_image(file, crop=None, preview=False):
    if not file or not file.filename:
        raise ImageUploadError("Izberi slikovno datoteko.")
    file.stream.seek(0)
    data = file.stream.read(MAX_UPLOAD_BYTES + 1)
    if len(data) > MAX_UPLOAD_BYTES:
        raise ImageUploadError(
            "Slika je prevelika. Največja velikost je 30 MB."
        )
    try:
        with warnings.catch_warnings():
            warnings.simplefilter("error", Image.DecompressionBombWarning)
            with Image.open(BytesIO(data), formats=FORMATS) as source:
                if source.width * source.height > MAX_IMAGE_PIXELS:
                    raise ImageUploadError(
                        "Slika je prevelika. Največ 50 milijonov pik."
                    )
                source_format = source.format
                source.load()
                image = ImageOps.exif_transpose(source)
                has_alpha = (
                    "A" in image.getbands() or "transparency" in image.info
                )
                mode = "RGBA" if has_alpha else "RGB"
                profile = image.info.get("icc_profile")
                if profile:
                    try:
                        target_profile = ImageCms.ImageCmsProfile(
                            ImageCms.createProfile("sRGB")
                        )
                        image = ImageCms.profileToProfile(
                            image
                            if image.mode
                            in ("RGB", "RGBA", "CMYK", "LAB", "L", "LA")
                            else image.convert(mode),
                            ImageCms.ImageCmsProfile(BytesIO(profile)),
                            target_profile,
                            outputMode=mode,
                        )
                        profile = target_profile.tobytes()
                    except (ImageCms.PyCMSError, OSError, ValueError):
                        image = image.convert(mode)
                        profile = None
                else:
                    image = image.convert(mode)
                # Keep the colour profile, without copying camera/GPS metadata.
                image.info.clear()
                if crop is not None:
                    image = crop_image(image, crop)
                if preview:
                    image.thumbnail((2048, 2048), Image.Resampling.LANCZOS)
                output = BytesIO()
                options = {"icc_profile": profile} if profile else {}
                if has_alpha or source_format in ("PNG", "GIF", "BMP"):
                    image.save(output, format="PNG", optimize=True, **options)
                    return BlogImage(output.getvalue(), "png", "image/png")
                image.save(
                    output,
                    format="JPEG",
                    quality=90,
                    optimize=True,
                    progressive=True,
                    **options,
                )
                return BlogImage(output.getvalue(), "jpg", "image/jpeg")
    except ImageUploadError:
        raise
    except (Image.DecompressionBombError, Image.DecompressionBombWarning):
        raise ImageUploadError("Slika ima preveliko ločljivost.") from None
    except (
        UnidentifiedImageError,
        OSError,
        ValueError,
        SyntaxError,
        EOFError,
    ):
        raise ImageUploadError(
            "Slike ni mogoče prebrati. Podprti so HEIC/HEIF, JPEG, PNG, "
            "WebP, AVIF, TIFF, BMP in GIF. Izberi veljavno slikovno datoteko."
        ) from None


def save_image(file, directory, crop=None):
    result = prepare_image(file, crop=crop)
    stem = Path(secure_filename(file.filename)).stem[:80] or "blog-image"
    filename = f"{stem}-{uuid4().hex}.{result.extension}"
    directory = Path(directory)
    directory.mkdir(parents=True, exist_ok=True)
    directory.chmod(0o755)
    with (directory / filename).open("xb") as output:
        output.write(result.data)
    (directory / filename).chmod(0o644)
    try:
        prepare_responsive_images(directory / filename)
    except Exception:
        # An upload is published only after its display assets are ready.
        remove_image_files(directory / filename)
        raise
    return filename


def _manifest_path(path):
    return path.with_name(f".{path.name}.responsive.json")


def _source_revision(path):
    stat = path.stat()
    return [stat.st_mtime_ns, stat.st_size, RESPONSIVE_VERSION]


@lru_cache(maxsize=512)
def _read_sources(path, revision, manifest_mtime):
    try:
        record = json.loads(_manifest_path(path).read_text())
    except (FileNotFoundError, ValueError):
        return None
    if record.get("revision") != list(revision):
        return None
    return record


def image_sources(filename, directory=None):
    """Read prepared display assets; never resize images during a page view."""
    fallback = {"src": filename, "srcset": []}
    if not filename or Path(filename).name != filename:
        return fallback
    path = Path(directory or IMAGE_DIRECTORY) / filename
    try:
        revision = _source_revision(path)
        manifest_stat = _manifest_path(path).stat()
    except FileNotFoundError:
        return fallback
    # Include manifest mtime so a background preparation becomes visible.
    record = _read_sources(path, tuple(revision), manifest_stat.st_mtime_ns)
    return record or fallback


def prepare_responsive_images(path):
    """Create immutable WebP display sizes, retaining the existing original."""
    path = Path(path)
    revision = _source_revision(path)
    try:
        previous = json.loads(_manifest_path(path).read_text())
    except (FileNotFoundError, ValueError):
        previous = {}
    if (
        previous.get("revision") == revision
        and all(
            (path.parent / item["filename"]).is_file()
            for item in previous.get("srcset", [])
        )
        and previous.get("srcset")
    ):
        return previous
    with path.open("rb") as stream:
        digest = hashlib.file_digest(stream, "sha256").hexdigest()[:16]
    created = []
    try:
        with Image.open(path, formats=FORMATS) as source:
            if source.width * source.height > MAX_IMAGE_PIXELS:
                raise ImageUploadError("Slika ima preveliko ločljivost.")
            # JPEG can decode at a reduced resolution before allocating pixels.
            source.draft("RGB", (1600, 1600))
            image = ImageOps.exif_transpose(source)
            mode = (
                "RGBA"
                if "A" in image.getbands() or "transparency" in image.info
                else "RGB"
            )
            image = image.convert(mode)
            image.thumbnail((1600, 1600), Image.Resampling.LANCZOS)
            profile = image.info.get("icc_profile")
            options = {"icc_profile": profile} if profile else {}
            width, height = image.size
            variants = []
            widths = sorted({min(size, width) for size in RESPONSIVE_WIDTHS})
            for size in widths:
                name = (
                    f"{path.stem}-responsive-v{RESPONSIVE_VERSION}-"
                    f"{digest}-{size}w.webp"
                )
                destination = path.parent / name
                already_exists = destination.exists()
                display = image.resize(
                    (size, max(1, round(height * size / width))),
                    Image.Resampling.LANCZOS,
                )
                descriptor, temporary = tempfile.mkstemp(dir=path.parent)
                try:
                    with os.fdopen(descriptor, "wb") as output:
                        display.save(
                            output,
                            format="WEBP",
                            quality=82,
                            method=4,
                            **options,
                        )
                        os.fchmod(output.fileno(), 0o644)
                    os.replace(temporary, destination)
                finally:
                    Path(temporary).unlink(missing_ok=True)
                if not already_exists:
                    created.append(destination)
                variants.append({"filename": name, "width": size})
            default = min(variants, key=lambda item: abs(item["width"] - 960))
            record = {
                "revision": revision,
                "src": default["filename"],
                "srcset": variants,
                "width": width,
                "height": height,
            }
            descriptor, temporary = tempfile.mkstemp(dir=path.parent)
            try:
                with os.fdopen(descriptor, "w") as output:
                    json.dump(record, output)
                os.replace(temporary, _manifest_path(path))
            finally:
                Path(temporary).unlink(missing_ok=True)
            _read_sources.cache_clear()
            return record
    except Exception:
        for item in created:
            item.unlink(missing_ok=True)
        raise


def remove_image_files(path):
    """Roll back assets for a new upload that was never published."""
    path = Path(path)
    for derivative in path.parent.glob(f"{path.stem}-responsive-v*.*"):
        derivative.unlink(missing_ok=True)
    _manifest_path(path).unlink(missing_ok=True)
    path.unlink(missing_ok=True)


def post_gallery(post):
    """Read the gallery, with compatibility for existing single-image posts."""
    if not post:
        return []
    if isinstance(post.get("images"), list):
        return [
            {
                "filename": item["filename"],
                "description": item.get("description") or "",
                **(
                    {"thumbnail": item["thumbnail"]}
                    if isinstance(item.get("thumbnail"), str)
                    else {}
                ),
            }
            for item in post["images"]
            if isinstance(item, dict)
            and isinstance(item.get("filename"), str)
            and item["filename"]
        ]
    if post.get("image"):
        return [
            {
                "filename": post["image"],
                "description": post.get("image_desc") or "",
            }
        ]
    return []


def save_gallery(form, files, directory, post=None):
    """Validate gallery entries and retain images owned by this post."""
    existing = post_gallery(post)
    manifest_text = form.get("gallery_manifest")
    if manifest_text is None:
        if form.get("remove_image") == "1":
            return [], {}
        incoming = [
            file for file in files.getlist("image_file") if file.filename
        ]
        if not incoming:
            if existing:
                existing[0]["description"] = form.get("image_desc") or ""
            elif form.get("image"):
                existing = [
                    {
                        "filename": form["image"],
                        "description": form.get("image_desc") or "",
                    }
                ]
            return existing, {}
        crop = {key: form.get(f"crop_{key}") for key in ("x", "y", "w", "h")}
        manifest = []
        for index, _file in enumerate(incoming):
            item = {
                "upload_id": f"legacy-{index}",
                "description": form.get("image_desc") or "",
            }
            if index == 0 and all(
                value not in (None, "") for value in crop.values()
            ):
                item["crop"] = crop
            manifest.append(item)
        upload_files = {
            f"legacy-{index}": file for index, file in enumerate(incoming)
        }
        # A single upload from an older client replaces its cover image.
        manifest.extend(existing[1:] if len(incoming) == 1 else existing)
    else:
        try:
            manifest = json.loads(manifest_text)
        except (TypeError, ValueError):
            raise ImageUploadError("Seznam slik ni veljaven.") from None
        upload_files = {}
    if not isinstance(manifest, list) or len(manifest) > 20:
        raise ImageUploadError("Galerija lahko vsebuje največ 20 slik.")
    known = {item["filename"]: item for item in existing}
    seen = set()
    saved = []
    mapping = {}
    created = []
    try:
        for index, item in enumerate(manifest):
            if not isinstance(item, dict):
                raise ImageUploadError("Seznam slik ni veljaven.")
            description = item.get("description") or ""
            if not isinstance(description, str) or len(description) > 2000:
                raise ImageUploadError("Opis slike: največ 2000 znakov.")
            upload_id = item.get("upload_id")
            if upload_id is not None:
                if (
                    not isinstance(upload_id, str)
                    or not upload_id
                    or len(upload_id) > 80
                ):
                    raise ImageUploadError("Oznaka nove slike ni veljavna.")
                if upload_id in seen:
                    raise ImageUploadError(
                        "Nova slika je na seznamu podvojena."
                    )
                seen.add(upload_id)
                file = upload_files.get(upload_id) or files.get(
                    f"gallery_file_{upload_id}"
                )
                crop = item.get("crop")
                if not file or (index == 0 and not isinstance(crop, dict)):
                    raise ImageUploadError(
                        "Naslovna slika potrebuje datoteko in izrez."
                    )
                filename = save_image(
                    file, directory, crop=crop if index == 0 else None
                )
                created.append(Path(directory) / filename)
                thumbnail = (
                    f"{Path(filename).stem}-thumb{Path(filename).suffix}"
                )
                thumbnail_path = Path(directory) / thumbnail
                created.append(thumbnail_path)
                with Image.open(Path(directory) / filename) as source:
                    source.thumbnail((240, 200), Image.Resampling.LANCZOS)
                    options = (
                        {"icc_profile": source.info["icc_profile"]}
                        if source.info.get("icc_profile")
                        else {}
                    )
                    if source.format == "JPEG":
                        options.update(quality=85, optimize=True)
                    with thumbnail_path.open("xb") as output:
                        source.save(output, format=source.format, **options)
                    thumbnail_path.chmod(0o644)
                mapping[upload_id] = filename
            else:
                filename = item.get("filename")
                if (
                    not isinstance(filename, str)
                    or filename not in known
                    or filename in seen
                ):
                    raise ImageUploadError(
                        "Slika ne pripada tej objavi ali je podvojena."
                    )
                seen.add(filename)
                thumbnail = known[filename].get("thumbnail")
            saved.append(
                {
                    "filename": filename,
                    "description": description.strip(),
                    **({"thumbnail": thumbnail} if thumbnail else {}),
                }
            )
    except Exception:
        # Undo only files created by this upload; retain existing assets.
        for path in created:
            remove_image_files(path)
        raise
    return saved, mapping


def prepare_existing_images(posts_path, directory):
    """Serial preparation for existing referenced images during deployment."""
    posts_path, directory = Path(posts_path), Path(directory)
    if not posts_path.exists():
        return 0
    posts = json.loads(posts_path.read_text())
    filenames = set()
    for post in posts.values():
        filenames.update(item["filename"] for item in post_gallery(post))
        filenames.update(
            re.findall(r"/blog/image/([^\s)\"'<>]+)", post.get("content", ""))
        )
    prepared = 0
    for name in sorted(filenames):
        if Path(name).name != name:
            continue
        path = directory / name
        # A missing legacy attachment must not prevent deployment.
        if path.is_symlink() or not path.is_file():
            continue
        prepare_responsive_images(path)
        prepared += 1
    return prepared


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="Prepare responsive blog images"
    )
    parser.add_argument(
        "--prepare-existing", action="store_true", required=True
    )
    parser.add_argument("--directory", type=Path, default=IMAGE_DIRECTORY)
    parser.add_argument(
        "--posts",
        type=Path,
        default=IMAGE_DIRECTORY.parent / "blog_posts.json",
    )
    arguments = parser.parse_args()
    count = prepare_existing_images(arguments.posts, arguments.directory)
    print(f"Prepared {count} blog images")

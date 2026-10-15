"""Decode blog uploads and encode browser-compatible, oriented images."""

import json
import math
import warnings
from dataclasses import dataclass
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
    with (directory / filename).open("xb") as output:
        output.write(result.data)
    return filename


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
                if not file or (
                    index == 0 and not isinstance(crop, dict)
                ):
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
            path.unlink(missing_ok=True)
        raise
    return saved, mapping

"""Responsive assets preserve originals and stay outside page rendering."""

import json
import sys
from io import BytesIO
from pathlib import Path

import pytest
from PIL import Image
from werkzeug.datastructures import FileStorage

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

import blog_images  # noqa: E402


def save_picture(path, size=(2000, 1500), color="green"):
    Image.new("RGB", size, color).save(path, format="JPEG")


def test_existing_image_preparation_preserves_original_and_is_repeatable(
    tmp_path,
):
    original = tmp_path / "cover.jpg"
    save_picture(original)
    before = original.read_bytes()
    sources = blog_images.prepare_responsive_images(original)

    assert original.read_bytes() == before
    assert [item["width"] for item in sources["srcset"]] == [480, 960, 1600]
    for item in sources["srcset"]:
        path = tmp_path / item["filename"]
        with Image.open(path) as image:
            assert image.format == "WEBP"
            assert image.size == (item["width"], item["width"] * 3 // 4)
        assert path.stat().st_mode & 0o777 == 0o644
    mtimes = {
        path.name: path.stat().st_mtime_ns for path in tmp_path.iterdir()
    }
    assert blog_images.prepare_responsive_images(original) == sources
    assert mtimes == {
        path.name: path.stat().st_mtime_ns for path in tmp_path.iterdir()
    }


def test_page_lookup_never_decodes_and_changes_become_visible(
    tmp_path, monkeypatch
):
    original = tmp_path / "cover.jpg"
    save_picture(original)
    assert blog_images.image_sources(original.name, tmp_path) == {
        "src": original.name,
        "srcset": [],
    }
    sources = blog_images.prepare_responsive_images(original)
    save_picture(original, color="blue")
    assert (
        blog_images.image_sources(original.name, tmp_path)["src"]
        == original.name
    )
    changed = blog_images.prepare_responsive_images(original)
    assert changed["src"] != sources["src"]
    monkeypatch.setattr(
        blog_images.Image,
        "open",
        lambda *_a, **_k: pytest.fail("HTTP lookup decoded image"),
    )
    assert blog_images.image_sources(original.name, tmp_path) == changed


def test_uploaded_image_has_ready_derivatives_without_upscaling(tmp_path):
    buffer = BytesIO()
    Image.new("RGBA", (320, 200), (100, 80, 20, 64)).save(buffer, format="PNG")
    buffer.seek(0)
    filename = blog_images.save_image(
        FileStorage(stream=buffer, filename="transparent.png"), tmp_path
    )
    sources = blog_images.image_sources(filename, tmp_path)
    assert [item["width"] for item in sources["srcset"]] == [320]
    with Image.open(tmp_path / sources["src"]) as image:
        assert image.mode == "RGBA"
        assert image.getpixel((0, 0))[3] == 64


def test_preparation_failure_rolls_back_only_new_upload(tmp_path, monkeypatch):
    old = tmp_path / "old.jpg"
    save_picture(old)
    old_bytes = old.read_bytes()

    def fail(_path):
        raise OSError("test full disk")

    monkeypatch.setattr(blog_images, "prepare_responsive_images", fail)
    with pytest.raises(OSError, match="full disk"):
        blog_images.save_image(
            FileStorage(stream=BytesIO(old_bytes), filename="new.jpg"),
            tmp_path,
        )
    assert list(tmp_path.iterdir()) == [old]
    assert old.read_bytes() == old_bytes


def test_existing_preparation_uses_referenced_images_and_skips_missing(
    tmp_path,
):
    directory = tmp_path / "images"
    directory.mkdir()
    save_picture(directory / "cover.jpg")
    save_picture(directory / "unused.jpg")
    posts = tmp_path / "posts.json"
    posts.write_text(
        json.dumps(
            {"public": {"image": "cover.jpg"}, "old": {"image": "missing.jpg"}}
        )
    )

    assert blog_images.prepare_existing_images(posts, directory) == 1
    assert blog_images.image_sources("cover.jpg", directory)["srcset"]
    assert not blog_images.image_sources("unused.jpg", directory)["srcset"]

"""Real image decoding, crop persistence and editor conversion workflows."""

import importlib.util
import json
import sys
from io import BytesIO
from pathlib import Path
from types import ModuleType, SimpleNamespace
from unittest.mock import Mock, patch

import pytest
from flask import Flask, send_from_directory, session
from flask_login import LoginManager, UserMixin
from flask_wtf.csrf import CSRFProtect
from PIL import Image, ImageCms
from werkzeug.datastructures import FileStorage

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from test_admin_memes_ui import browser as browser_fixture  # noqa: E402
from test_admin_memes_ui import fill_markdown

import blog_images  # noqa: E402

browser = browser_fixture


def picture(image_format="HEIF", mode="RGB", size=(120, 100), **options):
    color = (30, 100, 180, 100) if mode == "RGBA" else (30, 100, 180)
    image = Image.new(mode, size, color)
    output = BytesIO()
    image.save(output, format=image_format, **options)
    return output.getvalue()


def upload(data=None, filename="IMG_1234.heic"):
    return FileStorage(
        stream=BytesIO(picture() if data is None else data), filename=filename
    )


@pytest.fixture
def ui(tmp_path):
    utilities = ModuleType("utils")
    utilities.is_current_admin_view = lambda user: (
        user.is_authenticated
        and user.is_admin
        and session.get("view_as") not in ("user", "anonymous")
    )
    utilities.load_blog_subscribers = Mock(return_value=[])
    utilities.redis_client = Mock()
    utilities.send_mail = Mock()
    blog_module = ModuleType("blueprints.blog_bp")
    blog_module.public_base_url = lambda: "https://blog.example.test"
    config = ModuleType("content_preparation.config")
    config.LOG_FILENAME = str(tmp_path / "unused.log")
    spec = importlib.util.spec_from_file_location(
        "blog_image_test_admin", ROOT / "src/blueprints/admin_bp.py"
    )
    module = importlib.util.module_from_spec(spec)
    with patch.dict(
        sys.modules,
        {
            "utils": utilities,
            "blueprints.blog_bp": blog_module,
            "content_preparation.config": config,
            "pandas": ModuleType("pandas"),
        },
    ):
        spec.loader.exec_module(module)
    module.BLOG_DATA_FILE = str(tmp_path / "posts.json")
    module.BLOG_IMAGES_DIR = str(tmp_path / "images")
    app = Flask(
        __name__,
        template_folder=str(ROOT / "src/templates"),
        static_folder=str(ROOT / "src/static"),
    )
    app.config.update(
        TESTING=True,
        SECRET_KEY="image-tests",
        ADMIN=True,
        AUTHENTICATED=True,
        WTF_CSRF_ENABLED=False,
    )

    class User(UserMixin):
        id = "image-admin"

        @property
        def is_admin(self):
            return app.config["ADMIN"]

    manager = LoginManager(app)
    manager.user_loader(lambda _id: User())

    @app.before_request
    def authenticate():
        if app.config["AUTHENTICATED"]:
            session["_user_id"] = User.id
        else:
            session.pop("_user_id", None)

    CSRFProtect(app)
    app.jinja_env.globals.update(domain="localhost", current_year=2026)
    app.add_url_rule("/", "home", lambda: "home")
    app.add_url_rule("/blog/terms", "blog.blog_terms", lambda: "")
    app.add_url_rule("/blog/privacy", "blog.blog_privacy", lambda: "")
    app.add_url_rule(
        "/blog/image/<file_name>",
        "blog.blog_image_file",
        lambda file_name: send_from_directory(
            module.BLOG_IMAGES_DIR, file_name
        ),
    )
    app.register_blueprint(module.admin_bp)
    return SimpleNamespace(
        app=app,
        client=app.test_client(),
        module=module,
        images=Path(module.BLOG_IMAGES_DIR),
    )


@pytest.mark.parametrize(
    "image_format,extension",
    [
        ("HEIF", "jpg"),
        ("JPEG", "jpg"),
        ("WEBP", "jpg"),
        ("AVIF", "jpg"),
        ("TIFF", "jpg"),
        ("BMP", "png"),
        ("PNG", "png"),
        ("GIF", "png"),
    ],
)
def test_real_formats_are_encoded_as_browser_images(image_format, extension):
    result = blog_images.prepare_image(upload(picture(image_format)))
    assert result.extension == extension
    with Image.open(BytesIO(result.data)) as saved:
        assert saved.size == (120, 100)
        assert saved.format == ("PNG" if extension == "png" else "JPEG")


def test_alpha_survives_conversion_to_png():
    result = blog_images.prepare_image(
        upload(picture("WEBP", mode="RGBA"), "transparent.webp")
    )
    assert result.extension == "png"
    with Image.open(BytesIO(result.data)) as saved:
        assert saved.mode == "RGBA"
        assert saved.getpixel((10, 10))[3] == 100


def test_orientation_is_applied_before_crop_and_exif_is_removed():
    exif = Image.Exif()
    exif[274] = 6
    exif[270] = "Camera metadata"
    image = upload(picture("JPEG", size=(200, 120), exif=exif), "phone.jpg")
    result = blog_images.prepare_image(
        image,
        crop={
            "x": 0,
            "y": 0,
            "w": 1,
            "h": 0.5,
        },
    )
    with Image.open(BytesIO(result.data)) as saved:
        assert saved.size == (120, 100)
        assert not saved.getexif()


def test_png_metadata_is_removed_and_colour_profile_preserved():
    exif = Image.Exif()
    exif[270] = "Private metadata"
    profile = ImageCms.ImageCmsProfile(ImageCms.createProfile("sRGB"))
    result = blog_images.prepare_image(
        upload(
            picture("PNG", exif=exif, icc_profile=profile.tobytes()),
            "profile.png",
        )
    )
    with Image.open(BytesIO(result.data)) as saved:
        assert not saved.getexif()
        assert saved.info["icc_profile"]
        assert saved.getpixel((10, 10)) == (30, 100, 180)


def test_unique_names_prevent_overwriting_existing_blog_images(tmp_path):
    first = blog_images.save_image(upload(), tmp_path)
    second = blog_images.save_image(upload(), tmp_path)
    assert first != second and first.endswith(".jpg")
    assert (tmp_path / first).exists() and (tmp_path / second).exists()


@pytest.mark.parametrize(
    "crop",
    [
        {"x": float("nan"), "y": 0, "w": 1, "h": 1},
        {"x": -0.1, "y": 0, "w": 1, "h": 1},
        {"x": 0, "y": 0, "w": 0, "h": 1},
        {"x": 0.5, "y": 0, "w": 0.9, "h": 1},
    ],
)
def test_bad_crop_cannot_silently_store_uncropped_original(tmp_path, crop):
    with pytest.raises(blog_images.ImageUploadError):
        blog_images.save_image(upload(), tmp_path, crop=crop)
    assert not list(tmp_path.iterdir())


def test_invalid_and_oversized_uploads_are_rejected(monkeypatch):
    with pytest.raises(blog_images.ImageUploadError):
        blog_images.prepare_image(upload(b"not an image"))
    monkeypatch.setattr(blog_images, "MAX_UPLOAD_BYTES", 10)
    with pytest.raises(blog_images.ImageUploadError, match="30 MB"):
        blog_images.prepare_image(upload(b"01234567890"))


def post_image(ui, path="/admin/blog/new", image=None, **fields):
    return ui.client.post(
        path,
        data={
            "title": "Slika s telefona",
            "content": "Besedilo ostane.",
            "crop_x": "0",
            "crop_y": "0",
            "crop_w": "1",
            "crop_h": "1",
            "image_file": (
                BytesIO(picture() if image is None else image),
                "phone.heic",
            ),
            **fields,
        },
        headers={"X-Requested-With": "XMLHttpRequest"},
    )


def test_legacy_cover_crop_accepts_zero_origin(ui):
    response = post_image(ui, crop_w="0.5", crop_h="0.5")

    assert response.json["success"]
    filename = next(iter(ui.module.load_blog_posts().values()))["image"]
    with Image.open(ui.images / filename) as cover:
        assert cover.size == (60, 50)


def test_new_post_returns_encoded_edit_url_for_unicode_slug(ui):
    response = ui.client.post(
        "/admin/blog/new",
        data={"title": "München", "content": "Besedilo"},
        headers={"X-Requested-With": "XMLHttpRequest"},
    )

    assert response.json["success"]
    assert response.json["edit_url"] == "/admin/blog/edit/m%C3%BCnchen"


def test_blog_save_logs_request_id_and_persistence(caplog, ui):
    caplog.set_level("INFO")
    response = ui.client.post(
        "/admin/blog/new",
        data={"title": "Dnevnik", "content": "Besedilo"},
        headers={
            "X-Requested-With": "XMLHttpRequest",
            "X-Request-ID": "test-save-123",
        },
    )

    assert response.json["success"]
    assert "Blog save received request_id=test-save-123" in caplog.text
    assert "Blog post persisted request_id=test-save-123" in caplog.text
    assert "Blog save response success request_id=test-save-123" in caplog.text


def test_blog_save_returns_json_for_oversized_request(caplog, ui):
    caplog.set_level("WARNING")
    ui.app.config["MAX_CONTENT_LENGTH"] = 128

    response = ui.client.post(
        "/admin/blog/new",
        data={"title": "Prevelika", "content": "x" * 256},
        headers={
            "X-Requested-With": "XMLHttpRequest",
            "X-Request-ID": "large-test-123",
        },
    )

    assert response.status_code == 413
    assert response.json["success"] is False
    assert "40 MB" in response.json["message"]
    assert "request_id=large-test-123 reason=request-too-large" in caplog.text


def test_preview_and_new_and_edit_posts_use_real_heic_conversion(ui):
    response = ui.client.post(
        "/admin/blog/image-preview",
        data={
            "image_file": (BytesIO(picture()), "phone.HEIC"),
        },
    )
    assert response.status_code == 200
    assert response.mimetype == "image/jpeg"
    assert response.headers["Cache-Control"] == "private, no-store"
    assert not ui.images.exists()
    response = post_image(ui)
    assert response.status_code == 200 and response.json["success"]
    post_id = response.json["post_id"]
    assert response.json["edit_url"] == f"/admin/blog/edit/{post_id}"
    post = ui.module.load_blog_posts()[post_id]
    assert post["image"].endswith(".jpg")
    with Image.open(ui.images / post["image"]) as saved:
        assert saved.format == "JPEG" and saved.size == (120, 100)
    response = post_image(
        ui, f"/admin/blog/edit/{post_id}", image=picture("PNG", mode="RGBA")
    )
    assert response.json["success"]
    changed = ui.module.load_blog_posts()[post_id]
    assert changed["image"].endswith(".png")
    assert changed["image"] != post["image"]


def test_failed_conversion_does_not_create_or_replace_post(ui):
    assert post_image(ui, image=b"invalid").status_code == 400
    assert ui.module.load_blog_posts() == {}
    response = post_image(ui)
    post_id = response.json["post_id"]
    before = ui.module.load_blog_posts()
    response = post_image(ui, f"/admin/blog/edit/{post_id}", image=b"invalid")
    assert response.status_code == 400
    assert ui.module.load_blog_posts() == before


def test_preview_access_and_csrf_protection(ui):
    ui.app.config["ADMIN"] = False
    assert ui.client.post("/admin/blog/image-preview").status_code == 403
    ui.app.config["AUTHENTICATED"] = False
    assert ui.client.post("/admin/blog/image-preview").status_code == 401
    ui.app.config.update(ADMIN=True, AUTHENTICATED=True, WTF_CSRF_ENABLED=True)
    assert ui.client.post("/admin/blog/image-preview").status_code == 400


def gallery_post(ui, manifest, uploads=None, path="/admin/blog/new"):
    return ui.client.post(
        path,
        data={
            "title": "Galerija",
            "content": "Besedilo galerije",
            "gallery_manifest": json.dumps(manifest),
            **(uploads or {}),
        },
        headers={"X-Requested-With": "XMLHttpRequest"},
    )


def test_gallery_upload_reorder_remove_and_cover_compatibility(ui):
    manifest = [
        {
            "upload_id": "one",
            "description": "one",
            "crop": {"x": 0, "y": 0, "w": 0.5, "h": 0.5},
        }
    ] + [{"upload_id": "two", "description": "two"}]
    response = gallery_post(
        ui,
        manifest,
        {
            "gallery_file_one": (BytesIO(picture("PNG")), "one.png"),
            "gallery_file_two": (BytesIO(picture("HEIF")), "two.heic"),
        },
    )
    assert response.json["success"]
    post_id = response.json["post_id"]
    images = response.json["images"]
    assert len(images) == 2
    assert response.json["image_uploads"]["one"] == images[0]["filename"]
    assert images[1]["filename"].endswith(".jpg")
    with Image.open(ui.images / images[0]["filename"]) as cover:
        assert cover.size == (60, 50)
    with Image.open(ui.images / images[1]["filename"]) as gallery_image:
        assert gallery_image.size == (120, 100)
    for item in images:
        with Image.open(ui.images / item["thumbnail"]) as thumbnail:
            assert thumbnail.width <= 240 and thumbnail.height <= 200
    post = ui.module.load_blog_posts()[post_id]
    assert post["image"] == images[0]["filename"]
    assert post["image_desc"] == "one"
    response = gallery_post(
        ui, images[::-1], path=f"/admin/blog/edit/{post_id}"
    )
    assert response.json["success"]
    post = ui.module.load_blog_posts()[post_id]
    assert post["image"] == images[1]["filename"]
    assert post["image_desc"] == "two"
    assert gallery_post(
        ui, [images[0]], path=f"/admin/blog/edit/{post_id}"
    ).json["success"]
    assert len(ui.module.load_blog_posts()[post_id]["images"]) == 1
    assert gallery_post(ui, [], path=f"/admin/blog/edit/{post_id}").json[
        "success"
    ]
    assert ui.module.load_blog_posts()[post_id]["image"] is None
    assert len(list(ui.images.iterdir())) == 4


def test_gallery_bad_second_image_rolls_back_new_files_and_keeps_post(ui):
    response = gallery_post(
        ui,
        [
            {"upload_id": key, "crop": {"x": 0, "y": 0, "w": 1, "h": 1}}
            for key in ("valid", "bad")
        ],
        {
            "gallery_file_valid": (BytesIO(picture("PNG")), "valid.png"),
            "gallery_file_bad": (BytesIO(b"invalid"), "bad.heic"),
        },
    )
    assert response.status_code == 400
    assert ui.module.load_blog_posts() == {}
    assert not list(ui.images.iterdir())


def test_gallery_cannot_reference_another_post_or_duplicate_asset(ui):
    response = post_image(ui)
    post_id = response.json["post_id"]
    image = ui.module.load_blog_posts()[post_id]["images"][0]
    assert gallery_post(ui, [image]).status_code == 400
    assert (
        gallery_post(
            ui, [image, image], path=f"/admin/blog/edit/{post_id}"
        ).status_code
        == 400
    )
    assert len(ui.module.load_blog_posts()[post_id]["images"]) == 1


def test_old_single_image_posts_upgrade_without_losing_image(ui):
    ui.module.save_blog_posts(
        {
            "old": {
                "id": "old",
                "title": "Stara objava",
                "content": "Vsebina",
                "image": "old.jpg",
                "image_desc": "Opis",
            }
        }
    )
    response = ui.client.post(
        "/admin/blog/edit/old",
        data={
            "title": "Nov naslov",
            "content": "Vsebina",
            "image_desc": "Nov opis",
        },
        headers={"X-Requested-With": "XMLHttpRequest"},
    )
    assert response.json["success"]
    assert response.json["images"] == [
        {"filename": "old.jpg", "description": "Nov opis"}
    ]


def test_browser_heic_crop_save_and_conversion_failure_preserves_draft(
    ui, browser
):
    page = browser.page
    page.goto(browser.base + "/admin/blog/new")
    page.locator("#title").fill("HEIC iz telefona")
    fill_markdown(page, "Ohranjeno besedilo")
    page.locator("#image_file").set_input_files(
        {
            "name": "IMG_2026.HEIC",
            "mimeType": "application/octet-stream",
            "buffer": picture("HEIF", size=(600, 400)),
        }
    )
    page.wait_for_function(
        "Number(document.querySelector('#crop_w').value) > 0"
    )
    assert "JPEG" in page.locator("#imageUploadStatus").text_content()
    for width in [320, 390, 1440]:
        page.set_viewport_size({"width": width, "height": 900})
        assert page.evaluate(
            "document.documentElement.scrollWidth <= innerWidth + 1"
        )
    page.locator("#crop-size-range").fill("60")
    page.locator("#crop-size-range").dispatch_event("input")
    page.locator('#blogEditorForm button[type="submit"]').click()
    page.get_by_text("Blog objava shranjena.", exact=True).wait_for()
    posts = ui.module.load_blog_posts()
    assert len(posts) == 1
    post = next(iter(posts.values()))
    with Image.open(ui.images / post["image"]) as saved:
        assert saved.format == "JPEG"
        assert saved.width / saved.height == pytest.approx(6 / 5, abs=0.01)
    page.locator("#image_file").set_input_files(
        {
            "name": "broken.heic",
            "mimeType": "image/heic",
            "buffer": b"bad",
        }
    )
    page.wait_for_function(
        "document.querySelector('#imageUploadStatus').dataset.kind === 'error'"
    )
    assert (
        page.locator("#content-editor").input_value() == "Ohranjeno besedilo"
    )
    assert ui.module.load_blog_posts() == posts
    page.locator("#blogGalleryEditor article").last.get_by_role(
        "button", name="Odstrani", exact=True
    ).click()
    page.route(
        "**/admin/blog/image-preview",
        lambda route: route.fulfill(
            status=503,
            content_type="application/json",
            body='{"message":"Testna napaka pretvorbe"}',
        ),
    )
    page.locator("#image_file").set_input_files(
        {
            "name": "transparent.webp",
            "mimeType": "image/webp",
            "buffer": picture("WEBP", mode="RGBA", size=(600, 400)),
        }
    )
    page.locator("#imageUploadStatus").get_by_text(
        "Testna napaka pretvorbe", exact=True
    ).wait_for()
    assert (
        page.locator("#content-editor").input_value() == "Ohranjeno besedilo"
    )
    page.unroute("**/admin/blog/image-preview")
    page.get_by_role("button", name="Poskusi ponovno", exact=True).click()
    # A second gallery image preserves its full frame; only cover has a crop.
    page.wait_for_function(
        "document.querySelector('#imageUploadStatus').textContent.includes('PNG')"
    )
    page.locator('#blogEditorForm button[type="submit"]').click()
    page.get_by_text("Blog objava shranjena.", exact=True).wait_for()
    page.wait_for_function(
        "document.querySelector('#saveStatus').textContent === "
        "'Vse spremembe shranjene.'"
    )
    saved = ui.module.load_blog_posts()[post["id"]]
    assert len(saved["images"]) == 2
    assert saved["images"][1]["filename"].endswith(".png")


def test_browser_multiple_uploads_crop_only_cover_and_reload(ui, browser):
    page = browser.page
    page.goto(browser.base + "/admin/blog/new")
    page.locator("#title").fill("Moja galerija")
    fill_markdown(page, "Galerija z dvema slikama")
    page.locator("#image_file").set_input_files(
        [
            {
                "name": "first.png",
                "mimeType": "image/png",
                "buffer": picture("PNG", size=(600, 500)),
            },
            {
                "name": "second.heic",
                "mimeType": "image/heic",
                "buffer": picture("HEIF", size=(600, 400)),
            },
        ]
    )
    page.wait_for_function(
        "document.querySelectorAll('#blogGalleryEditor img').length === 2 && "
        "Array.from(document.querySelectorAll('#blogGalleryEditor small'))"
        ".every(node=>!node.textContent.includes('Pripravljam'))"
    )
    page.locator("#blogGalleryEditor [data-caption-key]").nth(0).fill(
        "Prva fotografija"
    )
    page.locator("#blogGalleryEditor [data-caption-key]").nth(1).fill(
        "Druga fotografija"
    )
    page.locator("#crop-size-range").fill("40")
    page.locator("#crop-size-range").dispatch_event("input")
    page.locator("#blogGalleryEditor .blog-gallery-select").nth(1).click()
    assert (
        page.locator("#image-crop-container")
        .get_attribute("class")
        .find("d-none")
        >= 0
    )
    assert page.locator("#crop_w").input_value() == ""
    page.locator("#blogGalleryEditor article").nth(1).get_by_role(
        "button", name="Naslovna", exact=True
    ).click()
    page.wait_for_function("document.querySelector('#crop_w').value !== ''")
    page.locator("#crop-size-range").fill("60")
    page.locator("#crop-size-range").dispatch_event("input")
    page.locator('#blogEditorForm button[type="submit"]').click()
    page.get_by_text("Blog objava shranjena.", exact=True).wait_for()
    post = next(iter(ui.module.load_blog_posts().values()))
    assert [item["description"] for item in post["images"]] == [
        "Druga fotografija",
        "Prva fotografija",
    ]
    assert post["image_desc"] == "Druga fotografija"
    with Image.open(ui.images / post["images"][0]["filename"]) as image:
        assert image.width == 360
    with Image.open(ui.images / post["images"][1]["filename"]) as image:
        assert image.width == 600
    page.reload()
    assert page.locator("#blogGalleryEditor article").count() == 2
    page.locator("#blogGalleryEditor article").first.get_by_role(
        "button", name="Odstrani", exact=True
    ).click()
    page.locator('#blogEditorForm button[type="submit"]').click()
    page.get_by_text("Blog objava shranjena.", exact=True).wait_for()
    saved = ui.module.load_blog_posts()[post["id"]]
    assert len(saved["images"]) == 1
    assert saved["image_desc"] == "Prva fotografija"

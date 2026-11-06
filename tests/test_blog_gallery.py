"""Public gallery rendering, automatic rotation and accessible controls."""

from io import BytesIO

import pytest
from PIL import Image
from playwright.sync_api import expect
from test_admin_memes_ui import browser as browser_fixture
from test_blog_translation import blog as blog_fixture

ui = blog_fixture
browser = browser_fixture


def test_public_pages_use_prepared_images_without_replacing_original_links(
    gallery, tmp_path, monkeypatch
):
    import blog_images

    monkeypatch.setattr(blog_images, "IMAGE_DIRECTORY", tmp_path)
    for index in range(1, 4):
        path = tmp_path / f"picture-{index}.jpg"
        Image.new("RGB", (1800, 1500), "green").save(path)
        blog_images.prepare_responsive_images(path)
    gallery.posts["javno"]["image"] = "picture-1.jpg"
    sources = blog_images.image_sources("picture-1.jpg")
    response = gallery.app.test_client().get("/blog")
    assert f'src="/blog/image/{sources["src"]}"' in response.text
    assert "480w, " in response.text
    assert "css/style.css" not in response.text
    response = gallery.app.test_client().get("/blog/javno")
    assert (
        f'data-gallery-main src="/blog/image/{sources["src"]}"'
        in response.text
    )
    assert 'href="/blog/image/picture-1.jpg"' in response.text
    assert f'data-display-src="/blog/image/{sources["src"]}"' in response.text


@pytest.fixture
def gallery(ui):
    ui.posts["javno"]["images"] = [
        {"filename": f"picture-{index}.jpg", "description": f"Opis {index}"}
        for index in range(1, 4)
    ]
    return ui


def test_public_gallery_thumbnails_captions_and_first_cover(gallery):
    response = gallery.app.test_client().get("/blog/javno")
    assert response.status_code == 200
    assert response.text.count('data-gallery-index="') == 3
    assert 'data-gallery-main src="/blog/image/picture-1.jpg"' in response.text
    assert "https://blog.example.com/blog/image/picture-1.jpg" in response.text
    assert 'data-description="Opis 3"' in response.text


def test_single_legacy_picture_needs_no_gallery_controls(ui):
    ui.posts["javno"]["image"] = "old.jpg"
    ui.posts["javno"]["image_desc"] = "Stara slika"
    response = ui.app.test_client().get("/blog/javno")
    assert 'src="/blog/image/old.jpg"' in response.text
    assert "data-gallery-play" not in response.text
    assert "data-gallery-index" not in response.text


def serve_pictures(page):
    buffer = BytesIO()
    Image.new("RGB", (600, 500), (75, 130, 110)).save(buffer, format="JPEG")
    page.route(
        "**/blog/image/**",
        lambda route: route.fulfill(
            body=buffer.getvalue(), content_type="image/jpeg"
        ),
    )


def test_browser_gallery_rotates_and_manual_selection_pauses(
    gallery, browser, tmp_path
):
    page = browser.page
    serve_pictures(page)
    page.clock.install()
    page.goto(browser.base + "/blog/javno")
    root = page.locator("[data-blog-gallery]")
    root.scroll_into_view_if_needed()
    page.mouse.move(0, 0)
    page.clock.run_for(5200)
    expect(root).to_have_attribute("data-current-index", "1")
    expect(page.locator("[data-gallery-caption]")).to_have_text("Opis 2")
    page.locator('[data-gallery-index="2"]').click()
    expect(root).to_have_attribute("data-current-index", "2")
    page.clock.run_for(10000)
    expect(root).to_have_attribute("data-current-index", "2")
    expect(page.locator("[data-gallery-play]")).to_have_attribute(
        "aria-label", "Predvajaj menjavanje"
    )
    expect(page.locator("[data-gallery-play] i")).to_have_class(
        "bi bi-play-fill"
    )
    expect(page.locator("[data-gallery-play]")).to_have_attribute(
        "aria-pressed", "false"
    )
    page.locator("[data-gallery-play]").click()
    page.clock.run_for(5200)
    expect(root).to_have_attribute("data-current-index", "0")
    expect(page.locator("[data-gallery-play]")).to_have_attribute(
        "aria-label", "Zaustavi menjavanje"
    )
    expect(page.locator("[data-gallery-play] i")).to_have_class(
        "bi bi-pause-fill"
    )
    expect(page.locator("[data-gallery-play]")).to_have_attribute(
        "aria-pressed", "true"
    )
    page.locator("[data-gallery-play]").click()
    page.clock.run_for(10000)
    expect(root).to_have_attribute("data-current-index", "0")
    expect(page.locator("[data-gallery-play] i")).to_have_class(
        "bi bi-play-fill"
    )
    page.locator("[data-gallery-play]").click()
    page.clock.run_for(5200)
    expect(root).to_have_attribute("data-current-index", "1")
    page.locator("[data-gallery-prev]").click()
    expect(root).to_have_attribute("data-current-index", "0")
    for width in [320, 390, 820, 1440]:
        page.set_viewport_size({"width": width, "height": 900})
        assert page.evaluate(
            "document.documentElement.scrollWidth <= innerWidth + 1"
        )
    page.screenshot(
        path=str(tmp_path / "blog-gallery-desktop.png"), full_page=True
    )


def test_browser_gallery_respects_reduced_motion(gallery, browser):
    page = browser.page
    page.emulate_media(reduced_motion="reduce")
    serve_pictures(page)
    page.clock.install()
    page.goto(browser.base + "/blog/javno")
    page.clock.run_for(11000)
    expect(page.locator("[data-blog-gallery]")).to_have_attribute(
        "data-current-index", "0"
    )
    expect(page.locator("[data-gallery-play]")).to_have_attribute(
        "aria-label", "Predvajaj menjavanje"
    )

"""Public blog layout, search, reading navigation and localized forms."""

import pytest
from playwright.sync_api import expect
from test_admin_memes_ui import browser as browser_fixture
from test_blog_translation import blog as blog_fixture

ui = blog_fixture
browser = browser_fixture


@pytest.fixture
def public_blog(ui):
    ui.posts["javno"]["content"] = (
        "<h2>Prvi korak</h2><p>Besedilo za mirno branje.</p>"
        "<h3>Majhna misel</h3><p>Veselje v preprostih stvareh.</p>"
        "<h2>Drugi korak</h2><blockquote>Vsak dan nekaj dobrega.</blockquote>"
        "<pre>" + "long_code_" * 100 + "</pre>"
        "<table><tr><th>Naslov</th><th>Vrednost</th></tr>"
        "<tr><td>"
        + "daljsebesedilo" * 100
        + "</td><td>Podatek</td></tr></table>"
    )
    for slug, title in [("o-meni", "O avtorju"), ("o-blogu", "O blogu")]:
        ui.posts[slug] = dict(ui.posts["javno"], id=slug, title=title)
    return ui


def test_browser_blog_layout_and_localized_subscription(public_blog, browser):
    page = browser.page
    paths = [
        "/blog",
        "/blog/javno",
        "/blog/o-meni",
        "/blog/o-blogu",
        "/blog/pogoji-uporabe",
        "/blog/politika-zasebnosti",
        "/blog/subscribe?lang=sl",
        "/blog/subscribe?lang=ar",
    ]
    for width in [320, 390, 820, 1440]:
        page.set_viewport_size({"width": width, "height": 844})
        for path in paths:
            page.goto(browser.base + path)
            assert page.locator("h1").is_visible()
            assert page.evaluate(
                "document.documentElement.scrollWidth <= innerWidth + 1"
            )
            if width in [390, 1440]:
                name = (
                    path.replace("/", "-").replace("?", "-").replace("=", "-")
                )
                page.screenshot(
                    path=f"/private/tmp/blog-ui{name}-{width}.png",
                    full_page=True,
                )
    assert page.locator("html").get_attribute("dir") == "rtl"
    assert page.locator("#subscribe-email").get_attribute("dir") == "ltr"


def test_browser_blog_search_and_reading_navigation(public_blog, browser):
    page = browser.page
    page.goto(browser.base + "/blog")
    page.get_by_role("searchbox", name="Poišči objavo").fill("cebelice")
    expect(page.locator("[data-blog-post]:visible")).to_have_count(1)
    assert "Čebelice" in page.locator("[data-blog-post]:visible").inner_text()
    page.locator("#blogSearch").fill("zzzzzzzzzz")
    expect(page.locator("#blogNoResults")).to_be_visible()
    page.get_by_role("button", name="Počisti iskanje").click()
    expect(page.locator("[data-blog-post]:visible")).to_have_count(4)
    assert page.locator("#blogSearch").evaluate(
        "(el) => el === document.activeElement"
    )
    page.goto(browser.base + "/blog/javno")
    page.locator("#blogToc summary").click()
    assert page.locator("#blogToc a").count() == 3
    page.get_by_role("link", name="Drugi korak", exact=True).click()
    assert page.url.endswith("#blog-section-3")
    assert page.locator("#blog-section-3").evaluate(
        "(el) => el.getBoundingClientRect().top >= 0"
    )
    page.locator(".blog-article-footer a").click()
    page.wait_for_url(browser.base + "/blog")


def test_browser_blog_without_javascript(public_blog, browser):
    context = browser.page.context.browser.new_context(
        java_script_enabled=False
    )
    page = context.new_page()
    try:
        page.goto(browser.base + "/blog")
        expect(page.locator("[data-blog-post]:visible")).to_have_count(4)
        assert page.locator(".blog-search").is_visible()
        page.get_by_role(
            "link", name="Preberi: Javna objava", exact=True
        ).click()
        page.wait_for_url(browser.base + "/blog/javno")
        assert page.locator(".blog-content").is_visible()
    finally:
        context.close()


def test_browser_pagination_index_and_global_search(public_blog, browser):
    for number in range(1, 27):
        public_blog.posts[f"page-{number}"] = dict(
            public_blog.posts["javno"],
            id=f"page-{number}",
            title=f"Novejša objava {number}",
            created_at=f"2026-09-{number:02d}T12:00:00+00:00",
        )
    page = browser.page
    page.goto(browser.base + "/blog")
    expect(page.locator("[data-blog-post]")).to_have_count(12)
    page.get_by_role("link", name="Naslednja →", exact=True).click()
    expect(page.locator(".blog-page-current")).to_have_text("2")
    assert "page=2" in page.url
    expect(page.locator("[data-blog-post]")).to_have_count(12)
    page.go_back()
    expect(page.locator(".blog-page-current")).to_have_text("1")
    page.locator("#blogIndex summary").click()
    expect(page.locator("#blogIndex a")).to_have_count(30)
    assert page.locator("#blogIndex time").count() == 30
    page.locator("#blogIndex summary").click()
    page.locator("#blogSearch").fill("cebelice")
    expect(page.locator("[data-blog-post]")).to_have_count(1)
    assert "Čebelice" in page.locator("[data-blog-post]").inner_text()
    assert "page=" not in page.url
    page.get_by_role("button", name="Počisti iskanje").click()
    expect(page.locator("[data-blog-post]")).to_have_count(12)
    assert page.locator("#blogSearch").evaluate(
        "el => el === document.activeElement"
    )

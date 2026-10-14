"""Admin palette follows the device clock independently of access gating."""

from datetime import datetime

import pytest
from flask import render_template
from test_fitness import browser as browser_fixture
from test_fitness import ui as ui_fixture

import fitness

ui = ui_fixture
browser = browser_fixture


@pytest.fixture
def themed(ui):
    ui.app.add_url_rule(
        "/admin/blog/new",
        "admin.blog_new",
        lambda: render_template("admin_blog_edit.html", post=None),
    )
    ui.app.add_url_rule(
        "/admin/logs",
        "admin.logs",
        lambda: render_template("admin_logs.html", system_log="Log"),
    )

    @ui.app.get("/blog/<post_id>", endpoint="blog.blog_post")
    def blog(post_id):
        return render_template(
            "blog_post.html",
            post={
                "id": post_id,
                "title": "Večerni zapis",
                "published": True,
                "created_at": "2026-10-14",
                "content_html": "<p>Zapis</p><blockquote>Misli</blockquote>",
            },
            blog_copy={"subscribe": "Naroči se"},
        )

    return ui


def test_theme_assets_are_admin_only(themed):
    for path in ("/admin/fitness", "/admin/blog/new", "/blog/one"):
        response = themed.client.get(path)
        assert response.status_code == 200
        assert "admin_night_theme.js" in response.text
        assert "admin_night_theme.css" in response.text
    themed.app.config["ADMIN"] = False
    response = themed.client.get("/blog/one")
    assert "admin_night_theme.js" not in response.text
    assert "admin_night_theme.css" not in response.text


@pytest.mark.parametrize(
    "hour,minute,dark",
    [
        (21, 59, False),
        (22, 0, True),
        (23, 59, True),
        (0, 0, True),
        (4, 59, True),
        (5, 0, False),
    ],
)
def test_browser_device_theme_boundaries(themed, browser, hour, minute, dark):
    from playwright.sync_api import expect

    page = browser.page
    page.clock.set_fixed_time(
        datetime(2026, 10, 14, hour, minute, tzinfo=fitness.LOCAL_ZONE)
    )
    page.goto(browser.base + "/admin/fitness")
    expect(page.locator("html[data-admin-night-theme]")).to_have_count(
        1 if dark else 0
    )
    if dark:
        expect(page.locator("html")).to_have_attribute("data-bs-theme", "dark")
        expect(page.locator("body")).to_have_css(
            "background-color", "rgb(20, 19, 17)"
        )
        expect(page.locator("#fitness-access-panel")).to_have_css(
            "background-color", "rgb(33, 30, 26)"
        )
        expect(page.locator("body")).to_have_css("color", "rgb(228, 216, 197)")
    else:
        expect(page.locator("body")).not_to_have_css(
            "background-color", "rgb(20, 19, 17)"
        )


@pytest.mark.parametrize(
    "path,surface",
    [
        ("/admin/blog/new", ".card"),
        ("/blog/one", ".blog-article"),
        ("/admin/logs", ".admin-panel"),
    ],
)
def test_browser_blog_editor_and_admin_surfaces(
    themed, browser, path, surface
):
    from playwright.sync_api import expect

    page = browser.page
    page.clock.set_fixed_time(
        datetime(2026, 10, 14, 23, 0, tzinfo=fitness.LOCAL_ZONE)
    )
    page.goto(browser.base + path)
    expect(page).to_have_url(browser.base + path)
    expect(page.locator(surface).first).to_have_css(
        "background-color", "rgb(33, 30, 26)"
    )
    expect(page.locator(".site-navbar")).to_have_css(
        "background-color", "rgb(33, 30, 26)"
    )
    if path == "/admin/blog/new":
        expect(page.locator("#title")).to_have_css(
            "background-color", "rgb(20, 19, 17)"
        )
        page.locator("#title").fill("Večerni osnutek")
        expect(page.locator("#title")).to_have_value("Večerni osnutek")
    if path == "/blog/one":
        expect(page.locator("blockquote")).to_have_css(
            "background-color", "rgb(33, 30, 26)"
        )


def test_browser_theme_switches_without_requests_and_recovers_after_sleep(
    themed, browser
):
    from playwright.sync_api import expect

    page = browser.page
    page.clock.install(
        time=datetime(2026, 10, 14, 21, 59, 50, tzinfo=fitness.LOCAL_ZONE)
    )
    page.goto(browser.base + "/admin/fitness")
    expect(page.locator("html[data-admin-night-theme]")).to_have_count(0)
    requests = []
    page.on("request", lambda request: requests.append(request.url))
    page.clock.run_for(10000)
    expect(page.locator("html")).to_have_attribute(
        "data-admin-night-theme", ""
    )
    page.clock.set_system_time(
        datetime(2026, 10, 15, 4, 59, 50, tzinfo=fitness.LOCAL_ZONE)
    )
    page.evaluate("window.dispatchEvent(new Event('focus'))")
    page.clock.run_for(10000)
    expect(page.locator("html[data-admin-night-theme]")).to_have_count(0)
    assert requests == []
    page.clock.set_system_time(
        datetime(2026, 10, 15, 23, 0, tzinfo=fitness.LOCAL_ZONE)
    )
    page.evaluate("window.dispatchEvent(new Event('pageshow'))")
    expect(page.locator("html")).to_have_attribute(
        "data-admin-night-theme", ""
    )

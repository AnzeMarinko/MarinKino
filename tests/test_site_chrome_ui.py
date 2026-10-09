"""Shared navigation and suggestion form browser regressions."""

import pytest
from flask import jsonify, render_template, render_template_string, request
from test_admin_memes_ui import browser as browser_fixture
from test_admin_memes_ui import ui as ui_fixture

ui = ui_fixture
browser = browser_fixture


@pytest.fixture
def site(ui):
    app = ui.app
    submitted = []
    app.config["SUGGESTION_RESPONSE"] = {"status": "success"}
    app.config["SUGGESTION_HTTP"] = 200

    @app.context_processor
    def preview_role():
        return {"view_as": app.config.get("VIEW_AS")}

    @app.route("/suggestions")
    def suggestions():
        return render_template("suggestions.html", pagetitle="Predlogi")

    @app.route("/movies/add-comment", methods=["POST"])
    def add_comment():
        submitted.append(
            {"body": request.json, "csrf": request.headers.get("X-CSRFToken")}
        )
        return jsonify(app.config["SUGGESTION_RESPONSE"]), app.config[
            "SUGGESTION_HTTP"
        ]

    languages = {
        "sl": dict(
            name="Slovenščina",
            flag="🇸🇮",
            direction="ltr",
            notice="",
            copy_link="Kopiraj povezavo",
            blog_title="Rože dobrega",
        ),
        "en": dict(
            name="English",
            flag="🇬🇧",
            direction="ltr",
            notice="Automatic translation",
            copy_link="Copy link",
            blog_title="Flowers of Goodness",
        ),
    }

    @app.route("/blog")
    def public_blog():
        return render_template_string(
            '{% extends "base.html" %}{% block content %}'
            "<main><h1>Blog</h1></main>{% endblock %}",
            pagetitle="Blog",
            blog_view="blog",
            blog_language="sl",
            blog_languages=languages,
            blog_translation_urls={
                "sl": "/blog",
                "en": "https://translate.google.com/?tl=en",
            },
        )

    @app.route("/music-test")
    def music():
        return render_template_string(
            '{% extends "base.html" %}{% block content %}'
            "<main><h1>Glasba</h1></main>{% endblock %}",
            is_music=True,
        )

    ui.submitted = submitted
    return ui


def test_site_templates_and_role_navigation(site):
    html = site.client.get("/suggestions").text
    assert 'aria-current="page"' in html
    assert 'id="suggestionForm"' in html
    assert 'id="main-content"' in html
    assert "Nadzorna plošča" in html
    site.app.config["VIEW_AS"] = "user"
    html = site.client.get("/suggestions").text
    assert 'href="/admin"' not in html
    assert "blog-view-as-notice" in html
    site.app.config["VIEW_AS"] = "anonymous"
    html = site.client.get("/blog").text
    assert 'href="/login"' in html
    assert 'href="/movies"' not in html
    assert "Pogoji uporabe" in html
    assert "blog-language-toggle" in html


def test_browser_mobile_menu_layout_and_keyboard(site, browser):
    page = browser.page
    for width in [320, 390, 820, 1200, 1440]:
        page.set_viewport_size({"width": width, "height": 844})
        page.goto(browser.base + "/suggestions")
        page.wait_for_function(
            'document.querySelector("#blog-header-spacer").style.height !== ""'
        )
        assert (
            page.locator(".nav-link[aria-current=page]").inner_text()
            == "Predlogi"
        )
        assert page.evaluate(
            "document.documentElement.scrollWidth <= innerWidth + 1"
        )
        if width < 1400:
            toggle = page.locator(".site-menu-toggle")
            toggle.click()
            page.locator("#mainNavbar.show").wait_for()
            page.wait_for_function(
                'document.querySelector("#main-content").getBoundingClientRect()'
                '.top >= document.querySelector(".site-header")'
                ".getBoundingClientRect().bottom - 1"
            )
            page.locator("#siteAccountToggle").click()
            assert page.get_by_role(
                "link", name="Nadzorna plošča", exact=True
            ).is_visible()
            page.keyboard.press("Escape")
            page.keyboard.press("Escape")
            page.wait_for_function(
                'document.querySelector(".site-menu-toggle")'
                '.getAttribute("aria-expanded") === "false"'
            )
            assert toggle.evaluate("(el) => el === document.activeElement")
            page.wait_for_function(
                '!document.querySelector("#mainNavbar")'
                '.classList.contains("collapsing")'
            )
        page.screenshot(
            path=f"/private/tmp/site-suggestions-{width}.png", full_page=True
        )
    page.goto(browser.base + "/suggestions")
    page.keyboard.press("Tab")
    assert page.locator(".site-skip-link").evaluate(
        "(el) => el === document.activeElement"
    )
    page.keyboard.press("Enter")
    assert page.locator("#main-content").evaluate(
        "(el) => el === document.activeElement"
    )


def test_browser_suggestion_draft_error_and_success(site, browser):
    page = browser.page
    page.goto(browser.base + "/suggestions")
    page.locator("#suggestionType").select_option("napaka")
    assert "korake" in page.locator("#suggestionHint").inner_text()
    page.locator("#suggestionText").fill(
        "Na strani vreme ne najdem izbranega kraja."
    )
    page.reload()
    assert page.locator("#suggestionType").input_value() == "napaka"
    assert "ne najdem" in page.locator("#suggestionText").input_value()
    site.app.config["SUGGESTION_RESPONSE"] = {
        "status": "error",
        "message": "Testna napaka",
    }
    site.app.config["SUGGESTION_HTTP"] = 503
    page.locator("#sendSuggestion").click()
    page.get_by_text("Testna napaka", exact=True).wait_for()
    assert "ne najdem" in page.locator("#suggestionText").input_value()
    assert site.submitted[0]["csrf"] == "test-csrf"
    assert site.submitted[0]["body"]["movieFolder"] == "Splošno"
    site.app.config["SUGGESTION_RESPONSE"] = {"status": "success"}
    site.app.config["SUGGESTION_HTTP"] = 200
    page.locator("#sendSuggestion").click()
    page.get_by_text("Predlog je uspešno shranjen.", exact=False).wait_for()
    assert page.locator("#suggestionText").input_value() == ""
    assert (
        page.evaluate(
            'localStorage.getItem(document.querySelector("#suggestionsPage").dataset.draftKey)'
        )
        is None
    )
    assert page.locator("#suggestionStatus").evaluate(
        "(el) => el === document.activeElement"
    )


def test_browser_suggestion_trim_validation_and_duplicate_submit(
    site, browser
):
    page = browser.page
    page.goto(browser.base + "/suggestions")
    page.locator("#suggestionType").select_option("komentar")
    page.locator("#suggestionText").fill("           kratek    ")
    page.locator("#sendSuggestion").click()
    assert page.locator("#suggestionText").evaluate(
        "(el) => !el.validity.valid"
    )
    assert not site.submitted
    page.locator("#suggestionText").fill(
        "Veljaven predlog za izboljšavo strani."
    )
    pending = []
    page.route("**/movies/add-comment", lambda route: pending.append(route))
    page.locator("#sendSuggestion").click()
    page.wait_for_function(
        'document.querySelector("#sendSuggestion").disabled'
    )
    page.evaluate(
        'document.querySelector("#suggestionForm")'
        '.dispatchEvent(new Event("submit", {cancelable:true}))'
    )
    assert len(pending) == 1
    assert page.locator("#suggestionText").is_disabled()
    pending[0].fulfill(status=200, json={"status": "success"})
    page.get_by_text("Predlog je uspešno shranjen.", exact=False).wait_for()


def test_browser_translation_toolbar_and_preview_role(site, browser):
    site.app.config["VIEW_AS"] = "anonymous"
    page = browser.page
    page.set_viewport_size({"width": 320, "height": 844})
    page.goto(browser.base + "/blog")
    page.locator("#blog-language-toggle").click()
    assert page.locator(".site-translation__options").is_visible()
    assert page.evaluate(
        "document.documentElement.scrollWidth <= innerWidth + 1"
    )
    page.keyboard.press("Escape")
    page.wait_for_function(
        'document.querySelector(".site-header").getBoundingClientRect().top'
        ' >= document.querySelector("#blog-view-as-notice")'
        ".getBoundingClientRect().bottom - 1"
    )
    page.evaluate(
        """() => { const bar = document.createElement('div');
        bar.id = 'gt-nvframe';
        bar.style.cssText = 'position:fixed;top:0;left:0;width:100%;' +
        'height:40px;z-index:1100'; document.body.append(bar);
        document.querySelector('#blog-view-as-notice').style.top = '40px'; }"""
    )
    page.wait_for_function(
        'document.querySelector(".site-header").getBoundingClientRect().top'
        ' >= document.querySelector("#blog-view-as-notice")'
        ".getBoundingClientRect().bottom - 1"
    )
    page.screenshot(
        path="/private/tmp/site-blog-translation-320.png", full_page=True
    )
    page.goto(browser.base + "/music-test")
    assert page.locator(".site-header-static").count() == 1
    assert page.locator(".site-footer").count() == 0


def test_browser_suggestions_without_storage_keep_failed_text(site, browser):
    page = browser.page
    page.add_init_script("""Storage.prototype.setItem = function() {
        throw new Error('Storage disabled'); };""")
    page.goto(browser.base + "/suggestions")
    page.locator("#suggestionType").select_option("komentar")
    page.locator("#suggestionText").fill("Besedilo ostane v odprtem obrazcu.")
    assert "ne omogoča" in page.locator("#suggestionDraftStatus").inner_text()
    page.route(
        "**/movies/add-comment",
        lambda route: route.fulfill(status=401, json={"status": "error"}),
    )
    page.locator("#sendSuggestion").click()
    page.get_by_text("Seja je potekla", exact=False).wait_for()
    assert page.locator("#suggestionText").input_value() == (
        "Besedilo ostane v odprtem obrazcu."
    )
    assert page.locator("#sendSuggestion").is_enabled()

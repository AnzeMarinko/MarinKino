"""Continuity when users return to downloads or suggested content forms."""

from flask import jsonify, render_template, request
from playwright.sync_api import expect
from test_admin_memes_ui import browser as browser_fixture
from test_admin_memes_ui import ui as ui_fixture

ui = ui_fixture
browser = browser_fixture


def test_browser_suggestion_context_preserves_existing_draft(ui, browser):
    ui.app.add_url_rule(
        "/suggestions",
        "suggestions",
        lambda: render_template("suggestions.html"),
    )
    page = browser.page
    page.goto(browser.base + "/suggestions?type=film")
    expect(page.locator("#suggestionType")).to_have_value("predlog za film")
    page.locator("#suggestionText").fill(
        "Moj predlog za film ostane shranjen."
    )
    page.goto(browser.base + "/suggestions?type=music")
    expect(page.locator("#suggestionType")).to_have_value("predlog za film")
    expect(page.locator("#suggestionText")).to_have_value(
        "Moj predlog za film ostane shranjen."
    )


def test_browser_download_refresh_preserves_preparation(ui, browser):
    ui.app.add_url_rule("/movies", "movies.index", lambda: "Films")
    path = "/movies/download/test/film"
    status_path = path + "/status/job-one"
    ui.app.config["DOWNLOAD_READY"] = False

    @ui.app.get(path)
    def download_page():
        queued = bool(request.args.get("job"))
        return render_template(
            "movie_download.html",
            movie={"title": "Poletni večer"},
            job_state="pending" if queued else None,
            status_url=status_path if queued else "",
            prepare_url=path + "/prepare",
        )

    @ui.app.post(path + "/prepare")
    def prepare():
        return jsonify(
            state="pending",
            page_url=path + "?job=job-one",
            status_url=status_path,
        ), 202

    @ui.app.get(status_path)
    def status():
        if ui.app.config["DOWNLOAD_READY"]:
            return jsonify(state="done", download_url=path + "/file.zip")
        return jsonify(state="pending")

    page = browser.page
    page.goto(browser.base + path)
    page.get_by_role("button", name="Pripravi prenos").click()
    page.wait_for_url("**?job=job-one")
    page.reload()
    expect(page.locator("#movie-download-form button")).to_be_disabled()
    expect(page.locator("#movie-download-status")).to_contain_text(
        "čaka na pripravo"
    )
    ui.app.config["DOWNLOAD_READY"] = True
    link = page.get_by_role("link", name="Prenesi film")
    expect(link).to_be_visible(timeout=6000)
    expect(link).to_have_attribute("href", path + "/file.zip")
    assert page.url.endswith("?job=job-one")

"""Movie discovery and playback with isolated content and mocked mutations."""

import pytest
from flask import Response, jsonify, render_template, request
from playwright.sync_api import expect
from test_admin_memes_ui import (
    PNG,
)
from test_admin_memes_ui import (
    browser as browser_fixture,
)
from test_admin_memes_ui import (
    ui as ui_fixture,
)

ui = ui_fixture
browser = browser_fixture


@pytest.fixture
def films(ui):
    movie = dict(
        movie_id="film-one",
        folder="/test/one",
        thumbnail="/test/poster.png",
        cover="/test/poster.png",
        title="Poletni večer",
        year="2025",
        original_title="Summer",
        slosinh="Slovenski podnapisi",
        genres=["drama"],
        players="Ana",
        description="Opis filma <b>ostane besedilo</b>.",
        runtimes=90,
        watch_ratio=35,
        last_play_time=0,
        recommendation_level="warm-recommend",
        ratings_summary={},
        user_notes={},
    )
    calls = []
    ui.app.config["MOVIE_PAGE_FAIL"] = False

    @ui.app.route("/movies")
    def catalog():
        movies = [] if request.args.get("q") == "missing" else [movie]
        return render_template(
            "movies.html",
            movies=movies,
            has_more=bool(movies),
            group_folders={"test": "Filmi"},
            known_genres=["drama"],
            selected_movietype="",
            selected_genre="",
            sort="",
            onlyunwatched=False,
            onlyrecommended=False,
        )

    @ui.app.route("/movies/page")
    def page():
        if ui.app.config["MOVIE_PAGE_FAIL"]:
            return jsonify(error="offline"), 503
        return jsonify(
            movies=[
                dict(
                    movie,
                    movie_id="film-two",
                    title="Drugi film",
                    is_admin=True,
                )
            ],
            has_more=False,
        )

    @ui.app.route("/movies/play/test/one")
    def player():
        collection = request.args.get("mode") == "collection"
        files = ["film.mp4", "second.mp4"] if collection else ["film.mp4"]
        data = dict(
            movie,
            watch_info={
                name: dict(watch_ratio=35, last_play_time=0) for name in files
            },
            runtimes_by_files={"film": 90, "second": 45},
        )
        return render_template(
            "player.html",
            movie=data,
            is_collection=collection,
            known_genres=["drama"],
            group_folder="test",
            folder="one",
            video_file="film.mp4",
            video_file_m3u8="master.m3u8"
            if request.args.get("mode") == "hls"
            else None,
            video_files=files,
            subtitles=[],
            subtitle_buttons=[],
            slosubs_file=None,
        )

    @ui.app.route("/movies/file/<path:name>")
    def poster(name):
        return Response(PNG, mimetype="image/png")

    @ui.app.route("/movies/progress-change", methods=["POST"])
    @ui.app.route("/movies/recommend", methods=["POST"])
    @ui.app.route("/movies/remove/test/one", methods=["POST"])
    def mutate():
        calls.append(request.path)
        return jsonify(status="success")

    @ui.app.route("/movies/add-comment", methods=["POST"])
    def comment():
        if ui.app.config.get("COMMENT_FAIL"):
            return jsonify(status="error", message="Poskusi znova."), 503
        return jsonify(status="success")

    @ui.app.route("/movies/rate", methods=["POST"])
    def rate():
        return jsonify(
            status="success",
            summary={
                key: dict(avg=4, count=1)
                for key in [
                    "violence",
                    "sexual",
                    "age_group",
                    "would_watch_again",
                    "video_quality",
                    "subtitles_quality",
                ]
            },
        )

    return ui, calls


def test_movie_templates_render(films):
    ui, _ = films
    for path in ["/movies", "/movies/play/test/one"]:
        response = ui.app.test_client().get(path)
        assert response.status_code == 200
        assert b"movies_ui.css" in response.data


def test_browser_movie_catalog_filters_and_retry(films, browser):
    ui, calls = films
    page = browser.page
    page.goto(browser.base + "/movies")
    assert page.locator(".movie-card").count() == 1
    assert page.get_by_role("link", name="Nadaljuj ogled").is_visible()
    page.get_by_text("Opis in možnosti", exact=True).click()
    assert page.get_by_text(
        "Opis filma <b>ostane besedilo</b>.", exact=True
    ).is_visible()
    page.get_by_text("Pogledano", exact=True).click()
    page.wait_for_function(
        "document.querySelector('.movie-watch-state').textContent.includes('✓')"
    )
    assert calls == ["/movies/progress-change"]
    ui.app.config["MOVIE_PAGE_FAIL"] = True
    page.get_by_role("button", name="Naloži več filmov").click()
    expect(
        page.get_by_text("Nalaganje ni uspelo. Poskusi znova.")
    ).to_be_visible()
    ui.app.config["MOVIE_PAGE_FAIL"] = False
    page.get_by_role("button", name="Naloži več filmov").click()
    page.wait_for_function(
        "document.querySelectorAll('.movie-card').length === 2"
    )
    assert page.locator("#movies-more").is_hidden()
    page.get_by_role("button", name="Poišči filme").click()
    assert "onlyunwatched=off" in page.url
    assert "onlyrecommended=off" in page.url
    page.goto(browser.base + "/movies?q=missing")
    assert page.get_by_text(
        "Ni filmov za izbrane pogoje.", exact=False
    ).is_visible()


def test_browser_movie_responsive_player(films, browser):
    page = browser.page
    for width in [320, 390, 820, 1440]:
        page.set_viewport_size({"width": width, "height": 844})
        for path in ["/movies", "/movies/play/test/one"]:
            page.goto(browser.base + path)
            assert page.locator("h1").is_visible()
            assert page.evaluate(
                "document.documentElement.scrollWidth <= innerWidth + 1"
            )
            if "play" in path:
                assert page.locator("#videoPlayer").is_visible()
                if width < 800:
                    assert (
                        page.locator("#videoPlayer").bounding_box()["y"]
                        < page.locator(
                            ".movie-page > .description"
                        ).bounding_box()["y"]
                    )
            kind = "play" if "play" in path else "list"
            page.screenshot(
                path=f"/private/tmp/movie-ui-{width}-{kind}.png",
                full_page=True,
            )
    # Fixture asserts that no JavaScript errors were emitted.


def test_browser_movie_comment_and_rating(films, browser):
    ui, _ = films
    page = browser.page
    page.goto(browser.base + "/movies/play/test/one")
    ui.app.config["COMMENT_FAIL"] = True
    page.locator("#commentText").fill("Dober film za večer.")
    page.get_by_role("button", name="Pošlji komentar").click()
    expect(page.locator("#commentStatus")).to_have_text("Poskusi znova.")
    assert page.locator("#commentText").input_value() == "Dober film za večer."
    ui.app.config["COMMENT_FAIL"] = False
    page.get_by_role("button", name="Pošlji komentar").click()
    expect(page.locator("#commentStatus")).to_contain_text(
        "Komentar je poslan"
    )
    assert page.locator("#commentText").input_value() == ""
    page.get_by_role("button", name="Oceni film", exact=True).click()
    expect(page.get_by_role("dialog")).to_be_visible()
    page.locator('.stars[data-name="would-watch"] button').nth(3).click()
    page.get_by_role("button", name="Pošlji oceno").click()
    expect(page.get_by_role("dialog")).to_be_hidden()
    expect(page.locator("#would-watch-again-count")).to_have_text("1")


def test_browser_movie_collection_and_hls_fallback(films, browser):
    page = browser.page
    page.goto(browser.base + "/movies/play/test/one?mode=collection")
    expect(page.locator("#chooseVideoNotice")).to_be_visible()
    page.locator(".video-btn").first.click()
    expect(page.locator("#collectionPlayerContainer")).to_be_visible()
    expect(page.locator(".video-btn").first).to_have_class(
        "video-btn selected"
    )
    assert (
        page.locator("#videoPlayer").get_attribute("src").endswith("/film.mp4")
    )
    page.goto(browser.base + "/movies/play/test/one?mode=hls")
    expect(page.locator("#hlsVideoPlayer")).to_be_visible()
    page.wait_for_function("""() => {
        const video = document.getElementById('hlsVideoPlayer');
        return video.src.endsWith('/master.m3u8') ||
            getComputedStyle(document.getElementById('hlsAudioContainer'))
                .display !== 'none';
    }""")

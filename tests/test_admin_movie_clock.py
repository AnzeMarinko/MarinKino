"""Device-local movie end estimates, including resume and collection files."""

import re
from datetime import datetime

import pytest
from flask import render_template, request
from test_fitness import browser as browser_fixture
from test_fitness import ui as ui_fixture

import fitness

ui = ui_fixture
browser = browser_fixture


@pytest.fixture
def film(ui):
    @ui.app.get("/movies/play/test/clock")
    def player():
        minutes = float(request.args.get("minutes", 120))
        resume = float(request.args.get("resume", 0))
        mode = request.args.get("mode", "mp4")
        files = (
            ["film.mp4", "second.mp4"]
            if mode == "collection"
            else ["film.mp4"]
        )
        movie = dict(
            movie_id="clock-film",
            folder="/test/clock",
            title="Večerni film",
            year="2026",
            original_title="Film",
            runtimes=minutes,
            runtimes_by_files={"film": minutes, "second": 30},
            last_play_time=resume,
            watch_ratio=0,
            cover="/test/poster.png",
            watch_info={
                name: {
                    "watch_ratio": 0,
                    "last_play_time": resume if name == "film.mp4" else 0,
                }
                for name in files
            },
            genres=[],
            players="",
            description="Test",
            ratings_summary={},
            user_notes={},
            recommendation_level="warm-recommend",
        )
        return render_template(
            "player.html",
            movie=movie,
            is_collection=mode == "collection",
            known_genres=[],
            group_folder="test",
            folder="clock",
            video_file="film.mp4",
            video_file_m3u8="master.m3u8" if mode == "hls" else None,
            video_files=files,
            subtitles=[],
            subtitle_buttons=[],
            slosubs_file=None,
        )

    return ui


def test_movie_warning_markup_is_only_for_admin(film):
    response = film.client.get("/movies/play/test/clock")
    assert response.status_code == 200
    assert 'id="admin-movie-duration-warning"' in response.text
    assert '"duration_min": 120.0' in response.text
    film.app.config["ADMIN"] = False
    response = film.client.get("/movies/play/test/clock")
    assert response.status_code == 200
    assert "admin_movie_clock.js" not in response.text
    assert "admin-movie-duration-warning" not in response.text


@pytest.mark.parametrize("mode", ["mp4", "hls"])
@pytest.mark.parametrize(
    "minutes,late", [(90, False), (91, True), (120, True)]
)
def test_browser_movie_end_warning_boundary(
    film, browser, mode, minutes, late
):
    from playwright.sync_api import expect

    page = browser.page
    page.clock.set_fixed_time(
        datetime(2026, 10, 14, 22, 15, tzinfo=fitness.LOCAL_ZONE)
    )
    page.goto(
        browser.base + f"/movies/play/test/clock?mode={mode}&minutes={minutes}"
    )
    warning = page.locator("#admin-movie-duration-warning")
    if late:
        expect(warning).to_be_visible()
        expect(warning).to_contain_text("presega 23:45")
        expect(warning).to_contain_text("Stran se ob polnoči zapre")
        expect(warning).to_contain_text("preusmeri na Gibanje")
    else:
        expect(warning).not_to_be_visible()


def test_browser_resume_seek_speed_and_end_change_estimate(film, browser):
    from playwright.sync_api import expect

    page = browser.page
    # Fake media metadata must not race a CDN player's ready/restore callbacks.
    page.route(re.compile(r"^https://"), lambda route: route.abort())
    page.clock.set_fixed_time(
        datetime(2026, 10, 14, 22, 15, tzinfo=fitness.LOCAL_ZONE)
    )
    page.goto(browser.base + "/movies/play/test/clock?resume=3600")
    warning = page.locator("#admin-movie-duration-warning")
    expect(warning).not_to_be_visible()
    page.evaluate("""() => {
        const video = document.getElementById('videoPlayer');
        Object.defineProperty(video, 'duration', {
            value:7200, configurable:true
        });
        Object.defineProperty(video, 'currentTime', {
            value:0, writable:true, configurable:true
        });
        video.dispatchEvent(new Event('seeked'));
    }""")
    expect(warning).to_be_visible()
    expect(warning).to_contain_text("15. 10.")
    page.evaluate("document.getElementById('videoPlayer').playbackRate = 2")
    expect(warning).not_to_be_visible()
    page.evaluate("document.getElementById('videoPlayer').playbackRate = 1")
    expect(warning).to_be_visible()
    page.evaluate("""() => {
        const video = document.getElementById('videoPlayer');
        video.currentTime = 7200;
        video.dispatchEvent(new Event('ended'));
    }""")
    expect(warning).not_to_be_visible()


def test_browser_collection_warns_for_selected_file(film, browser):
    from playwright.sync_api import expect

    page = browser.page
    page.clock.set_fixed_time(
        datetime(2026, 10, 14, 22, 15, tzinfo=fitness.LOCAL_ZONE)
    )
    page.goto(browser.base + "/movies/play/test/clock?mode=collection")
    warning = page.locator("#admin-movie-duration-warning")
    expect(warning).not_to_be_visible()
    page.locator(".video-btn").first.click()
    expect(warning).to_be_visible()
    page.locator(".video-btn").nth(1).click()
    expect(warning).not_to_be_visible()

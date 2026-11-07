"""Collections retain every episode and progress across MP4/HLS switches."""

import json
import shutil
import subprocess
from datetime import datetime, timezone
from urllib.parse import urlsplit

import pytest
from jinja2 import DictLoader
from playwright.sync_api import expect
from test_admin_memes_ui import browser as browser_fixture
from test_admin_memes_ui import ui as ui_fixture
from test_movie_security import movies as movies_fixture
from test_movies_ui import films as films_fixture

ui = ui_fixture
browser = browser_fixture
movies = movies_fixture
films = films_fixture


@pytest.mark.parametrize(
    "files,streams,expected",
    [
        ([], ["ep1", "ep2"], ["ep1/master.m3u8", "ep2/master.m3u8"]),
        (
            ["ep1.mp4", "ep2.mp4"],
            ["ep1"],
            ["ep1/master.m3u8", "ep2.mp4"],
        ),
    ],
)
def test_real_collection_route_has_every_source_and_resume(
    movies, files, streams, expected
):
    film = movies.module.all_films["/group/film-00"]
    film.update(
        video_files=files,
        video_files_m3u8=streams,
        runtimes_by_files={"ep1": 10, "ep2": 10},
    )
    movies.redis.hset(
        "prog:member",
        mapping={
            "group/film-00/ep1": json.dumps(
                {"last_play_time": 120, "duration": 600}
            ),
            "group/film-00/ep2": json.dumps(
                {"last_play_time": 240, "duration": 600}
            ),
        },
    )
    movies.app.jinja_loader = DictLoader(
        {
            "player.html": "{{ {'collection': is_collection, "
            "'sources': video_sources, 'movie': movie}|tojson }}"
        }
    )
    response = movies.client.get("/movies/play/group/film-00")
    assert response.status_code == 200
    result = json.loads(response.text)
    assert result["collection"]
    assert [source["path"] for source in result["sources"]] == expected
    assert result["movie"]["watch_ratio"] == 30
    assert result["movie"]["last_play_time"] == 120
    assert result["movie"]["watch_info"]["ep2.mp4"]["last_play_time"] == 240


def test_nested_episode_progress_stays_separate_and_mark_seen_uses_same_keys(
    movies,
):
    film = movies.module.all_films["/group/film-00"]
    film.update(
        video_files=[],
        video_files_m3u8=["Season/ep1", "Season/ep2"],
        runtimes_by_files={"Season/ep1": 10, "Season/ep2": 15},
    )
    for episode, time in [("ep1", 120), ("ep2", 240)]:
        response = movies.client.post(
            "/movies/video-progress",
            json={
                "filename": (
                    "/movies/file/group/film-00/Season/"
                    + episode
                    + "/master.m3u8"
                ),
                "currentTime": time,
                "duration": 600,
            },
        )
        assert response.status_code == 204
    assert set(movies.redis.hgetall("prog:member")) == {
        "group/film-00/Season/ep1",
        "group/film-00/Season/ep2",
    }
    result = movies.module.add_watch_info(
        film, movies.module.get_user_progress_data("member")
    )
    assert result["watch_info"]["Season/ep1.mp4"]["last_play_time"] == 120
    assert result["watch_info"]["Season/ep2.mp4"]["last_play_time"] == 240
    assert (
        movies.client.post(
            "/movies/progress-change",
            json={"movieId": film["movie_id"], "izbor": 100},
        ).status_code
        == 204
    )
    result = movies.module.add_watch_info(
        film, movies.module.get_user_progress_data("member")
    )
    assert result["watch_ratio"] == 100
    assert (
        movies.client.post(
            "/movies/video-progress",
            json={
                "filename": "group/film-00/Season/unknown.mp4",
                "currentTime": 10,
                "duration": 600,
            },
        ).status_code
        == 404
    )


def test_root_hls_uses_canonical_progress_identity(movies):
    film = movies.module.all_films["/group/film-00"]
    film.update(video_files=[], video_files_m3u8=["."])
    movies.app.jinja_loader = DictLoader(
        {
            "player.html": (
                "{{ {'sources': video_sources, "
                "'progress': progress_source_url}|tojson }}"
            )
        }
    )
    response = movies.client.get("/movies/play/group/film-00")
    assert response.status_code == 200
    result = json.loads(response.text)
    assert result["sources"][0]["path"] == "master.m3u8"
    response = movies.client.post(
        "/movies/video-progress",
        json={
            "filename": result["progress"],
            "currentTime": 10,
            "duration": 600,
        },
    )
    assert response.status_code == 204


@pytest.fixture
def media(tmp_path):
    if shutil.which("ffmpeg") is None:
        pytest.skip("FFmpeg is required for real playback fixtures")
    source = tmp_path / "source.mp4"
    subprocess.run(
        [
            "ffmpeg",
            "-nostdin",
            "-v",
            "error",
            "-f",
            "lavfi",
            "-i",
            "color=c=blue:s=160x90:r=5:d=90",
            "-f",
            "lavfi",
            "-i",
            "sine=frequency=440:duration=90",
            "-c:v",
            "libx264",
            "-threads",
            "1",
            "-preset",
            "ultrafast",
            "-pix_fmt",
            "yuv420p",
            "-g",
            "20",
            "-c:a",
            "aac",
            "-b:a",
            "32k",
            str(source),
        ],
        check=True,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    subprocess.run(
        [
            "ffmpeg",
            "-nostdin",
            "-v",
            "error",
            "-i",
            str(source),
            "-c",
            "copy",
            "-hls_time",
            "4",
            "-hls_playlist_type",
            "vod",
            "-hls_segment_type",
            "fmp4",
            str(tmp_path / "master.m3u8"),
        ],
        check=True,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    return tmp_path


def serve_media(page, media):
    def serve(route):
        name = urlsplit(route.request.url).path.rsplit("/", 1)[-1]
        path = media / ("source.mp4" if name == "second.mp4" else name)
        if not path.is_file():
            route.continue_()
            return
        data = path.read_bytes()
        headers = {"Accept-Ranges": "bytes"}
        status = 200
        byte_range = route.request.headers.get("range")
        if byte_range:
            start, end = byte_range.removeprefix("bytes=").split("-")
            start = int(start)
            end = int(end) if end else len(data) - 1
            headers["Content-Range"] = f"bytes {start}-{end}/{len(data)}"
            data = data[start : end + 1]
            status = 206
        route.fulfill(
            body=data,
            status=status,
            headers=headers,
            content_type="application/vnd.apple.mpegurl"
            if name.endswith(".m3u8")
            else "video/mp4",
        )

    page.route("**/movies/file/test/one/**", serve)


@pytest.mark.parametrize("mode", ["hls-collection", "mixed"])
def test_browser_real_collection_switching_resume_and_progress(
    films, browser, media, mode
):
    page = browser.page
    page.clock.install(time=datetime(2026, 11, 6, 12, tzinfo=timezone.utc))
    serve_media(page, media)
    progress = []
    page.route(
        "**/movies/video-progress",
        lambda route: (
            progress.append(route.request.post_data_json),
            route.fulfill(status=204, body=""),
        ),
    )
    page.goto(browser.base + "/movies/play/test/one?mode=" + mode)
    page.evaluate("""() => {
        const RealHls = window.Hls;
        window.episodeHls = [];
        window.Hls = class extends RealHls {
            constructor(options) { super(options); episodeHls.push(this); }
            destroy() { this.wasDestroyed = true; super.destroy(); }
        };
        window.originalCollectionVideo =
            document.getElementById('videoPlayer');
    }""")
    buttons = page.locator(".video-btn")
    expect(buttons).to_have_count(2)
    buttons.first.click()
    video = page.locator("#collectionPlayerContainer video")
    page.wait_for_function(
        "() => document.getElementById('videoPlayer').currentTime > .1"
    )
    assert video.evaluate("node => node.duration > 80")
    video.evaluate("node => { node.pause(); node.currentTime = 12; }")
    buttons.nth(1).click()
    page.wait_for_function(
        "() => document.getElementById('videoPlayer').currentTime > .1"
    )
    assert page.evaluate("episodeHls[0].wasDestroyed")
    assert video.evaluate("node => node === window.originalCollectionVideo")
    expect(buttons.first).to_have_attribute("data-resume", "12")
    assert video.evaluate("node => node.duration > 80")
    video.evaluate("node => { node.currentTime = 31; }")
    page.clock.fast_forward(20_000)
    page.wait_for_function(
        "() => document.getElementById('videoPlayer').currentTime >= 31"
    )
    assert progress
    assert progress[-1]["filename"].endswith(
        "/second/master.m3u8" if mode == "hls-collection" else "/second.mp4"
    )
    assert not progress[-1]["filename"].startswith("blob:")
    buttons.first.click()
    page.wait_for_function(
        "() => document.getElementById('videoPlayer').currentTime >= 12"
    )
    assert video.evaluate("node => node.currentTime < 20")
    assert page.evaluate(
        "episodeHls.slice(0, -1).every(item => item.wasDestroyed)"
    )
    assert page.locator("#collectionPlayerContainer .plyr").count() == 1
    expect(buttons.first).to_have_attribute("aria-pressed", "true")
    expect(buttons.nth(1)).to_have_attribute("aria-pressed", "false")

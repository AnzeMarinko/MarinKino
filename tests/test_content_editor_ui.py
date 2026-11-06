"""Browser regressions for local editors; no media services."""

import json
import os
from pathlib import Path
from urllib.parse import urlsplit

import pytest
from jinja2 import Environment, FileSystemLoader

ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture
def page():
    if os.environ.get("MARINKINO_UI_BROWSER") != "1":
        pytest.skip("Set MARINKINO_UI_BROWSER=1 to run browser checks")
    playwright = pytest.importorskip("playwright.sync_api")
    with playwright.sync_playwright() as runtime:
        executable = os.environ.get("MARINKINO_BROWSER_EXECUTABLE")
        browser = runtime.chromium.launch(
            headless=True, executable_path=executable or None
        )
        context = browser.new_context(viewport={"width": 390, "height": 844})
        page = context.new_page()
        page.set_default_timeout(5000)
        yield page
        context.close()
        browser.close()


def serve(page, template, api, **variables):
    environment = Environment(
        loader=FileSystemLoader(ROOT / "src/templates"), autoescape=True
    )
    environment.globals.update(
        csrf_token=lambda: "test-token",
        csp_nonce=lambda: "test-nonce",
        url_for=lambda _endpoint, filename: "/static/" + filename,
    )
    html = environment.get_template(template).render(**variables)

    def route(request):
        path = urlsplit(request.request.url).path
        if path == "/":
            request.fulfill(content_type="text/html", body=html)
        elif path.startswith("/static/"):
            request.fulfill(path=str(ROOT / "src" / path.lstrip("/")))
        elif path.startswith("/api/"):
            request.fulfill(
                content_type="application/json",
                body=json.dumps(api(path, request.request)),
            )
        else:
            request.fulfill(status=404, body="")

    page.route("http://localhost:8080/**", route)
    page.goto("http://localhost:8080/")


def test_movie_editor_keeps_fields_and_reports_empty_subtitle_result(page):
    movie = {
        "folder": "Film.A",
        "name": "Film A",
        "videos": ["part.mp4"],
        "subtitles": [],
        "is_collection": False,
        "metadata": {},
    }
    received = []

    def api(path, request):
        if path == "/api/movies/incoming":
            return {"status": "ok", "movies": [movie]}
        if path == "/api/movies/subtitles/download":
            return {"status": "ok", "downloaded": False}
        if path == "/api/movies/process":
            received.append(request.post_data_json)
            return {"status": "ok", "hls": ["Film.A"], "folder": "Film.A"}
        raise AssertionError(path)

    serve(page, "video_editor.html", api)
    page.get_by_role("button", name="Film A").click()
    page.get_by_role("button", name="Naprej", exact=True).click()
    page.get_by_role("button", name="Naprej", exact=True).click()
    page.get_by_label("Naslov *", exact=True).fill("Ročno urejen naslov")
    page.get_by_label("Opis", exact=True).fill("Ročni opis")
    page.get_by_role("button", name="Naprej", exact=True).click()
    page.get_by_role("button", name="Prenesi slovenske in angleške").click()
    page.get_by_text("Ni novih podnapisov.", exact=False).wait_for()
    page.get_by_role("button", name="Nazaj", exact=True).click()
    assert (
        page.get_by_label("Naslov *", exact=True).input_value()
        == "Ročno urejen naslov"
    )
    assert page.get_by_label("Opis", exact=True).input_value() == "Ročni opis"
    page.get_by_role("button", name="Naprej", exact=True).click()
    page.get_by_role("button", name="Naprej", exact=True).click()
    assert page.evaluate("document.documentElement.scrollWidth <= innerWidth")
    page.get_by_role("button", name="Potrdi in pripravi HLS").click()
    page.get_by_role("heading", name="Film pripravljen").wait_for()
    assert received[0]["metadata"]["title"] == "Ročno urejen naslov"
    assert received[0]["metadata"]["plot"] == "Ročni opis"


def test_music_editor_keeps_drafts_across_search_and_save(page):
    tracks = [
        {
            "filename": "Album/Song",
            "title": "Song",
            "artist": "Artist",
            "album": "Album",
            "duration": "1:20",
            "play_path": "Album/Song.mp3",
        }
    ]
    received = []

    def api(path, request):
        assert path == "/api/music/update"
        received.append(request.post_data_json)
        return {
            "status": "ok",
            "metadata": {"title": request.post_data_json["title"]},
        }

    serve(page, "music_editor.html", api, music=tracks)
    page.get_by_role("textbox", name="Naslov: Song", exact=True).fill(
        "Urejen naslov"
    )
    page.get_by_label("Poišči skladbo").fill("brez zadetkov")
    assert page.get_by_text("Ni skladb.", exact=False).is_visible()
    page.get_by_label("Poišči skladbo").fill("")
    assert (
        page.get_by_role(
            "textbox", name="Naslov: Song", exact=True
        ).input_value()
        == "Urejen naslov"
    )
    assert page.evaluate("document.documentElement.scrollWidth <= innerWidth")
    page.get_by_role("button", name="Shrani spremembe", exact=True).click()
    page.get_by_text("Vse spremembe shranjene.", exact=True).wait_for()
    assert received[0]["title"] == "Urejen naslov"
    assert page.get_by_role(
        "button", name="Shrani spremembe", exact=True
    ).is_disabled()

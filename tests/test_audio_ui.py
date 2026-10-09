"""Music and children's radio browser regressions with isolated audio."""

import wave
from io import BytesIO

import pytest
from flask import Response, jsonify, render_template, request
from test_admin_memes_ui import browser as browser_fixture
from test_admin_memes_ui import ui as ui_fixture

ui = ui_fixture
browser = browser_fixture


@pytest.fixture
def audio_site(ui):
    songs = ["first.wav", "second.wav"]
    metadata = {
        "first.wav": dict(
            title="Jutranja melodija",
            artist="Ana",
            album="Za dobro voljo",
            file_path="first.wav",
            duration=30,
        ),
        "second.wav": dict(
            title="Zgodba o lisici",
            artist="Bine",
            album="Za dobro voljo",
            file_path="second.wav",
            duration=30,
        ),
    }
    personal = []
    albums = [
        dict(name="Za dobro voljo", songs=songs),
        dict(name="Prazen album", songs=[]),
        dict(name="Za dobro voljo - Podalbum", songs=[]),
    ]

    @ui.app.route("/music")
    def music():
        return render_template(
            "music_player.html",
            is_music=True,
            albums=personal + albums,
            private_albums=personal,
            max_private_albums=10,
            music_metadata=metadata,
        )

    @ui.app.route("/radio-stories")
    def radio():
        return render_template(
            "radio_stories.html",
            is_music=True,
            radio_stories_files=songs,
            radio_stories_metadata=metadata,
        )

    @ui.app.route("/music/private-albums", methods=["POST"])
    def add_album():
        personal.append(
            dict(
                id="private-one",
                name=request.json["name"],
                is_private=True,
                songs=[],
            )
        )
        return jsonify(albums=personal)

    output = BytesIO()
    with wave.open(output, "wb") as sound:
        sound.setnchannels(1)
        sound.setsampwidth(2)
        sound.setframerate(8000)
        sound.writeframes(b"\x00\x00" * 8000 * 30)

    @ui.app.route("/music/file/<path:name>")
    @ui.app.route("/radio-stories/file/<path:name>")
    def audio_file(name):
        return Response(output.getvalue(), mimetype="audio/wav")

    ui.metadata = metadata
    ui.personal = personal
    return ui


def test_audio_templates(audio_site):
    for path in ["/music", "/radio-stories"]:
        html = audio_site.client.get(path).text
        assert "Kako poslušam?" not in html
        assert 'aria-label="Položaj predvajanja"' in html
        assert "user-scalable=no" not in html


def test_browser_audio_layout_search_keyboard_and_playback(
    audio_site, browser
):
    page = browser.page
    for width in [320, 390, 820, 1440]:
        page.set_viewport_size({"width": width, "height": 844})
        for path in ["/music", "/radio-stories"]:
            page.goto(browser.base + path)
            page.locator(".track-item").first.wait_for(state="attached")
            if path == "/music" and width <= 812:
                page.locator('.toggle-btn[data-target="albums"]').click()
                page.locator(".album-item").first.click()
                assert page.locator("#tracks").is_visible()
            assert page.locator("#player").is_visible()
            if path == "/music":
                sub = page.locator(".album-item-after-separator")
                assert sub.count() == 1
                assert sub.evaluate(
                    "(el) => parseFloat(getComputedStyle(el).marginLeft) > 0"
                )
                assert (
                    page.locator(".music-ambience__wave").first.evaluate(
                        "(el) => getComputedStyle(el).animationName"
                    )
                    != "none"
                )
            else:
                assert (
                    page.locator(".radio-bubbles span").first.evaluate(
                        "(el) => getComputedStyle(el).animationName"
                    )
                    != "none"
                )

            assert page.evaluate(
                "document.documentElement.scrollWidth <= innerWidth + 1"
            )
            page.locator("#searchInput").fill("xxxxxxxxxxx")
            page.wait_for_function(
                'document.querySelector("#trackResultsStatus")'
                '.textContent.includes(": 0")'
            )
            assert page.locator(".audio-empty").is_visible()
            page.get_by_role("button", name="Počisti iskanje").click()
            assert page.locator(".track-item").count() == 2
            assert page.locator("#searchInput").input_value() == ""
            track = page.locator(".track-item").last
            track.focus()
            page.keyboard.press("Enter")
            page.wait_for_function('!document.querySelector("#audio").paused')
            page.wait_for_function(
                'document.querySelector("#playBtn")'
                '.getAttribute("aria-label") === "Premor"'
            )
            assert (
                page.locator("#nowPlayingTitle").inner_text()
                == "Zgodba o lisici"
            )
            assert (
                page.locator("#playBtn").get_attribute("aria-label")
                == "Premor"
            )
            page.get_by_role("button", name="Premor", exact=True).click()
            assert page.locator("#audio").evaluate("(el) => el.paused")
            if path == "/music" and width <= 812:
                page.locator(".audio-private-details summary").click()
                assert page.locator("#privateAlbumEmptyHint").is_visible()
                assert page.locator("#privateAlbumEmptyHint").evaluate(
                    "(el) => el.getBoundingClientRect().bottom <= "
                    'document.querySelector(".music-app-container")'
                    ".getBoundingClientRect().bottom"
                )
                page.locator(".audio-private-details summary").click()
            page.screenshot(
                path=f"/private/tmp/audio-{path[1:]}-{width}.png",
                full_page=True,
            )


def test_browser_personal_album_safe_names_and_empty_state(
    audio_site, browser
):
    page = browser.page
    page.goto(browser.base + "/music")
    page.locator("#managePrivateAlbumsBtn").click()
    page.locator("#newPrivateAlbumName").fill("<img src=x onerror=alert(1)>")
    page.get_by_role("button", name="Dodaj album", exact=True).click()
    page.wait_for_function(
        'document.querySelectorAll(".private-manager-row").length === 1'
    )
    assert audio_site.personal[0]["name"] == "<img src=x onerror=alert(1)>"
    assert page.locator(".album-item img").count() == 0
    page.locator("#privateAlbumsModal .btn-close").click()
    page.locator(".album-item").first.click()
    assert page.locator(".audio-empty").is_visible()
    assert (
        "V tem albumu še ni pesmi" in page.locator(".audio-empty").inner_text()
    )
    assert (
        page.locator("#trackResultsStatus")
        .inner_text()
        .startswith("V zbirki: 0")
    )


def test_browser_playback_errors_and_restricted_storage(audio_site, browser):
    page = browser.page
    page.add_init_script(
        'Storage.prototype.getItem = () => {throw new Error("blocked")};'
        'Storage.prototype.setItem = () => {throw new Error("blocked")};'
    )
    page.goto(browser.base + "/radio-stories")
    page.locator(".track-item").first.wait_for()
    page.evaluate(
        '() => {document.querySelector("#audio").play = () =>'
        'Promise.reject(new DOMException("blocked", "NotAllowedError"));}'
    )
    page.get_by_role("button", name="Predvajaj", exact=True).click()
    page.wait_for_function(
        'document.querySelector("#playbackStatus").dataset.error === "true"'
    )
    assert page.locator("#playBtn").get_attribute("aria-label") == "Predvajaj"
    assert page.locator("#playbackStatus").is_visible()


def test_browser_music_and_radio_restore_separate_tracks(audio_site, browser):
    page = browser.page
    page.goto(browser.base + "/music")
    page.locator('.toggle-btn[data-target="tracks"]').click()
    page.locator(".track-item").last.click()
    page.wait_for_function('localStorage.getItem("track") === "second.wav"')
    page.goto(browser.base + "/radio-stories")
    assert page.locator("#nowPlayingTitle").inner_text() == "Jutranja melodija"
    page.locator(".track-item").first.click()
    page.wait_for_function(
        'localStorage.getItem("radioStories:track") === "first.wav"'
    )
    page.goto(browser.base + "/music")
    assert page.locator("#nowPlayingTitle").inner_text() == "Zgodba o lisici"

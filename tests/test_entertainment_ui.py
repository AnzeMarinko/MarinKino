"""Regression checks for weather failures and the shared-device game flow.

Browser checks run with MARINKINO_UI_BROWSER=1 and an installed Playwright
Chromium. Set PLAYWRIGHT_BROWSERS_PATH when using a temporary browser install.
"""

import importlib.util
import json
import os
import sys
import threading
from datetime import datetime, timedelta, timezone
from pathlib import Path
from types import ModuleType, SimpleNamespace
from unittest.mock import Mock, patch
from urllib.parse import quote

import pytest
from flask import Flask
from flask_login import LoginManager
from werkzeug.serving import make_server

ROOT = Path(__file__).resolve().parents[1]


def weather_payload(is_day=1):
    now = datetime.now().replace(minute=0, second=0, microsecond=0)
    dates = [(now + timedelta(days=i)).date().isoformat() for i in range(10)]
    times = [(now + timedelta(minutes=15 * i)).isoformat() for i in range(960)]
    return {
        "latitude": 46.06, "longitude": 14.51,
        "timezone": "Europe/Ljubljana", "utc_offset_seconds": 7200,
        "current": {
            "time": now.isoformat(), "temperature_2m": 18.5,
            "weather_code": 2, "is_day": is_day, "precipitation": .2,
            "cloud_cover": 40, "wind_speed_10m": 12.5,
        },
        "daily": {
            "time": dates, "weather_code": [2] * 10,
            "temperature_2m_max": [22] * 10,
            "temperature_2m_min": [12] * 10,
            "precipitation_sum": [1] * 10,
            "sunrise": [f"{day}T07:10" for day in dates],
            "sunset": [f"{day}T18:25" for day in dates],
            "moon_phase": [.3] * 10,
        },
        "minutely_15": {
            "time": times, "temperature_2m": [18 + (i % 40) / 10 for i in range(960)],
            "precipitation": [.1] * 960, "wind_speed_10m": [12] * 960,
            "global_tilted_irradiance": [i % 400 for i in range(960)],
            "is_day": [int(7 <= int(time[11:13]) < 19) for time in times],
        },
        "minutely_15_units": {
            "temperature_2m": "°C", "precipitation": "mm",
            "wind_speed_10m": "km/h", "global_tilted_irradiance": "W/m²",
        },
    }


@pytest.fixture
def entertainment():
    utilities = ModuleType("utils")
    for name in ("get_guest_identity", "is_current_admin_view", "safe_path"):
        setattr(utilities, name, Mock())
    utilities.redis_client = Mock()
    utilities.redis_client.incr.return_value = 1
    pandas = ModuleType("pandas")
    pandas.read_csv = Mock()
    pandas.read_csv.return_value.to_dict.return_value = {"data": [["morje", "jezero"]]}
    i18n = ModuleType("blog_i18n")
    i18n.BLOG_LANGUAGES = []
    i18n.messages = i18n.normalize_language = Mock()
    translation = ModuleType("blog_translation")
    translation.translate_url = Mock()
    blog = ModuleType("blueprints.blog_bp")
    blog.public_base_url = Mock()
    spec = importlib.util.spec_from_file_location("entertainment_test_misc", ROOT / "src/blueprints/misc_bp.py")
    module = importlib.util.module_from_spec(spec)
    with patch.dict(sys.modules, {
        "utils": utilities, "pandas": pandas, "blog_i18n": i18n,
        "blog_translation": translation, "blueprints.blog_bp": blog,
    }):
        spec.loader.exec_module(module)
    module.geocode_location = Mock(return_value=[
        {"name": "Ljubljana", "latitude": 46.06, "longitude": 14.51, "country": "Slovenija", "admin1": "Osrednjeslovenska"},
        {"name": "Ljubljana", "latitude": 46.1, "longitude": 14.6, "country": "Slovenija", "admin1": "Drug kraj"},
    ])
    module.fetch_weather_for_location = Mock(side_effect=lambda lat, lon, name: module.build_weather_data(weather_payload(), name))
    module.daily_calendar = Mock(return_value={"saint": None, "holidays": []})
    app = Flask(__name__, template_folder=str(ROOT / "src/templates"), static_folder=str(ROOT / "src/static"))
    app.config.update(TESTING=True, SECRET_KEY="entertainment-tests-only")
    LoginManager(app).user_loader(lambda _id: None)
    app.jinja_env.globals.update(csrf_token=lambda: "", domain="localhost", current_year=2026)
    app.register_blueprint(module.misc_bp)
    return SimpleNamespace(app=app, client=app.test_client(), module=module)


def test_weather_outage_keeps_page_usable(entertainment):
    entertainment.module.fetch_weather_for_location.side_effect = RuntimeError("provider down")
    response = entertainment.client.get("/weather?location=Ljubljana")
    assert response.status_code == 200
    assert "Vremenski podatki trenutno niso dosegljivi" in response.text
    assert 'id="weatherSearchForm"' in response.text
    assert 'id="weather-root"' in response.text


def test_weather_missing_location_explains_fallback(entertainment):
    entertainment.module.geocode_location.return_value = []
    response = entertainment.client.get("/weather?location=Neobstojec")
    assert response.status_code == 200
    assert "ni bilo mogoče najti" in response.text
    entertainment.module.fetch_weather_for_location.assert_called_once_with(46.0569, 14.5058, "Ljubljana")


def test_weather_outage_refresh_preserves_selected_coordinates(entertainment):
    entertainment.module.fetch_weather_for_location.side_effect = RuntimeError("provider down")
    response = entertainment.client.get("/weather?location=Kranj&lat=46.25&lon=14.36")
    assert response.status_code == 200
    assert "lat=46.25" in response.text and "lon=14.36" in response.text
    entertainment.module.geocode_location.assert_not_called()


def test_weather_search_outage_explains_fallback(entertainment):
    entertainment.module.geocode_location.side_effect = RuntimeError("search down")
    response = entertainment.client.get("/weather?location=Kranj")
    assert response.status_code == 200
    assert "Iskanje krajev trenutno ni na voljo" in response.text


@pytest.mark.parametrize("coordinates", ["lat=nan&lon=14", "lat=91&lon=14", "lat=46&lon=181", "lat=46"])
def test_weather_rejects_invalid_coordinates(entertainment, coordinates):
    assert entertainment.client.get(f"/weather?location=Ljubljana&{coordinates}").status_code == 200
    entertainment.module.geocode_location.assert_called_once_with("Ljubljana")


def test_weather_uses_saved_location_without_search(entertainment):
    entertainment.client.set_cookie("marinkino_weather_locations", quote(json.dumps([{"name": "Kranj", "lat": 46.24, "lon": 14.36}])))
    response = entertainment.client.get("/weather")
    assert response.status_code == 200
    entertainment.module.geocode_location.assert_not_called()
    entertainment.module.fetch_weather_for_location.assert_called_once_with(46.24, 14.36, "Kranj")


def test_weather_shows_disambiguation_and_preserves_refresh_location(entertainment):
    response = entertainment.client.get("/weather?location=Ljubljana")
    assert "Več krajev s tem imenom" in response.text
    assert "lat=46.06" in response.text and "lon=14.51" in response.text


@pytest.fixture
def browser_page(entertainment):
    if os.environ.get("MARINKINO_UI_BROWSER") != "1":
        pytest.skip("Set MARINKINO_UI_BROWSER=1 to run browser checks")
    from playwright.sync_api import sync_playwright

    server = make_server("127.0.0.1", 0, entertainment.app)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    errors = []
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch()
        context = browser.new_context(
            viewport={"width": 390, "height": 844},
            timezone_id="America/Los_Angeles",
        )
        page = context.new_page()
        page.on("pageerror", lambda error: errors.append(str(error)))
        page.route("https://openfpcdn.io/**", lambda route: route.fulfill(status=200, body=""))
        page.route("https://meteo.arso.gov.si/**", lambda route: route.abort())
        plotly = os.environ.get("MARINKINO_PLOTLY_PATH")
        page.route("https://cdn.plot.ly/**", lambda route: route.fulfill(path=plotly, content_type="text/javascript") if plotly else route.abort())
        yield SimpleNamespace(page=page, context=context, base=f"http://127.0.0.1:{server.server_port}", errors=errors)
        browser.close()
    server.shutdown()
    thread.join(timeout=5)
    assert not errors, errors


def fill_names(page, amount=5):
    for index in range(amount):
        page.locator(f"#playerName{index}").fill(f"Igralec {index + 1}")


def start_and_reveal(page):
    page.locator("#setupForm [data-start-game]").click()
    page.locator("#revealPanel").wait_for(state="visible")
    seen = {}
    count = page.locator(".pk-name-row").count()
    for index in range(count):
        page.locator("#revealButton").click()
        seen[f"Igralec {index + 1}"] = page.locator("#secretWord").inner_text()
        page.locator("#hideSecretButton").click()
        assert page.locator("#secretWord").inner_text() == ""
    page.locator("#playPanel").wait_for(state="visible")
    return seen


def eliminate(page, name):
    page.locator("#voteButton").click()
    page.get_by_role("button", name=f"Izloči igralca {name}", exact=True).click()
    page.locator("#confirmActionButton").click()
    page.locator("#eliminationDialog").wait_for(state="visible")


def test_game_validation_persistence_and_team_resize(browser_page):
    page = browser_page.page
    page.goto(browser_page.base + "/pod_krinko")
    page.locator("#setupForm [data-start-game]").click()
    assert "Vnesi ime" in page.locator("#gameMessage").inner_text()
    fill_names(page)
    page.locator("#playerName1").fill("igralec 1")
    page.locator("#setupForm [data-start-game]").click()
    assert "Podvojeno" in page.locator("#gameMessage").inner_text()
    page.locator("#playerName1").fill("Igralec 2")
    page.locator("#nWhitesSlider").fill("1")
    page.reload()
    assert page.locator("#playerName1").input_value() == "Igralec 2"
    assert page.locator("#nWhitesSlider").input_value() == "1"
    page.locator('[data-adjust="nPlayersSlider"][data-delta="-1"]').click()
    page.locator('[data-adjust="nPlayersSlider"][data-delta="-1"]').click()
    assert page.locator(".pk-name-row").count() == 3
    start_and_reveal(page)
    assert page.locator(".pk-card").count() == 3
    assert page.locator('[aria-current="step"]').get_attribute("data-step") == "play"
    assert page.evaluate("document.documentElement.scrollWidth <= innerWidth")


def test_game_resident_win_and_scores_survive_reload(browser_page):
    page = browser_page.page
    page.goto(browser_page.base + "/pod_krinko")
    fill_names(page)
    seen = start_and_reveal(page)
    assert page.get_by_role("button", name="Izloči", exact=True).count() == 0
    page.locator("#rulesButton").click()
    page.locator("#rulesDialog [data-close-dialog]").first.click()
    assert page.locator("#playPanel").is_visible()
    spy_word = min(set(seen.values()), key=lambda word: list(seen.values()).count(word))
    spy = next(name for name, word in seen.items() if word == spy_word)
    eliminate(page, spy)
    page.locator("#continueRoundButton").click()
    assert "Prebivalci" in page.locator("#resultsTitle").inner_text()
    assert page.locator(".pk-score-total small").count() == 4
    saved = page.evaluate("JSON.parse(localStorage.getItem('podKrinko_data'))")
    assert sum(p["tocke"] for p in saved["tocke"]) == 8
    assert "words" not in saved
    page.reload()
    fill_names(page)
    start_and_reveal(page)
    page.locator("#scoresButton").click()
    assert "2 tč." in page.locator("#liveScores").inner_text()
    assert "Vohun" not in page.locator("#liveScores").inner_text()


def test_game_white_guess_trimmed_and_case_insensitive(browser_page):
    page = browser_page.page
    page.goto(browser_page.base + "/pod_krinko")
    fill_names(page)
    page.locator("#nWhitesSlider").fill("1")
    seen = start_and_reveal(page)
    white = next(name for name, word in seen.items() if word == "Gospod v belem")
    assert white not in page.locator("#navodilo").inner_text()
    resident_word = max(set(seen.values()), key=lambda word: list(seen.values()).count(word))
    eliminate(page, white)
    page.locator("#ugibanje").fill("  " + resident_word.upper() + "  ")
    page.locator('#guessForm button[type="submit"]').click()
    assert "uganil besedo" in page.locator("#resultsTitle").inner_text()
    assert "+7" in page.locator("#osebe_rezultati").inner_text()


@pytest.mark.parametrize("failure", ["http", "malformed", "rate_limit"])
def test_game_new_word_failure_preserves_current_round(browser_page, failure):
    page = browser_page.page
    page.goto(browser_page.base + "/pod_krinko")
    fill_names(page)
    start_and_reveal(page)
    before = page.locator("#navodilo").inner_text()
    page.route("**/pod_krinko/new_words", lambda route: route.fulfill(status=429 if failure == "rate_limit" else 503 if failure == "http" else 200, json={} if failure == "malformed" else {"error": failure}))
    page.locator("#playPanel [data-start-game]").click()
    page.locator("#confirmActionButton").click()
    page.locator("#gameMessage").wait_for(state="visible")
    assert page.locator("#playPanel").is_visible()
    assert page.locator("#navodilo").inner_text() == before
    assert page.locator(".pk-card").count() == 5
    assert page.locator("#playPanel [data-start-game]").is_enabled()


def test_weather_mobile_controls_and_chart_fallback(browser_page):
    page = browser_page.page
    page.goto(browser_page.base + "/weather")
    assert page.locator(".weather-day:visible").count() == 6
    page.locator(".weather-more-toggle").click()
    assert page.locator(".weather-day:visible").count() == 10
    page.locator(".weather-more-toggle").click()
    assert page.locator(".weather-day:visible").count() == 6
    assert page.locator("#weatherLocationButton").count() == 1
    assert page.locator(".saved-location-remove").count() == 1
    assert page.locator(".saved-location-remove").locator("xpath=..").evaluate("element => element.tagName") == "SPAN"
    page.locator(".saved-location-remove").click()
    assert page.locator(".saved-location").count() == 0
    assert page.evaluate("document.documentElement.scrollWidth <= innerWidth")
    if os.environ.get("MARINKINO_PLOTLY_PATH"):
        page.locator('[data-chart-hours="48"]').wait_for(state="visible")
        page.wait_for_function("!document.querySelector('[data-chart-hours=\"48\"]').disabled")
        page.locator('[data-chart-hours="48"]').click()
        assert page.locator('[data-chart-hours="48"]').get_attribute("aria-pressed") == "true"
        assert page.evaluate("!!document.getElementById('weatherChart').data.length")
        page.locator('[data-chart-hours="all"]').click()
        assert page.locator('[data-chart-hours="all"]').get_attribute("aria-pressed") == "true"
    else:
        assert "Grafa ni bilo mogoče naložiti" in page.locator("#weatherChartStatus").inner_text()


def test_game_opponents_win_when_one_resident_remains(browser_page):
    page = browser_page.page
    page.goto(browser_page.base + "/pod_krinko")
    fill_names(page)
    seen = start_and_reveal(page)
    resident_word = max(set(seen.values()), key=lambda word: list(seen.values()).count(word))
    residents = [name for name, word in seen.items() if word == resident_word]
    for name in residents[:-1]:
        eliminate(page, name)
        page.locator("#continueRoundButton").click()
    assert "Skrivne vloge" in page.locator("#resultsTitle").inner_text()
    assert "+5" in page.locator("#osebe_rezultati").inner_text()
    assert page.locator(".pk-score-total small").count() == 1


def test_game_wrong_white_guess_then_resident_win(browser_page):
    page = browser_page.page
    page.goto(browser_page.base + "/pod_krinko")
    fill_names(page)
    page.locator("#nWhitesSlider").fill("1")
    seen = start_and_reveal(page)
    white = next(name for name, word in seen.items() if word == "Gospod v belem")
    eliminate(page, white)
    page.locator("#ugibanje").fill("napačna beseda")
    page.locator('#guessForm button[type="submit"]').click()
    assert "ni prava" in page.locator("#guessFeedback").inner_text()
    page.locator("#continueRoundButton").click()
    resident_word = max(set(seen.values()), key=lambda word: list(seen.values()).count(word))
    spy = next(name for name, word in seen.items() if word not in {resident_word, "Gospod v belem"})
    eliminate(page, spy)
    page.locator("#continueRoundButton").click()
    assert "Prebivalci" in page.locator("#resultsTitle").inner_text()
    assert page.locator(".pk-score-total small").count() == 3


def test_game_mime_bonus_awarded_once(browser_page):
    page = browser_page.page
    page.goto(browser_page.base + "/pod_krinko")
    page.evaluate("Math.random = () => 0")
    fill_names(page)
    page.locator("#nemec").check()
    seen = start_and_reveal(page)
    mime = "Igralec 1"
    assert mime in page.locator("#mimeNotice").inner_text()
    resident_word = max(set(seen.values()), key=lambda word: list(seen.values()).count(word))
    assert seen[mime] == resident_word
    spy = next(name for name, word in seen.items() if word != resident_word)
    eliminate(page, spy)
    page.locator("#continueRoundButton").click()
    saved = page.evaluate("JSON.parse(localStorage.getItem('podKrinko_data'))")
    assert sum(p["tocke"] for p in saved["tocke"]) == 16
    assert page.locator(".pk-score-total small").count() == 4


def test_game_storage_unavailable_and_malformed_data(browser_page):
    page = browser_page.page
    page.goto(browser_page.base + "/pod_krinko")
    page.evaluate("localStorage.setItem('podKrinko_data', 'invalid-json')")
    page.reload()
    assert page.locator(".pk-name-row").count() == 5
    page.evaluate("() => { Storage.prototype.setItem = () => { throw new Error('blocked'); }; }")
    fill_names(page)
    start_and_reveal(page)
    assert page.locator("#playPanel").is_visible()
    assert "ni na voljo" in page.locator("#storageNote").inner_text()


def test_weather_location_permission_failure_allows_retry(browser_page):
    page = browser_page.page
    page.goto(browser_page.base + "/weather")
    page.evaluate("""() => {
        Object.defineProperty(navigator, 'geolocation', { value: {
            getCurrentPosition: (_success, failure) => failure({ code: 1 })
        } });
    }""")
    page.locator("#weatherLocationButton").click()
    assert "zavrnjen" in page.locator("#weatherLocationMessage").inner_text()
    assert page.locator("#weatherLocationButton").is_enabled()
    assert page.locator("#weatherSearch").is_visible()


def test_weather_missing_graph_keeps_daily_forecast(browser_page):
    page = browser_page.page
    page.route("https://cdn.plot.ly/**", lambda route: route.abort())
    page.goto(browser_page.base + "/weather")
    assert "Grafa ni bilo mogoče naložiti" in page.locator("#weatherChartStatus").inner_text()
    assert page.locator(".weather-day:visible").count() == 6
    assert page.locator("#weatherSearch").is_visible()


def test_weather_clock_and_graph_use_location_timezone(browser_page):
    page = browser_page.page
    page.clock.install(time=datetime(2026, 10, 9, 11, tzinfo=timezone.utc))
    page.goto(browser_page.base + "/weather")
    assert "13:00" in page.locator("#weatherCurrentEpochSeconds").inner_text()
    if os.environ.get("MARINKINO_PLOTLY_PATH"):
        page.wait_for_function("!document.querySelector('[data-chart-hours=\"24\"]').disabled")
        assert "13:00" in page.evaluate("document.getElementById('weatherChart').layout.xaxis.range[0]")

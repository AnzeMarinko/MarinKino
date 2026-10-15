"""Private journal persistence, calculations, access and browser workflows."""

import importlib.util
import os
import sys
import threading
from concurrent.futures import ThreadPoolExecutor
from datetime import date, datetime, timedelta
from pathlib import Path
from types import ModuleType, SimpleNamespace
from unittest.mock import patch

import pytest
from flask import Flask, render_template, session
from flask_login import LoginManager, UserMixin
from flask_wtf.csrf import CSRFProtect
from werkzeug.serving import make_server

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
import fitness  # noqa: E402


@pytest.fixture
def ui(tmp_path, monkeypatch):
    utilities = ModuleType("utils")
    utilities.is_current_admin_view = lambda user: (
        user.is_authenticated
        and user.is_admin
        and session.get("view_as") not in ("user", "anonymous")
    )
    spec = importlib.util.spec_from_file_location(
        "fitness_test_blueprint", ROOT / "src/blueprints/fitness_bp.py"
    )
    module = importlib.util.module_from_spec(spec)
    with patch.dict(sys.modules, {"utils": utilities}):
        spec.loader.exec_module(module)
    app = Flask(
        __name__,
        template_folder=str(ROOT / "src/templates"),
        static_folder=str(ROOT / "src/static"),
    )
    app.config.update(
        TESTING=True,
        SECRET_KEY="fitness-tests",
        ADMIN=True,
        AUTHENTICATED=True,
        USER_ID="admin-one",
        WTF_CSRF_ENABLED=False,
        FITNESS_DATABASE=str(tmp_path / "fitness.sqlite3"),
    )
    monkeypatch.setattr(
        fitness,
        "now_local",
        lambda: datetime(2026, 10, 14, 15, 25, tzinfo=fitness.LOCAL_ZONE),
    )

    class User(UserMixin):
        @property
        def id(self):
            return app.config["USER_ID"]

        @property
        def is_admin(self):
            return app.config["ADMIN"]

    manager = LoginManager(app)
    manager.user_loader(lambda _id: User())

    @app.before_request
    def authenticate():
        if app.config["AUTHENTICATED"]:
            session["_user_id"] = app.config["USER_ID"]
        else:
            session.pop("_user_id", None)

    CSRFProtect(app)
    app.jinja_env.globals.update(domain="localhost", current_year=2026)
    app.add_url_rule("/", "home", lambda: "home")
    app.add_url_rule("/blog/terms", "blog.blog_terms", lambda: "")
    app.add_url_rule("/blog/privacy", "blog.blog_privacy", lambda: "")
    app.register_blueprint(module.fitness_bp)
    return SimpleNamespace(app=app, client=app.test_client(), module=module)


def create(ui, collection, **payload):
    response = ui.client.post(f"/admin/fitness/{collection}", json=payload)
    assert response.status_code == 201, response.text
    return response.json["entry"]


def state(ui):
    response = ui.client.get("/admin/fitness/data")
    assert response.status_code == 200
    return response.json


@pytest.fixture
def gated(ui):
    from fitness_access import init_fitness_access

    ui.app.add_url_rule("/movies", "movies.list", lambda: "movies")
    ui.app.add_url_rule("/music", "music.list", lambda: "music")
    ui.app.add_url_rule("/blog", "blog.index", lambda: "blog")
    ui.app.add_url_rule("/weather", "misc.weather", lambda: "weather")
    ui.app.add_url_rule("/admin", "admin.dashboard", lambda: "admin")
    ui.app.add_url_rule("/admin/blog", "admin.blog", lambda: "admin blog")
    ui.app.add_url_rule(
        "/blog/night-test",
        "blog.night_test",
        lambda: render_template("base.html"),
    )
    ui.app.add_url_rule(
        "/admin/blog/edit/night-test",
        "admin.blog_edit",
        lambda: render_template("base.html"),
    )
    ui.app.add_url_rule(
        "/admin/blog/image-preview",
        "admin.blog_preview",
        lambda: {"ok": True},
        methods=["POST"],
    )
    ui.app.add_url_rule("/page", "page", lambda: render_template("base.html"))
    ui.app.add_url_rule(
        "/movies/file/movie.mp4", "movies.file", lambda: "video"
    )
    ui.app.add_url_rule(
        "/music/rate", "music.rate", lambda: "changed", methods=["POST"]
    )
    for endpoint in ("login", "logout", "change_password"):
        ui.app.add_url_rule(
            f"/auth/{endpoint}", f"auth.{endpoint}", lambda: "auth"
        )
    init_fitness_access(ui.app)
    return ui


def complete_plan(ui, plan, **overrides):
    response = ui.client.post(
        f"/admin/fitness/plan/{plan['id']}/complete",
        json={"timestamp": "2026-10-14T12:00:00", **overrides},
    )
    assert response.status_code in (200, 201), response.text
    return response.json["activity_id"]


def test_recurring_schedule_is_iso_parity_and_idempotent(ui):
    even = create(ui, "schedule", kind="cycling", parity="even", weekday=0)
    odd = create(ui, "schedule", kind="running", parity="odd", weekday=0)
    first = state(ui)
    assert {row["date"] for row in first["plan"]} == {
        "2026-10-12",
        "2026-10-19",
        "2026-10-26",
    }
    assert len(state(ui)["plan"]) == len(first["plan"])
    assert len({row["id"] for row in first["plan"]}) == 3
    future = ui.client.get("/admin/fitness/data?start=2026-12-28").json
    plans = {row["date"]: row for row in future["plan"]}
    assert plans["2026-12-28"]["schedule_id"] == odd["id"]  # ISO 53
    assert plans["2027-01-04"]["schedule_id"] == odd["id"]  # ISO 1
    following = ui.client.get("/admin/fitness/data?start=2027-01-11").json
    assert (
        next(row for row in following["plan"] if row["date"] == "2027-01-11")[
            "schedule_id"
        ]
        == even["id"]
    )
    assert (
        ui.client.get("/admin/fitness/data?start=invalid").status_code == 400
    )


@pytest.mark.parametrize(
    "parity,weekday",
    [
        ("both", 0),
        (True, 0),
        ("odd", None),
        ("even", -1),
        ("even", 7),
        ("odd", 1.2),
        ("odd", False),
    ],
)
def test_recurring_schedule_validation(ui, parity, weekday):
    response = ui.client.post(
        "/admin/fitness/schedule",
        json={
            "kind": "running",
            "parity": parity,
            "weekday": weekday,
        },
    )
    assert response.status_code == 400


def test_recurring_completion_preserves_history_and_future_copies(ui):
    routine = create(
        ui,
        "schedule",
        kind="running",
        parity="even",
        weekday=0,
        title="Umirjeni tek",
        duration_min=30,
    )
    rows = state(ui)["plan"]
    current = next(row for row in rows if row["date"] == "2026-10-12")
    future = next(row for row in rows if row["date"] == "2026-10-26")
    activity_id = complete_plan(ui, current)
    assert complete_plan(ui, current) == activity_id
    assert len(state(ui)["activities"]) == 1
    response = ui.client.put(
        f"/admin/fitness/schedule/{routine['id']}",
        json={
            **routine,
            "title": "Novi tek",
            "duration_seconds": 2400,
        },
    )
    assert response.status_code == 200
    plans = {row["id"]: row for row in state(ui)["plan"]}
    assert plans[current["id"]]["title"] == "Umirjeni tek"
    assert plans[future["id"]]["title"] == "Novi tek"
    assert plans[future["id"]]["duration_seconds"] == 2400
    customized = {
        **plans[future["id"]],
        "description": "Moja trasa",
        "date": "2026-10-27",
    }
    assert (
        ui.client.put(
            f"/admin/fitness/plan/{future['id']}", json=customized
        ).status_code
        == 200
    )
    assert (
        ui.client.put(
            f"/admin/fitness/schedule/{routine['id']}",
            json={
                **routine,
                "title": "Drugi naslov",
            },
        ).status_code
        == 200
    )
    plans = state(ui)["plan"]
    assert len(plans) == 2  # Moved occurrence is not regenerated on Monday.
    changed = next(row for row in plans if row["id"] == future["id"])
    assert changed["date"] == "2026-10-27"
    assert changed["description"] == "Moja trasa"
    assert (
        ui.client.delete(
            f"/admin/fitness/schedule/{routine['id']}"
        ).status_code
        == 204
    )
    remaining = state(ui)
    assert remaining["schedule"] == []
    assert [row["id"] for row in remaining["plan"]] == [current["id"]]
    assert remaining["activities"][0]["id"] == activity_id


def test_recurring_deleted_occurrence_stays_deleted_and_is_private(ui):
    routine = create(ui, "schedule", kind="cardio", parity="even", weekday=2)
    occurrence = state(ui)["plan"][0]
    assert (
        ui.client.delete(f"/admin/fitness/plan/{occurrence['id']}").status_code
        == 204
    )
    assert occurrence["id"] not in {row["id"] for row in state(ui)["plan"]}
    assert occurrence["date"] not in {row["date"] for row in state(ui)["plan"]}
    assert (
        ui.client.post(
            f"/admin/fitness/plan/{occurrence['id']}/complete", json={}
        ).status_code
        == 404
    )
    ui.app.config["USER_ID"] = "admin-two"
    assert state(ui)["schedule"] == []
    assert state(ui)["plan"] == []
    assert (
        ui.client.delete(
            f"/admin/fitness/schedule/{routine['id']}"
        ).status_code
        == 404
    )
    assert (
        ui.client.post(
            f"/admin/fitness/plan/{occurrence['id']}/complete", json={}
        ).status_code
        == 404
    )


def test_access_counts_actual_week_and_last_seven_planned_days(gated):
    ui = gated
    plans = [
        create(ui, "plan", kind="running", date=day)
        for day in (
            "2026-10-07",
            "2026-10-09",
            "2026-10-12",
            "2026-10-13",
            "2026-10-14",
        )
    ]
    complete_plan(ui, plans[1], timestamp="2026-10-11T12:00:00")
    progress = state(ui)["plan_progress"]
    assert not progress["allowed"]
    assert (progress["recent_completed"], progress["recent_total"]) == (1, 4)
    assert {row["date"] for row in progress["due"]} == {
        "2026-10-12",
        "2026-10-13",
        "2026-10-14",
    }
    assert ui.client.get("/movies").status_code == 302
    # A late execution of a previous week's plan also counts this week.
    activity = complete_plan(ui, plans[0])
    assert ui.client.get("/music").status_code == 200
    assert state(ui)["plan_progress"]["week_completed"] == 1
    assert (
        ui.client.delete(f"/admin/fitness/activities/{activity}").status_code
        == 204
    )
    assert ui.client.get("/music").status_code == 302
    complete_plan(ui, plans[2], timestamp="2026-10-13T12:00:00")
    progress = state(ui)["plan_progress"]
    assert progress["allowed"]
    assert (progress["recent_completed"], progress["recent_total"]) == (2, 4)


def test_weighing_reminder_and_lock_date_thresholds():
    today = date(2026, 10, 15)

    def status(last_date):
        return fitness.weighing_status(
            [
                {
                    "timestamp": f"{last_date}T10:00:00+00:00",
                    "weight_kg": 80,
                }
            ],
            today=today,
        )

    assert not status("2026-10-01")["orange"]  # Exactly 14 days.
    assert status("2026-09-30")["orange"]  # More than 14 days.
    assert not status("2026-09-15")["red"]  # Exactly one month.
    assert status("2026-09-14")["red"]
    assert not status("2026-08-15")["locked"]  # Exactly two months.
    assert status("2026-08-14")["locked"]
    assert fitness.weighing_status([], today=today)["reminder"]


def test_stale_weighing_locks_content_until_new_measurement(gated):
    ui = gated
    plan = create(ui, "plan", kind="running", date="2026-10-14")
    complete_plan(ui, plan)
    create(
        ui,
        "measurements",
        timestamp="2026-08-13T12:00",
        weight_kg=80,
    )

    response = ui.client.get("/movies")
    assert response.status_code == 302
    assert "minila več kot dva meseca" in ui.client.get(response.location).text
    assert ui.client.get("/blog").status_code == 302
    assert ui.client.get("/admin/fitness").status_code == 200
    response = ui.client.post("/music/rate", json={})
    assert response.status_code == 423
    assert "meritev teže" in response.json["error"]

    create(
        ui,
        "measurements",
        timestamp="2026-10-14T12:00",
        weight_kg=79.5,
    )
    assert ui.client.get("/movies").status_code == 200


def test_access_rejects_unplanned_workouts_and_blocks_content_mutation(gated):
    ui = gated
    create(ui, "activities", kind="running", duration_min=60)
    create(ui, "plan", kind="running", date="2026-10-14", status="skipped")
    for path in (
        "/",
        "/movies",
        "/music",
        "/blog",
        "/weather",
        "/admin",
        "/admin/blog",
        "/movies/file/movie.mp4",
    ):
        response = ui.client.get(path)
        assert response.status_code == 302
        assert response.location.endswith("/admin/fitness")
        assert response.headers["Cache-Control"] == "private, no-store"
    response = ui.client.post("/music/rate", json={})
    assert response.status_code == 423
    assert response.json["fitness_url"] == "/admin/fitness"
    assert (
        ui.client.get(
            "/movies", headers={"Accept": "application/json"}
        ).status_code
        == 423
    )
    for path in (
        "/admin/fitness",
        "/auth/login",
        "/auth/logout",
        "/auth/change_password",
        "/static/script/admin_fitness.js",
    ):
        assert ui.client.get(path).status_code == 200


def test_redirect_flashes_once_and_fitness_does_not_check_access(gated):
    from fitness_access import access_cache

    ui = gated
    ui.client.get("/weather")
    ui.client.get("/admin/blog")
    with ui.client.session_transaction() as sess:
        assert len(sess["_flashes"]) == 1
        assert sess["_flashes"][0][0] == "warning"
    with ui.app.app_context():
        cache = access_cache()
    with patch.object(
        cache, "get", side_effect=AssertionError("No gate inside fitness")
    ):
        response = ui.client.get("/admin/fitness")
        assert response.status_code == 200
        assert "Ostale vsebine so zaklenjene." in response.text
        for path in ("/admin/fitness", "/admin/fitness/data"):
            response = ui.client.get(path)
            assert response.status_code == 200
            assert "Ostale vsebine so zaklenjene." not in response.text
    with ui.client.session_transaction() as sess:
        assert not sess.get("_flashes")


def test_access_cache_uses_no_database_reads_until_fifteen_minutes(
    gated, monkeypatch
):
    import fitness_access

    clock = [100.0]
    monkeypatch.setattr(fitness_access, "monotonic", lambda: clock[0])
    with patch.object(
        fitness_access, "read_state", wraps=fitness.read_state
    ) as read:
        assert gated.client.get("/movies").status_code == 302
        for path in ("/music", "/blog", "/movies/file/movie.mp4", "/"):
            assert gated.client.get(path).status_code == 302
        assert read.call_count == 1
        clock[0] = 999.0
        assert gated.client.get("/movies").status_code == 302
        assert read.call_count == 1
        clock[0] = 1000.0
        assert gated.client.get("/movies").status_code == 302
        assert read.call_count == 2


def test_access_cache_checks_once_for_concurrent_visits(gated):
    import fitness_access

    def check(_index):
        with gated.app.app_context():
            return fitness_access.access_cache().get("admin-one")["allowed"]

    with patch.object(
        fitness_access, "read_state", wraps=fitness.read_state
    ) as read:
        with ThreadPoolExecutor(max_workers=8) as workers:
            assert list(workers.map(check, range(16))) == [False] * 16
        assert read.call_count == 1


@pytest.mark.parametrize(
    "hour,minute,locked",
    [
        (0, 0, True),
        (3, 0, True),
        (5, 59, True),
        (6, 0, False),
        (23, 49, False),
        (23, 50, False),
    ],
)
def test_night_lock_boundaries_override_completed_fitness(
    gated, monkeypatch, hour, minute, locked
):
    ui = gated
    plan = create(ui, "plan", kind="running", date="2026-10-14")
    complete_plan(ui, plan)
    assert ui.client.get("/movies").status_code == 200
    ui.client.set_cookie("marinkino_device_timezone", "Europe%2FLjubljana")
    monkeypatch.setattr(
        fitness,
        "now_local",
        lambda: datetime(
            2026, 10, 15, hour, minute, tzinfo=fitness.LOCAL_ZONE
        ),
    )
    response = ui.client.get("/weather")
    assert response.status_code == (302 if locked else 200)
    if locked:
        assert response.location == "/admin/fitness"
        assert "Nočni počitek" in ui.client.get(response.location).text


def test_night_lock_uses_device_zone_without_fitness_database(gated):
    from fitness_access import access_cache

    ui = gated
    ui.client.set_cookie("marinkino_device_timezone", "Pacific%2FKiritimati")
    # Fixture time is 15:25 in Ljubljana, 03:25 on this device.
    with ui.app.app_context():
        cache = access_cache()
    with patch.object(
        cache, "get", side_effect=AssertionError("No journal at night")
    ):
        assert ui.client.get("/movies").status_code == 302
        response = ui.client.post("/music/rate", json={})
        assert response.status_code == 423
        assert "Nočni počitek" in response.json["error"]
        assert ui.client.get("/admin/fitness").status_code == 200
    ui.app.config["ADMIN"] = False
    assert ui.client.get("/movies").status_code == 200


@pytest.mark.parametrize("zone", ["", "invalid/timezone", "../etc/passwd"])
def test_unknown_device_zone_keeps_fitness_condition(gated, zone):
    gated.client.set_cookie("marinkino_device_timezone", zone)
    response = gated.client.get("/movies")
    assert response.status_code == 302
    assert (
        "Ta teden najprej opravi" in gated.client.get(response.location).text
    )


def test_night_redirect_clears_preview_and_flashes_once(gated):
    ui = gated
    with ui.client.session_transaction() as sess:
        sess["view_as"] = "anonymous"
    for _ in range(2):
        response = ui.client.get("/admin/fitness/night-lock")
        assert response.status_code == 302
        assert response.location == "/admin/fitness"
    with ui.client.session_transaction() as sess:
        assert "view_as" not in sess
        assert len(sess["_flashes"]) == 1
    assert "Nočni počitek" in ui.client.get("/admin/fitness").text
    assert "Nočni počitek" not in ui.client.get("/admin/fitness").text


def test_blog_night_exception_keeps_activity_condition(gated, monkeypatch):
    ui = gated
    ui.client.set_cookie("marinkino_device_timezone", "Europe%2FLjubljana")
    monkeypatch.setattr(
        fitness,
        "now_local",
        lambda: datetime(2026, 10, 15, 2, 0, tzinfo=fitness.LOCAL_ZONE),
    )
    assert ui.client.get("/blog/night-test").status_code == 302
    plan = create(ui, "plan", kind="running", date="2026-10-14")
    complete_plan(ui, plan)
    for path in (
        "/blog",
        "/blog/night-test",
        "/admin/blog",
        "/admin/blog/edit/night-test",
    ):
        assert ui.client.get(path).status_code == 200
    assert (
        ui.client.post("/admin/blog/image-preview", json={}).status_code == 200
    )
    for path in ("/movies", "/music", "/weather", "/admin"):
        assert ui.client.get(path).status_code == 302


def test_browser_blog_stays_open_across_midnight(gated, browser, monkeypatch):
    from playwright.sync_api import expect

    plan = create(gated, "plan", kind="running", date="2026-10-14")
    complete_plan(gated, plan)
    clock = [datetime(2026, 10, 14, 23, 49, tzinfo=fitness.LOCAL_ZONE)]
    monkeypatch.setattr(fitness, "now_local", lambda: clock[0])
    page = browser.page
    page.clock.install(time=clock[0])
    page.goto(browser.base + "/admin/blog/edit/night-test")
    page.clock.run_for(60000)
    expect(page.locator("#admin-night-warning")).to_have_count(0)
    clock[0] = datetime(2026, 10, 15, 0, 1, tzinfo=fitness.LOCAL_ZONE)
    page.clock.run_for(660000)
    expect(page).to_have_url(browser.base + "/admin/blog/edit/night-test")
    page.reload()
    expect(page).to_have_url(browser.base + "/admin/blog/edit/night-test")
    page.goto(browser.base + "/blog/night-test")
    expect(page).to_have_url(browser.base + "/blog/night-test")
    expect(page.locator("#flash-container")).not_to_contain_text(
        "Nočni počitek"
    )
    page.goto(browser.base + "/music")
    expect(page).to_have_url(browser.base + "/admin/fitness")


def test_browser_night_warning_redirect_and_six_am_unlock(
    gated, browser, monkeypatch
):
    from playwright.sync_api import expect

    ui, page = gated, browser.page
    plan = create(ui, "plan", kind="running", date="2026-10-14")
    complete_plan(ui, plan)
    clock = [datetime(2026, 10, 14, 23, 49, 50, tzinfo=fitness.LOCAL_ZONE)]
    monkeypatch.setattr(fitness, "now_local", lambda: clock[0])
    page.clock.install(time=clock[0])
    page.goto(browser.base + "/page")
    expect(page).to_have_url(browser.base + "/page")
    expect(page.locator("#admin-night-warning")).to_have_count(0)
    cookies = {row["name"]: row["value"] for row in page.context.cookies()}
    assert cookies["marinkino_device_timezone"] == "Europe%2FLjubljana"
    page.clock.run_for(10000)
    expect(page.locator("#admin-night-warning")).to_contain_text("čez 10 min")
    clock[0] = datetime(2026, 10, 15, 0, 0, tzinfo=fitness.LOCAL_ZONE)
    page.clock.run_for(600000)
    expect(page).to_have_url(browser.base + "/admin/fitness")
    expect(page.locator("#flash-container")).to_contain_text("Nočni počitek")
    expect(page.locator("#admin-night-warning")).to_have_count(0)
    page.reload()
    expect(page.locator("#flash-container")).not_to_contain_text(
        "Nočni počitek"
    )
    clock[0] = datetime(2026, 10, 15, 6, 0, tzinfo=fitness.LOCAL_ZONE)
    page.clock.set_system_time(clock[0])
    page.goto(browser.base + "/page")
    expect(page).to_have_url(browser.base + "/page")
    expect(page.locator("#admin-night-warning")).to_have_count(0)


def test_browser_first_visit_at_night_and_resume_from_sleep(gated, browser):
    from playwright.sync_api import expect

    plan = create(gated, "plan", kind="cardio", date="2026-10-14")
    complete_plan(gated, plan)
    page = browser.page
    # No timezone cookie yet: the head script blocks the first night visit.
    page.clock.set_fixed_time(
        datetime(2026, 10, 14, 2, 0, tzinfo=fitness.LOCAL_ZONE)
    )
    page.goto(browser.base + "/page")
    expect(page).to_have_url(browser.base + "/admin/fitness")
    expect(page.locator("#flash-container")).to_contain_text("Nočni počitek")
    page.clock.set_fixed_time(
        datetime(2026, 10, 14, 15, 25, tzinfo=fitness.LOCAL_ZONE)
    )
    page.goto(browser.base + "/page")
    expect(page).to_have_url(browser.base + "/page")
    page.clock.set_fixed_time(
        datetime(2026, 10, 15, 2, 0, tzinfo=fitness.LOCAL_ZONE)
    )
    page.evaluate("window.dispatchEvent(new Event('focus'))")
    expect(page).to_have_url(browser.base + "/admin/fitness")


def test_access_progress_appears_on_other_pages(gated):
    plan = create(gated, "plan", kind="running", date="2026-10-12")
    complete_plan(gated, plan, timestamp="2026-10-13T12:00:00")
    response = gated.client.get("/page")
    assert response.status_code == 200
    assert 'id="site-fitness-progress"' in response.text
    assert "1 / 1 opravljenih" in response.text
    assert "Izvedbe iz plana ta teden: 1" in response.text


def test_access_cache_unlocks_immediately_and_resets_on_monday(
    gated, monkeypatch
):
    import fitness_access

    ui = gated
    plan = create(ui, "plan", kind="cycling", date="2026-10-14")
    with patch.object(
        fitness_access, "read_state", wraps=fitness.read_state
    ) as read:
        assert ui.client.get("/movies").status_code == 302
        assert read.call_count == 1
        complete_plan(ui, plan)
        assert ui.client.get("/movies").status_code == 200
        for _ in range(4):
            assert ui.client.get("/music").status_code == 200
        assert read.call_count == 2
        monkeypatch.setattr(
            fitness,
            "now_local",
            lambda: datetime(2026, 10, 19, 0, 1, tzinfo=fitness.LOCAL_ZONE),
        )
        assert ui.client.get("/movies").status_code == 302
        assert read.call_count == 3


def test_access_is_per_admin_and_view_as_cannot_bypass(gated):
    ui = gated
    plan = create(ui, "plan", kind="strength", date="2026-10-14")
    complete_plan(ui, plan)
    assert ui.client.get("/movies").status_code == 200
    ui.app.config["USER_ID"] = "admin-two"
    assert ui.client.get("/movies").status_code == 302
    with ui.client.session_transaction() as sess:
        sess["view_as"] = "anonymous"
    assert ui.client.get("/movies", follow_redirects=True).status_code == 200
    with ui.client.session_transaction() as sess:
        assert "view_as" not in sess
    ui.app.config["USER_ID"] = "admin-one"
    assert ui.client.get("/movies").status_code == 200
    ui.app.config["ADMIN"] = False
    ui.app.config["USER_ID"] = "member"
    assert ui.client.get("/movies").status_code == 200
    ui.app.config["AUTHENTICATED"] = False
    assert ui.client.get("/blog").status_code == 200


def test_browser_two_week_cycle_and_access_completion(gated, browser):
    from playwright.sync_api import expect

    page = browser.page
    page.goto(browser.base + "/music")
    expect(page).to_have_url(browser.base + "/admin/fitness")
    expect(page.locator("#flash-container")).to_contain_text(
        "Ostale vsebine so zaklenjene."
    )
    page.locator("[data-open-plan]").click()
    expect(page.locator("#fitness-cycle-library button")).to_have_count(8)
    for index in range(8):
        page.locator("#fitness-cycle-library button").nth(index).click()
        page.locator("#session-repeat").select_option(
            "even" if index < 4 else "odd"
        )
        page.locator("#session-weekday").select_option(str(index % 4))
        page.get_by_role("button", name="Shrani v plan", exact=True).click()
        expect(page.locator("#fitness-session-dialog")).not_to_be_visible()
        expect(
            page.locator('#fitness-cycle-plan [data-edit="schedule"]')
        ).to_have_count(index + 1)
    expect(page.locator("#fitness-plan > section")).to_have_count(2)
    even = page.locator('#fitness-cycle-plan [data-parity="even"]')
    odd = page.locator('#fitness-cycle-plan [data-parity="odd"]')
    expect(even.locator('[data-edit="schedule"]')).to_have_count(4)
    expect(odd.locator('[data-edit="schedule"]')).to_have_count(4)
    expect(page.locator("#fitness-access-title")).to_have_text(
        "Načrti in izvedbe"
    )
    expect(page.locator("[data-complete-due]")).to_have_count(3)
    page.locator("[data-complete-due]").first.click()
    expect(page.locator("#session-date")).to_have_value("2026-10-14")
    page.locator("#session-date").fill("2026-10-14")
    page.locator("#session-time").fill("12:00")
    page.get_by_role("button", name="Shrani izvedbo", exact=True).click()
    expect(page.locator("#fitness-access-title")).to_have_text(
        "Načrti in izvedbe"
    )
    expect(page.locator("#fitness-plan-progress")).to_contain_text(
        "1 / 3 opravljenih"
    )
    page.goto(browser.base + "/music")
    expect(page).to_have_url(browser.base + "/music")
    assert page.locator("body").inner_text() == "music"


def test_optional_measurements_and_chronological_persistence(ui):
    empty = create(ui, "measurements")
    assert empty["timestamp"] == "2026-10-14T13:25:00+00:00"
    assert all(
        empty[key] is None
        for key in (
            "weight_kg",
            "waist_cm",
            "fasting",
            "morning",
            "after_bowel",
        )
    )
    older = create(
        ui,
        "measurements",
        timestamp="2025-02-01T12:00:00",
        weight_kg="85,5",
        fasting=False,
        morning=True,
    )
    assert older["timestamp"] == "2025-02-01T11:00:00+00:00"
    assert older["weight_kg"] == 85.5
    assert older["fasting"] is False and older["after_bowel"] is None
    assert state(ui)["measurements"][0]["id"] == older["id"]
    # A separate client reads committed data from the same database.
    client = ui.app.test_client()
    assert len(client.get("/admin/fitness/data").json["measurements"]) == 2
    response = ui.client.put(
        f"/admin/fitness/measurements/{older['id']}",
        json={"timestamp": older["timestamp"], "waist_cm": 90},
    )
    assert response.status_code == 200
    assert response.json["entry"]["weight_kg"] is None


def test_height_indices_use_same_measurement_and_preserve_gaps(ui):
    create(ui, "measurements", weight_kg=80)
    create(ui, "measurements", waist_cm=90)
    assert state(ui)["measurements"][0]["bmi"] is None
    assert (
        ui.client.put(
            "/admin/fitness/profile",
            json={
                "height_cm": 180,
                "aerobic_goal": 150,
                "strength_goal": 2,
            },
        ).status_code
        == 200
    )
    rows = state(ui)["measurements"]
    assert rows[0]["bmi"] == pytest.approx(80 / 1.8**2)
    assert rows[0]["waist_height_ratio"] is None
    assert rows[1]["bmi"] is None and rows[1]["waist_height_ratio"] == 0.5
    assert ui.client.put("/admin/fitness/profile", json={}).status_code == 200
    assert state(ui)["measurements"][0]["bmi"] is None


def test_weekly_totals_distinguish_aerobic_strength_and_missing_values(ui):
    timestamp = "2026-10-12T12:00:00"
    for kind, minutes, intensity in [
        ("cycling", 30, "moderate"),
        ("running", 20, "vigorous"),
        ("cardio", 10, "light"),
        ("strength", 40, "vigorous"),
        ("strength", 10, "moderate"),
        ("cycling", 15, None),
        ("running", None, "vigorous"),
    ]:
        create(
            ui,
            "activities",
            kind=kind,
            duration_min=minutes,
            intensity=intensity,
            timestamp=timestamp,
        )
    create(ui, "activities", kind="strength", timestamp="2026-10-13T12:00")
    create(
        ui,
        "activities",
        kind="cycling",
        duration_min=99,
        intensity="moderate",
        timestamp="2026-10-11T23:30:00",
    )
    create(
        ui,
        "plan",
        kind="running",
        duration_min=200,
        intensity="vigorous",
        date="2026-10-14",
    )
    week = state(ui)["current_week"]
    assert week["aerobic_equivalent"] == 70
    assert week["minutes"] == 125
    assert week["strength_days"] == 1
    assert week["recorded_strength_days"] == 2
    assert week["unknown_strength_intensity"] == 1
    assert week["missing_duration"] == 2 and week["unknown_intensity"] == 1
    assert state(ui)["weekly"][-2]["minutes"] == 99
    assert len(state(ui)["weekly"]) == 12


def test_template_snapshot_and_idempotent_completion(ui):
    template = state(ui)["templates"][0]
    plan = create(ui, "plan", **{**template, "date": "2026-10-15"})
    assert (
        ui.client.put(
            f"/admin/fitness/templates/{template['id']}",
            json={**template, "title": "Spremenjena predloga"},
        ).status_code
        == 200
    )
    assert state(ui)["plan"][0]["title"] == template["title"]
    path = f"/admin/fitness/plan/{plan['id']}/complete"
    response = ui.client.post(
        path,
        json={
            "timestamp": "2026-10-14T10:00",
            "duration_min": 45,
        },
    )
    assert response.status_code == 201
    activity_id = response.json["activity_id"]
    assert ui.client.post(path, json={}).json["activity_id"] == activity_id
    journal = state(ui)
    assert len(journal["activities"]) == 1
    assert journal["activities"][0]["duration_min"] == 45
    assert journal["plan"][0]["status"] == "completed"
    assert (
        ui.client.delete(
            f"/admin/fitness/activities/{activity_id}"
        ).status_code
        == 204
    )
    assert state(ui)["plan"][0]["status"] == "planned"


@pytest.mark.parametrize(
    "collection,payload",
    [
        ("measurements", {"weight_kg": "nan"}),
        ("measurements", {"weight_kg": "inf"}),
        ("measurements", {"weight_kg": True}),
        ("measurements", {"waist_cm": -1}),
        ("measurements", {"fasting": "false"}),
        ("measurements", {"timestamp": "2026-10-16T12:00"}),
        ("measurements", {"timestamp": "not-a-date"}),
        ("activities", {"kind": "unknown"}),
        ("activities", {"kind": []}),
        ("activities", {"kind": "running", "duration_min": 0}),
        (
            "templates",
            {"kind": "cardio", "tutorial_url": "javascript:alert(1)"},
        ),
        ("templates", {"kind": "cardio", "tutorial_url": "https://[broken"}),
        ("plan", {"kind": "strength", "date": "2026-02-30"}),
        (
            "plan",
            {"kind": "strength", "date": "2026-10-15", "status": "completed"},
        ),
    ],
)
def test_reject_invalid_input_without_mutation(ui, collection, payload):
    before = state(ui)[collection]
    response = ui.client.post(f"/admin/fitness/{collection}", json=payload)
    assert response.status_code == 400 and response.json["error"]
    assert state(ui)[collection] == before


def test_profile_rejects_fractional_strength_goal(ui):
    assert (
        ui.client.put(
            "/admin/fitness/profile",
            json={
                "strength_goal": 1.5,
            },
        ).status_code
        == 400
    )


def test_private_access_and_cross_account_record_isolation(ui):
    record = create(ui, "measurements", weight_kg=80)
    response = ui.client.get("/admin/fitness/data")
    assert response.headers["Cache-Control"] == "private, no-store"
    assert response.headers["X-Robots-Tag"] == "noindex, nofollow"
    ui.app.config["USER_ID"] = "admin-two"
    assert state(ui)["measurements"] == []
    path = f"/admin/fitness/measurements/{record['id']}"
    assert ui.client.delete(path).status_code == 404
    assert ui.client.put(path, json={}).status_code == 404
    ui.app.config["ADMIN"] = False
    assert ui.client.get("/admin/fitness").status_code == 302
    assert ui.client.get("/admin/fitness/data").status_code == 403
    assert (
        ui.client.post("/admin/fitness/measurements", json={}).status_code
        == 403
    )
    ui.app.config["ADMIN"] = True
    with ui.client.session_transaction() as cookie:
        cookie["view_as"] = "user"
    assert ui.client.get("/admin/fitness/data").status_code == 403
    ui.app.config["AUTHENTICATED"] = False
    assert ui.client.get("/admin/fitness/data").status_code == 401


def test_csrf_and_page_rendering(ui):
    response = ui.client.get("/admin/fitness")
    assert response.status_code == 200
    assert 'href="/admin/fitness" aria-current=page' in response.text
    assert "fitness-data" in response.text
    ui.app.config["WTF_CSRF_ENABLED"] = True
    assert (
        ui.client.post("/admin/fitness/measurements", json={}).status_code
        == 400
    )


def test_expired_api_session_does_not_redirect_to_login_html(ui):
    ui.app.add_url_rule("/login", "login", lambda: "login form")
    ui.app.login_manager.login_view = "login"
    ui.app.config["AUTHENTICATED"] = False
    assert ui.client.get("/admin/fitness").status_code == 302
    assert ui.client.get("/admin/fitness/data").status_code == 401
    response = ui.client.post("/admin/fitness/measurements", json={})
    assert response.status_code == 401
    assert "Location" not in response.headers


def test_database_rollback_and_private_file_permissions(ui):
    path = ui.app.config["FITNESS_DATABASE"]
    state(ui)
    with pytest.raises(RuntimeError):
        with fitness.database(path) as connection:
            fitness.insert(connection, "admin-one", "measurements", {})
            raise RuntimeError("rollback")
    assert state(ui)["measurements"] == []
    assert Path(path).stat().st_mode & 0o777 == 0o600


def test_body_targets_are_optional_private_and_can_be_cleared(ui):
    response = ui.client.put(
        "/admin/fitness/profile",
        json={
            "height_cm": 180,
            "target_weight_kg": "75,5",
            "target_waist_cm": 85,
            "aerobic_goal": 150,
            "strength_goal": 2,
        },
    )
    assert response.status_code == 200
    assert state(ui)["profile"]["target_weight_kg"] == 75.5
    assert state(ui)["profile"]["target_waist_cm"] == 85
    ui.app.config["USER_ID"] = "admin-two"
    assert state(ui)["profile"]["target_weight_kg"] is None
    ui.app.config["USER_ID"] = "admin-one"
    assert (
        ui.client.put(
            "/admin/fitness/profile",
            json={
                "target_weight_kg": "",
                "target_waist_cm": None,
            },
        ).status_code
        == 200
    )
    assert state(ui)["profile"]["target_weight_kg"] is None


@pytest.mark.parametrize(
    "field,value",
    [
        ("target_weight_kg", -1),
        ("target_waist_cm", "nan"),
        ("target_weight_kg", True),
        ("target_waist_cm", 401),
    ],
)
def test_invalid_body_target_does_not_replace_profile(ui, field, value):
    before = state(ui)["profile"]
    assert (
        ui.client.put(
            "/admin/fitness/profile",
            json={
                field: value,
            },
        ).status_code
        == 400
    )
    assert state(ui)["profile"] == before


@pytest.mark.parametrize(
    "elapsed,seconds",
    [
        ("27:30", 1650),
        ("1:05:30", 3930),
        ("0:01", 1),
        ("24:00:00", 86400),
    ],
)
def test_exact_elapsed_time_and_running_pace(ui, elapsed, seconds):
    entry = create(
        ui, "activities", kind="running", distance_km=5, elapsed_time=elapsed
    )
    assert entry["duration_seconds"] == seconds
    assert entry["duration_min"] == seconds / 60
    saved = state(ui)["activities"][0]
    assert saved["pace_seconds_per_km"] == seconds / 5
    assert saved["average_speed_kmh"] == pytest.approx(5 * 3600 / seconds)
    edited = ui.client.put(
        f"/admin/fitness/activities/{entry['id']}",
        json={
            "kind": "cycling",
            "distance_km": 25,
            "elapsed_time": "1:05:30",
            "cadence_rpm": 88,
        },
    )
    assert edited.status_code == 200
    assert state(ui)["activities"][0]["average_speed_kmh"] == pytest.approx(
        25 * 3600 / 3930
    )


@pytest.mark.parametrize(
    "payload",
    [
        {"elapsed_time": "27:60"},
        {"elapsed_time": "1:60:00"},
        {"elapsed_time": "0:00"},
        {"elapsed_time": "25:00:00"},
        {"elapsed_time": "bad"},
        {"duration_seconds": 1.5},
        {"duration_seconds": True},
        {"training_style": "unknown"},
        {"equipment": []},
        {"cadence_rpm": 0},
        {"advice": 42},
    ],
)
def test_invalid_workout_fields_reject_without_mutation(ui, payload):
    response = ui.client.post(
        "/admin/fitness/activities",
        json={
            "kind": "cycling",
            **payload,
        },
    )
    assert response.status_code == 400
    assert state(ui)["activities"] == []


def test_distance_statistics_preserve_missing_values_and_pair_time(ui):
    for distance, elapsed in [
        (5, "25:00"),
        (10, "1:00:00"),
        (2, ""),
        (None, "20:00"),
        (0, "5:00"),
    ]:
        create(
            ui,
            "activities",
            kind="running",
            distance_km=distance,
            elapsed_time=elapsed,
        )
    week = state(ui)["current_week"]
    assert week["distance_by_kind"]["running"] == 17
    assert week["missing_distance_by_kind"]["running"] == 1
    assert week["timed_distance_by_kind"]["running"] == 15
    assert week["timed_seconds_by_kind"]["running"] == 85 * 60
    assert week["seconds_by_kind"]["running"] == 110 * 60
    rows = state(ui)["activities"]
    assert rows[2]["pace_seconds_per_km"] is None
    assert rows[3]["average_speed_kmh"] is None
    assert rows[4]["pace_seconds_per_km"] is None


def test_existing_profile_and_decimal_minutes_load_without_overwrite(ui):
    state(ui)
    with fitness.database(ui.app.config["FITNESS_DATABASE"]) as connection:
        connection.execute(
            "UPDATE fitness_profiles SET payload = ? WHERE user_id = ?",
            (
                '{"height_cm":185,"aerobic_goal":180,"strength_goal":3}',
                "admin-one",
            ),
        )
        fitness.insert(
            connection,
            "admin-one",
            "activities",
            {
                "kind": "running",
                "title": "Star zapis",
                "duration_min": 27.5,
                "distance_km": 5,
                "intensity": None,
                "timestamp": "2026-10-14T10:00:00+00:00",
                "description": "Ohranjeno",
                "tutorial_url": "",
            },
        )
    journal = state(ui)
    assert journal["profile"]["height_cm"] == 185
    assert journal["profile"]["target_weight_kg"] is None
    assert journal["activities"][0]["duration_seconds"] == 1650
    assert journal["activities"][0]["pace_seconds_per_km"] == 330
    assert journal["activities"][0]["description"] == "Ohranjeno"


def test_suggested_workout_copy_preserves_form_advice_and_actual_overrides(ui):
    suggestion = next(
        row
        for row in state(ui)["suggestions"]
        if row["id"] == "cycling-cadence"
    )
    template = create(ui, "templates", **suggestion)
    plan = create(ui, "plan", **{**template, "date": "2026-10-14"})
    for key in ("training_style", "cadence_rpm", "advice", "description"):
        assert plan[key] == suggestion[key]
    assert (
        ui.client.put(
            f"/admin/fitness/templates/{template['id']}",
            json={**template, "advice": "Spremenjeno"},
        ).status_code
        == 200
    )
    assert state(ui)["plan"][0]["advice"] == suggestion["advice"]
    assert (
        ui.client.post(
            f"/admin/fitness/plan/{plan['id']}/complete",
            json={
                "elapsed_time": "40:15",
                "distance_km": 20,
                "cadence_rpm": 89,
            },
        ).status_code
        == 201
    )
    activity = state(ui)["activities"][0]
    assert activity["duration_seconds"] == 2415
    assert activity["duration_min"] == 40.25
    assert activity["cadence_rpm"] == 89
    assert activity["advice"] == suggestion["advice"]


@pytest.fixture
def browser(ui):
    if os.environ.get("MARINKINO_UI_BROWSER") != "1":
        pytest.skip("Opt-in browser checks")
    from playwright.sync_api import sync_playwright

    server = make_server("127.0.0.1", 0, ui.app)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    errors = []
    with sync_playwright() as playwright:
        chromium = playwright.chromium.launch()
        page = chromium.new_page(
            viewport={"width": 390, "height": 844},
            timezone_id="Europe/Ljubljana",
        )
        page.clock.set_fixed_time(fitness.now_local())
        page.set_default_timeout(7000)
        page.on("pageerror", lambda error: errors.append(str(error)))
        page.route("https://**", lambda route: route.abort())
        page.route(
            "**/static/script/fingerprint.js",
            lambda route: route.fulfill(body=""),
        )
        yield SimpleNamespace(
            page=page, base=f"http://127.0.0.1:{server.server_port}"
        )
        chromium.close()
    server.shutdown()
    thread.join(timeout=5)
    assert not errors, errors


def test_browser_measurements_graphs_and_mobile_layout(ui, browser):
    page = browser.page
    page.goto(browser.base + "/admin/fitness")
    page.get_by_role("button", name="Nova meritev", exact=True).click()
    today = page.locator("#measurement-date").input_value()
    assert page.locator("#measurement-time").input_value() != ""
    past = (
        (datetime.fromisoformat(today) - timedelta(days=10)).date().isoformat()
    )
    page.locator("#measurement-date").fill(past)
    page.locator("#measurement-date").dispatch_event("change")
    assert page.locator("#measurement-time").input_value() == "12:00"
    page.locator("#measurement-weight").fill("80")
    page.locator("#measurement-standard").check()
    page.get_by_role("button", name="Shrani meritev", exact=True).click()
    page.locator("#fitness-measurement-dialog").wait_for(state="hidden")
    assert state(ui)["measurements"][0]["after_bowel"] is True
    page.get_by_role("tab", name="Predloge in nastavitve").click()
    page.locator("#fitness-height").fill("180")
    page.get_by_role("button", name="Shrani nastavitve").click()
    page.get_by_role("tab", name="Pregled", exact=True).click()
    page.locator("#chart-bmi svg").wait_for()
    page.locator("#fitness-comparable").check()
    assert page.locator("#chart-weight circle").count() == 1
    for width in [320, 390, 820, 1440]:
        page.set_viewport_size({"width": width, "height": 900})
        for tab in [
            "Pregled",
            "Meritve",
            "Dnevnik aktivnosti",
            "Tedenski plan",
            "Predloge in nastavitve",
        ]:
            page.get_by_role("tab", name=tab, exact=True).click()
            assert page.evaluate(
                "document.documentElement.scrollWidth <= innerWidth + 1"
            ), (width, tab)
        page.get_by_role("tab", name="Pregled", exact=True).click()
        if width in [390, 1440]:
            page.evaluate("window.scrollTo(0, 0)")
            page.screenshot(
                path=f"/private/tmp/fitness-{width}.png", full_page=True
            )
    page.reload()
    assert page.locator("#chart-weight circle").count() == 1


def test_browser_template_plan_completion_and_failure_recovery(ui, browser):
    page = browser.page
    page.goto(browser.base + "/admin/fitness")
    page.get_by_role("tab", name="Predloge in nastavitve").click()
    page.locator("[data-use-template]").first.click()
    title = page.locator("#session-name").input_value()
    page.locator("#plan-date").fill("2026-10-14")
    page.locator("#session-description").fill(
        "Moj opis <script>bad()</script>"
    )
    page.locator("#session-tutorial").fill("https://example.com/tutorial")
    page.get_by_role("button", name="Shrani v plan").click()
    page.locator("#fitness-session-dialog").wait_for(state="hidden")
    page.get_by_role("tab", name="Tedenski plan").click()
    page.locator("[data-complete]").click()
    page.locator("#session-date").fill("2026-10-14")
    page.locator("#session-time").fill("12:00")
    page.locator("#session-duration").fill("45")
    page.get_by_role("button", name="Shrani izvedbo").click()
    page.locator("#fitness-session-dialog").wait_for(state="hidden")
    assert state(ui)["plan"][0]["status"] == "completed"
    completed_card = page.locator(
        "#fitness-plan .fitness-card.is-completed"
    ).filter(has_text=title)
    assert completed_card.locator("button").count() == 0
    assert state(ui)["activities"][0]["duration_min"] == 45
    page.get_by_role("tab", name="Dnevnik aktivnosti").click()
    assert page.get_by_role("heading", name=title, exact=True).is_visible()
    assert page.locator("#fitness-activities script").count() == 0
    page.locator("#fitness-activities [data-edit]").click()
    page.locator("#session-description").fill("Ohranjen osnutek")
    page.route(
        "**/admin/fitness/activities/*",
        lambda route: route.fulfill(
            status=503,
            content_type="application/json",
            body='{"error":"Testna napaka"}',
        ),
    )
    page.get_by_role("button", name="Shrani aktivnost", exact=True).click()
    page.get_by_text("Testna napaka", exact=True).wait_for()
    assert (
        page.locator("#session-description").input_value()
        == "Ohranjen osnutek"
    )
    page.unroute("**/admin/fitness/activities/*")
    page.get_by_role("button", name="Shrani aktivnost", exact=True).click()
    page.locator("#fitness-session-dialog").wait_for(state="hidden")
    assert state(ui)["activities"][0]["description"] == "Ohranjen osnutek"


def test_browser_custom_template_nullable_fields_plan_edit_and_delete(
    ui, browser
):
    page = browser.page
    page.goto(browser.base + "/admin/fitness")
    page.get_by_role("tab", name="Predloge in nastavitve").click()
    page.get_by_role("button", name="Nova predloga", exact=True).click()
    page.locator("#session-kind").select_option("strength")
    page.locator("#session-name").fill("Moje vaje")
    page.locator("#session-description").fill("Opis in serije")
    page.get_by_role("button", name="Shrani predlogo", exact=True).click()
    page.locator("#fitness-session-dialog").wait_for(state="hidden")
    template = next(
        row for row in state(ui)["templates"] if row["title"] == "Moje vaje"
    )
    assert template["duration_min"] is None and template["intensity"] is None
    page.locator(f'[data-use-template="{template["id"]}"]').click()
    page.locator("#plan-date").fill("2026-10-19")
    page.locator("#session-description").fill("Prilagojen opis")
    page.get_by_role("button", name="Shrani v plan", exact=True).click()
    page.locator("#fitness-session-dialog").wait_for(state="hidden")
    assert page.locator("#tab-plan").get_attribute("aria-selected") == "true"
    page.locator("#fitness-plan [data-edit]").click()
    page.locator("#session-status").select_option("skipped")
    page.get_by_role("button", name="Shrani v plan", exact=True).click()
    page.locator("#fitness-session-dialog").wait_for(state="hidden")
    assert state(ui)["plan"][0]["status"] == "skipped"
    assert (
        next(
            row
            for row in state(ui)["templates"]
            if row["id"] == template["id"]
        )["description"]
        == "Opis in serije"
    )
    page.locator("#fitness-plan [data-delete]").click()
    page.get_by_role("button", name="Prekliči", exact=True).click()
    assert len(state(ui)["plan"]) == 1
    page.locator("#fitness-plan [data-delete]").click()
    page.get_by_role("button", name="Izbriši zapis", exact=True).click()
    page.locator("#fitness-delete-dialog").wait_for(state="hidden")
    assert state(ui)["plan"] == []


def test_browser_graphs_with_data_and_unknown_conditions(ui, browser):
    ui.client.put(
        "/admin/fitness/profile",
        json={
            "height_cm": 180,
            "target_weight_kg": 70,
            "target_waist_cm": 80,
        },
    )
    for index in range(4):
        standard = index in (0, 2)
        create(
            ui,
            "measurements",
            timestamp=f"2026-10-{10 + index}T12:00",
            weight_kg=80 + index,
            waist_cm=90 + index,
            fasting=True if standard else None,
            morning=True if standard else False,
            after_bowel=True if standard else None,
        )
    create(
        ui, "activities", kind="running", duration_min=30, intensity="vigorous"
    )
    page = browser.page
    page.goto(browser.base + "/admin/fitness")
    assert page.locator("#chart-weight circle").count() == 4
    assert page.locator("#chart-ratio circle").count() == 4
    assert page.locator("#chart-weight polyline").count() == 2
    comparable_curve = page.locator("#chart-weight .fitness-chart-comparable")
    assert comparable_curve.count() == 1
    assert len(comparable_curve.get_attribute("points").split()) == 2
    assert page.locator("#chart-activity rect").count() == 1
    assert page.locator("#fitness-summary .fitness-info").count() == 2
    assert page.locator("#fitness-insights").count() == 0
    assert page.locator(".fitness-wellbeing").is_visible()
    assert "Cilj: 21,6" in page.locator("#fitness-summary").text_content()
    assert "Cilj: 0,444" in page.locator("#fitness-summary").text_content()
    bmi_info = page.locator("#fitness-info-bmi")
    assert bmi_info.evaluate(
        "(element) => getComputedStyle(element).display"
    ) == "none"
    page.locator(".fitness-info").first.hover()
    assert bmi_info.is_visible()
    assert "referenčni razpon" in bmi_info.text_content()
    page.locator("#fitness-comparable").check()
    assert page.locator("#chart-weight circle").count() == 2
    assert page.locator("#chart-weight .fitness-chart-comparable").count() == 0
    point = page.locator("#chart-weight .fitness-chart-point").first
    point.click()
    tooltip = page.locator("#chart-weight .fitness-chart-tooltip")
    assert tooltip.get_attribute("visibility") == "visible"
    assert "80" in tooltip.text_content()
    page.get_by_role("tab", name="Meritve", exact=True).click()
    page.locator("#fitness-measurements [data-edit]").first.click()
    assert page.locator("#measurement-morning").input_value() == "false"
    assert page.locator("#measurement-fasting").input_value() == ""
    page.locator("#measurement-weight").fill("")
    page.locator("#measurement-waist").fill("")
    page.get_by_role("button", name="Shrani meritev", exact=True).click()
    page.locator("#fitness-measurement-dialog").wait_for(state="hidden")
    assert state(ui)["measurements"][-1]["weight_kg"] is None
    assert state(ui)["measurements"][-1]["morning"] is False


def test_browser_reminds_to_weigh_after_a_week(ui, browser):
    create(
        ui,
        "measurements",
        timestamp="2026-10-06T08:00",
        weight_kg=80,
    )
    page = browser.page
    page.goto(browser.base + "/admin/fitness")
    reminder = page.locator("#fitness-weigh-reminder")
    assert reminder.is_visible()
    assert "8 dni" in reminder.text_content()

    create(
        ui,
        "measurements",
        timestamp="2026-10-14T08:00",
        weight_kg=79.5,
    )
    page.locator("#fitness-refresh").click()
    assert reminder.is_hidden()


def test_browser_targets_workout_suggestions_and_precise_running_time(
    ui, browser
):
    create(ui, "measurements", weight_kg=80, waist_cm=90)
    page = browser.page
    page.goto(browser.base + "/admin/fitness")
    page.get_by_role("button", name="Cilja in višina", exact=True).click()
    page.locator("#fitness-target-weight").fill("75")
    page.locator("#fitness-target-waist").fill("85")
    page.get_by_role("button", name="Shrani nastavitve").click()
    page.wait_for_function(
        "document.querySelector('#fitness-summary').textContent"
        ".includes('Cilj: 75')"
    )
    page.get_by_role("tab", name="Pregled", exact=True).click()
    assert page.locator("#chart-weight .fitness-chart-guide").count() == 1
    assert page.locator("#chart-waist .fitness-chart-guide").count() == 1
    page.get_by_role("tab", name="Predloge in nastavitve").click()
    page.locator("#fitness-suggestion-kind").select_option("cycling")
    assert page.locator("#fitness-suggestions .fitness-card").count() == 2
    page.locator('[data-use-suggestion="cycling-cadence"]').click()
    assert page.locator("#session-style").input_value() == "intervals"
    assert page.locator("#session-cadence").input_value() == "95"
    assert "tedensko" in page.locator("#session-advice").input_value()
    page.get_by_role("button", name="Shrani v plan", exact=True).click()
    page.locator("#fitness-session-dialog").wait_for(state="hidden")
    page.get_by_role("button", name="Zabeleži aktivnost", exact=True).click()
    page.locator("#session-kind").select_option("running")
    page.locator("#session-distance").fill("5")
    page.locator("#session-elapsed").fill("27:30")
    assert page.locator("#session-duration").input_value() == "27.5"
    assert "5:30 min/km" in page.locator("#session-performance").text_content()
    page.get_by_role("button", name="Shrani aktivnost", exact=True).click()
    page.locator("#fitness-session-dialog").wait_for(state="hidden")
    page.get_by_role("tab", name="Dnevnik aktivnosti").click()
    page.locator("#fitness-activities .fitness-card").wait_for()
    assert "5:30 min/km" in page.locator("#fitness-activities").text_content()
    assert "27:30" in page.locator("#fitness-distance-summary").text_content()
    page.locator("#fitness-activities [data-edit]").click()
    assert page.locator("#session-elapsed").input_value() == "27:30"
    page.locator("#session-duration").fill("28")
    assert page.locator("#session-elapsed").input_value() == "28:00"
    page.get_by_role("button", name="Shrani aktivnost", exact=True).click()
    page.locator("#fitness-session-dialog").wait_for(state="hidden")
    assert state(ui)["activities"][0]["duration_seconds"] == 1680
    page.reload()
    assert state(ui)["profile"]["target_weight_kg"] == 75
    page.get_by_role("tab", name="Dnevnik aktivnosti").click()
    page.locator("#fitness-activities [data-edit]").click()
    page.locator("#session-distance").fill("1")
    page.locator("#session-elapsed").fill("1:00:00")
    assert (
        "60:00 min/km" in page.locator("#session-performance").text_content()
    )
    page.get_by_role("button", name="Prekliči", exact=True).click()


def test_browser_distance_totals_and_precise_cycling(ui, browser):
    for distance, elapsed in [
        (5, "25:00"),
        (10, "1:00:00"),
        (2, ""),
        (None, "20:00"),
    ]:
        create(
            ui,
            "activities",
            kind="running",
            distance_km=distance,
            elapsed_time=elapsed,
        )
    page = browser.page
    page.goto(browser.base + "/admin/fitness")
    page.get_by_role("tab", name="Dnevnik aktivnosti").click()
    summary = page.locator("#fitness-distance-summary").text_content()
    assert "17 km" in summary
    assert "1:45:00" in summary
    assert "5:40 min/km" in summary
    page.get_by_role("button", name="Zabeleži aktivnost", exact=True).click()
    page.locator("#session-kind").select_option("cycling")
    page.locator("#session-distance").fill("30")
    page.locator("#session-elapsed").fill("1:02:30")
    page.locator("#session-cadence").fill("88")
    assert "28,8 km/h" in page.locator("#session-performance").text_content()
    page.get_by_role("button", name="Shrani aktivnost", exact=True).click()
    page.locator("#fitness-session-dialog").wait_for(state="hidden")
    page.wait_for_function(
        "document.querySelector('#fitness-distance-summary').textContent"
        ".includes('28,8 km/h')"
    )
    assert "1:02:30" in page.locator("#fitness-activities").text_content()
    assert "88 obr./min" in page.locator("#fitness-activities").text_content()
    page.locator("#fitness-distance-period").select_option("all")
    assert "17 km" in page.locator("#fitness-distance-summary").text_content()
    for width in [320, 1440]:
        page.set_viewport_size({"width": width, "height": 900})
        assert page.evaluate(
            "document.documentElement.scrollWidth <= innerWidth + 1"
        )
        page.locator("#fitness-distance-summary").screenshot(
            path=f"/private/tmp/fitness-distance-{width}.png"
        )
    page.get_by_role("tab", name="Predloge in nastavitve").click()
    page.locator("#fitness-suggestion-kind").select_option("strength")
    page.locator("#fitness-suggestions").screenshot(
        path="/private/tmp/fitness-workout-suggestions.png"
    )

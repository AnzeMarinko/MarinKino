"""Admin UX regressions. Browser checks: MARINKINO_UI_BROWSER=1."""

import ast
import base64
import importlib.util
import json
import logging
import os
import re
import sys
import threading
from datetime import datetime
from pathlib import Path
from types import ModuleType, SimpleNamespace
from unittest.mock import Mock, patch

import pytest
from flask import Flask, jsonify, render_template, request, session
from flask_login import LoginManager, UserMixin
from werkzeug.serving import make_server

ROOT = Path(__file__).resolve().parents[1]
# Valid PNG, used only in the temporary meme directory.
PNG = bytes.fromhex(
    "89504e470d0a1a0a0000000d4948445200000001000000010804000000b51c0c020000000b4944415478da6364f80f00010501012718e3660000000049454e44ae426082"
)


@pytest.fixture
def ui(tmp_path):
    utilities = ModuleType("utils")
    utilities.FLASK_ENV = "development"
    utilities.get_guest_identity = lambda: "test-guest"
    utilities.is_current_admin_view = (
        lambda user: user.is_authenticated and user.is_admin
    )
    utilities.redis_client = Mock()
    utilities.redis_client.incr.return_value = 10001

    def safe_path(root, name):
        path = Path(root).resolve() / name
        if path.resolve().parent != Path(root).resolve():
            raise ValueError("invalid path")
        return str(path)

    utilities.safe_path = safe_path
    spec = importlib.util.spec_from_file_location(
        "ui_test_memes", ROOT / "src/blueprints/memes_bp.py"
    )
    module = importlib.util.module_from_spec(spec)
    with patch.dict(sys.modules, {"utils": utilities}):
        spec.loader.exec_module(module)
    module.MEMES_DIR = str(tmp_path)
    for name in ("first.png", "second.png"):
        (tmp_path / name).write_bytes(PNG)
    app = Flask(
        __name__,
        template_folder=str(ROOT / "src/templates"),
        static_folder=str(ROOT / "src/static"),
    )
    app.config.update(
        TESTING=True,
        SECRET_KEY="admin-ui-tests",
        ADMIN=True,
        AUTHENTICATED=True,
    )

    class User(UserMixin):
        id = "test-admin"

        @property
        def is_admin(self):
            return app.config["ADMIN"]

    manager = LoginManager(app)
    manager.user_loader(lambda _id: User())

    @app.before_request
    def authenticate():
        if app.config["AUTHENTICATED"]:
            session["_user_id"] = User.id
        else:
            session.pop("_user_id", None)

    app.jinja_env.globals.update(
        csrf_token=lambda: "test-csrf", domain="localhost", current_year=2026
    )
    app.add_url_rule("/blog/terms", "blog.blog_terms", lambda: "")
    app.add_url_rule("/blog/privacy", "blog.blog_privacy", lambda: "")
    app.register_blueprint(module.memes_bp)
    posts = [
        dict(
            id="one",
            title="Prva objava",
            published=True,
            views=12,
            created_at="2026-01-01",
            created_at_formatted="01.01.2026",
        ),
        dict(
            id="two",
            title="Druga objava",
            published=False,
            views=3,
            created_at="2026-02-01",
            created_at_formatted="01.02.2026",
        ),
    ]
    saves, mails = [], []

    @app.route("/admin")
    def dashboard():
        return render_template(
            "admin.html",
            users_count=2,
            blog_stats=[],
            total_blog_views=0,
            total_si_views=0,
            users=["Ana", "Bine"],
            users_stats={
                "Ana": {"Skupen čas": "2h 00m"},
                "Bine": {"Skupen čas": "1h 30m"},
            },
            users_stats_columns=["Skupen čas"],
            access_stats_users={
                "200": {"2026-09-01": {"Ana": {"count": 2, "routes": "/"}}}
            },
            access_stats_monthly={"2026-08": {"/": 2}, "2026-09": {"/new": 3}},
            blog_views_daily={"2026-09-01": 5},
            blog_si_views_daily={},
            geo_stats_cities={},
            geo_stats={},
            referrer_stats={},
            emails="",
            system_log="Test",
        )

    @app.route("/admin/blog")
    def blog():
        return render_template("admin_blog.html", posts=posts)

    @app.route("/admin/blog/new", methods=["GET", "POST"])
    @app.route("/admin/blog/edit/<post_id>", methods=["GET", "POST"])
    def editor(post_id=None):
        if request.method == "POST":
            saves.append(dict(path=request.path, **request.form))
            return jsonify(success=True, post_id="saved")
        return render_template("admin_blog_edit.html", post=None)

    @app.route("/admin/register")
    def register():
        return render_template("register.html")

    @app.route("/admin/send_emails", methods=["GET", "POST"])
    def mail():
        if request.method == "POST":
            mails.append(request.json)
            return jsonify(error="simulated mail failure")
        return render_template(
            "admin_mailing.html",
            recipients=[{"name": "Ana", "emails": ["ana@example.test"]}],
        )

    @app.route("/movies/get-comments")
    def comments():
        return jsonify(
            comments=[
                dict(
                    author="<img src=x onerror=alert(1)>",
                    email="user@example.test",
                    text="<script>bad()</script>",
                    date="",
                    movie_folder="Splošno",
                    movie_title="Splošno",
                    comment_index="1",
                    admin_response=None,
                )
            ]
        )

    @app.route("/movies/admin-comment", methods=["POST"])
    def answer():
        return jsonify(status="error"), 503

    return SimpleNamespace(
        app=app,
        client=app.test_client(),
        module=module,
        files=tmp_path,
        saves=saves,
        mails=mails,
    )


def test_admin_templates_render(ui):
    for path in [
        "/admin",
        "/admin/blog",
        "/admin/blog/new",
        "/admin/register",
        "/admin/send_emails",
        "/memes",
    ]:
        response = ui.client.get(path)
        assert response.status_code == 200, path
        assert "csrf-token" in response.text


def test_admin_counter_wraps_and_collection_refreshes(ui):
    response = ui.client.get("/memes?format=json")
    assert response.status_code == 200
    first = response.json["meme_file_name"]
    assert ui.client.delete("/memes/delete/" + first).status_code == 204
    assert first not in ui.module.available_memes()
    assert ui.client.get("/memes?format=json").json["meme_file_name"] != first
    (ui.files / "new.MP4").write_bytes(b"test")
    assert "new.MP4" in ui.module.available_memes()
    assert (
        ui.client.get("/memes?format=json&previous=second.png").json["total"]
        == 2
    )


def test_meme_quota_and_history_requests(ui):
    ui.app.config["ADMIN"] = False
    for remaining in range(11, -1, -1):
        response = ui.client.get("/memes?format=json")
        assert response.status_code == 200
        assert response.json["remaining"] == remaining
    assert ui.client.get("/memes?format=json").status_code == 429
    assert ui.client.delete("/memes/delete/first.png").status_code == 403
    assert (ui.files / "first.png").exists()


def test_empty_meme_collection_does_not_consume_quota(ui):
    for path in ui.files.iterdir():
        path.unlink()
    assert ui.client.get("/memes?format=json").json["empty"] is True
    assert ui.client.get("/memes").status_code == 200
    assert not ui.module.user_meme_count


def test_comments_include_answers_and_accept_missing_dates(tmp_path):
    # Compile only this real view to avoid loading production movie data.
    tree = ast.parse((ROOT / "src/blueprints/movies_bp.py").read_text())
    view = next(
        node
        for node in tree.body
        if isinstance(node, ast.FunctionDef) and node.name == "get_comments"
    )
    view.decorator_list = []
    namespace = dict(
        os=os,
        json=json,
        FILMS_ROOT=str(tmp_path),
        log=logging.getLogger(__name__),
        current_user=object(),
        is_current_admin_view=lambda user: True,
        all_films={
            "/film": {
                "title": "Film",
                "user_notes": {
                    "1": {"text": "Vprašanje", "admin_response": "Odgovor"}
                },
            }
        },
    )
    exec(
        compile(
            ast.Module(body=[view], type_ignores=[]), "get_comments", "exec"
        ),
        namespace,
    )
    (tmp_path / "users_comments.json").write_text('{"user_notes": []}')
    data, status = namespace["get_comments"]()
    assert status == 200
    assert data["comments"][0]["admin_response"] == "Odgovor"
    assert data["comments"][0]["date"] == ""


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
        page = chromium.new_page(viewport={"width": 390, "height": 844})
        page.set_default_timeout(7000)
        page.on("pageerror", lambda error: errors.append(str(error)))
        # Offline fallbacks; admin actions use fake routes.
        page.route(re.compile(r"^https://"), lambda route: route.abort())
        page.route(
            "**/static/script/fingerprint.js",
            lambda route: route.fulfill(body=""),
        )
        page.on("dialog", lambda dialog: dialog.dismiss())
        yield SimpleNamespace(
            page=page, base=f"http://127.0.0.1:{server.server_port}", ui=ui
        )
        chromium.close()
    server.shutdown()
    thread.join(timeout=5)
    assert not errors, errors


def test_browser_admin_filters_comments_and_mobile_layout(browser):
    page = browser.page
    page.goto(browser.base + "/admin")
    page.locator(".admin-comment").wait_for()
    assert (
        page.locator(".admin-comment img, .admin-comment script").count() == 0
    )
    reply = page.locator(".admin-comment textarea")
    reply.fill("Ohranjen osnutek odgovora")
    page.locator("#commentFilter").select_option("answered")
    page.locator("#commentFilter").select_option("unanswered")
    assert reply.input_value() == "Ohranjen osnutek odgovora"
    page.locator(".admin-comment button").click()
    page.get_by_text(
        "Odgovora ni bilo mogoče poslati.", exact=False
    ).wait_for()
    assert reply.input_value() == "Ohranjen osnutek odgovora"
    page.locator("#views-table th").nth(1).click()
    assert (
        page.locator("#views-table tbody tr")
        .first.inner_text()
        .startswith("Bine")
    )
    for width in [320, 390, 1440]:
        page.set_viewport_size({"width": width, "height": 900})
        for path in [
            "/admin",
            "/admin/blog",
            "/admin/register",
            "/admin/send_emails",
            "/admin/blog/new",
            "/memes",
        ]:
            page.goto(browser.base + path)
            assert page.evaluate(
                "document.documentElement.scrollWidth <= innerWidth + 1"
            ), (width, path)
            if width in (390, 1440):
                filename = path.strip("/").replace("/", "-")
                page.screenshot(
                    path=f"/private/tmp/admin-ui-{width}-{filename}.png",
                    full_page=True,
                )
    page.goto(browser.base + "/admin/blog")
    page.locator("#postStatus").select_option("draft")
    assert page.locator("#blogPostsTable tbody tr:visible").count() == 1
    page.locator("[data-table-search]").fill("ni take objave")
    assert page.locator("[data-table-empty]").is_visible()


def test_browser_editor_reuses_saved_post_and_preserves_failed_edits(browser):
    page = browser.page
    page.goto(browser.base + "/admin/blog/new")
    page.locator("#title").fill("Nov naslov")
    image = page.evaluate(
        """() => { const canvas = document.createElement('canvas');
        canvas.width = 600; canvas.height = 400;
        const ctx = canvas.getContext('2d'); ctx.fillStyle = '#29757b';
        ctx.fillRect(0, 0, 600, 400);
        return canvas.toDataURL().split(',')[1]; }"""
    )
    page.locator("#image_file").set_input_files(
        {
            "name": "crop.png",
            "mimeType": "image/png",
            "buffer": base64.b64decode(image),
        }
    )
    page.wait_for_function(
        'Number(document.querySelector("#crop_w").value) > 0'
    )
    box = page.locator("#crop-box")
    box.scroll_into_view_if_needed()
    bounds = box.bounding_box()
    original = float(page.locator("#crop_x").input_value())
    page.mouse.move(
        bounds["x"] + bounds["width"] / 2, bounds["y"] + bounds["height"] / 2
    )
    page.mouse.down()
    page.mouse.move(
        bounds["x"] + bounds["width"] / 2 - 15,
        bounds["y"] + bounds["height"] / 2,
        steps=5,
    )
    page.mouse.up()
    assert float(page.locator("#crop_x").input_value()) < original
    ratio = page.evaluate(
        '() => { const box = document.querySelector("#crop-box");'
        "return parseFloat(box.style.width) / parseFloat(box.style.height); }"
    )
    assert ratio == pytest.approx(1.2)

    page.locator("#content-editor").fill("Markdown vsebina")
    page.locator("#content-editor").press("Control+s")
    page.wait_for_url("**/admin/blog/edit/saved")
    assert browser.ui.saves[0]["content"] == "Markdown vsebina"
    page.locator("#title").fill("Spremenjen naslov")
    page.locator("#blogEditorForm button[type=submit]").click()
    page.get_by_text("Vse spremembe shranjene.", exact=True).wait_for()
    assert browser.ui.saves[-1]["path"] == "/admin/blog/edit/saved"
    page.route(
        "**/admin/blog/edit/saved",
        lambda route: route.fulfill(status=500, json={"message": "Napaka"}),
    )
    page.locator("#content-editor").fill("Ne izgubi besedila")
    page.locator("#blogEditorForm button[type=submit]").click()
    page.get_by_text("Napaka pri shranjevanju:", exact=False).wait_for()
    assert (
        page.locator("#content-editor").input_value() == "Ne izgubi besedila"
    )


def test_browser_mail_confirmation_and_error(browser):
    page = browser.page
    page.goto(browser.base + "/admin/send_emails")
    page.locator('[data-send-mail="true"]').click()
    page.locator("#cancelMail").click()
    assert browser.ui.mails == []
    page.locator('[data-send-mail="false"]').click()
    page.locator("#confirmMail").click()
    page.get_by_text(
        "Pošiljanja ni bilo mogoče potrditi.", exact=False
    ).wait_for()
    assert browser.ui.mails == [{"whole_list": "false"}]


def test_browser_meme_history_and_delete(browser):
    page = browser.page
    page.goto(browser.base + "/memes")
    first = page.locator("#memeMedia img").get_attribute("src")
    page.locator("#nextButton").click()
    page.wait_for_function(
        '(first) => document.querySelector("#memeMedia img")'
        '?.getAttribute("src") !== first',
        arg=first,
    )
    opened = browser.ui.module.user_meme_count["test-admin"]["count"]
    page.locator("#previousMeme").click()
    assert page.locator("#memeMedia img").get_attribute("src") == first
    page.locator("#nextButton").click()
    assert browser.ui.module.user_meme_count["test-admin"]["count"] == opened
    page.locator("#deleteMemeButton").click()
    page.locator("#cancelDeleteMeme").click()
    assert len(browser.ui.module.available_memes()) == 2
    page.locator("#deleteMemeButton").click()
    page.locator("#confirmDeleteMeme").click()
    page.get_by_text("Šala odstranjena iz zbirke.", exact=True).wait_for()
    assert len(browser.ui.module.available_memes()) == 1
    page.route(
        "**/memes?*",
        lambda route: route.fulfill(status=503, json={"error": "offline"}),
    )
    retained = page.locator("#memeMedia img").get_attribute("src")
    page.locator("#nextButton").click()
    page.get_by_text("Nove šale ni mogoče naložiti.", exact=False).wait_for()
    assert page.locator("#memeMedia img").get_attribute("src") == retained


def test_browser_real_markdown_editor_sync(browser):
    asset = Path("/private/tmp/marinkino-simplemde.min.js")
    if not asset.exists():
        pytest.skip("Optional local SimpleMDE asset unavailable")
    page = browser.page
    page.route(
        "https://cdn.jsdelivr.net/simplemde/latest/simplemde.min.js",
        lambda route: route.fulfill(
            path=str(asset), content_type="text/javascript"
        ),
    )
    page.goto(browser.base + "/admin/blog/new")
    page.wait_for_function(
        '!!document.querySelector(".CodeMirror")?.CodeMirror'
    )
    page.locator("#title").fill("CodeMirror naslov")
    page.evaluate(
        'document.querySelector(".CodeMirror").CodeMirror'
        '.setValue("Dejanska Markdown vsebina")'
    )
    page.locator("#blogEditorForm button[type=submit]").click()
    page.wait_for_url("**/admin/blog/edit/saved")
    assert browser.ui.saves[0]["content"] == "Dejanska Markdown vsebina"


def test_browser_meme_quota_retains_history(browser):
    browser.ui.app.config["ADMIN"] = False
    page = browser.page
    page.goto(browser.base + "/memes")
    for remaining in range(10, -1, -1):
        page.locator("#nextButton").click()
        page.wait_for_function(
            '(n) => document.querySelector("#memeProgress").textContent'
            ".includes(`še ${n} šal`)",
            arg=remaining,
        )
    assert page.locator("#nextButton").is_disabled()
    page.locator("#previousMeme").click()
    assert page.locator("#nextButton").is_enabled()
    page.locator("#nextButton").click()
    assert page.locator("#nextButton").is_disabled()
    assert browser.ui.module.user_meme_count["test-admin"]["count"] == 12


def test_browser_real_dashboard_charts(browser):
    asset = Path("/private/tmp/marinkino-plotly.min.js")
    if not asset.exists():
        pytest.skip("Optional local Plotly asset unavailable")
    page = browser.page
    page.route(
        "https://cdn.plot.ly/**",
        lambda route: route.fulfill(
            path=str(asset), content_type="text/javascript"
        ),
    )
    page.goto(browser.base + "/admin")
    page.locator("#access-monthly-graph .main-svg").first.wait_for()
    page.locator("#access-user-graph .main-svg").first.wait_for()
    page.locator("#blog-views-graph .main-svg").first.wait_for()
    values = page.locator("#access-monthly-graph").evaluate(
        "(node) => node.data.map(trace => trace.y)"
    )
    assert values == [[2, 0], [0, 3]]


def test_mail_recipient_count_excludes_users_without_email(ui):
    tree = ast.parse((ROOT / "src/blueprints/misc_bp.py").read_text())
    view = next(
        node
        for node in tree.body
        if isinstance(node, ast.FunctionDef)
        and node.name == "send_admin_emails"
    )
    view.decorator_list = []
    send = Mock(return_value={})
    namespace = dict(
        json=json,
        datetime=datetime,
        request=request,
        current_user=SimpleNamespace(id="admin"),
        send_mail=send,
        users={"admin": {"emails": ["admin@example.test"]}, "no-email": {}},
        is_current_admin_view=lambda user: True,
        WWW_DOMAIN="example.test",
        render_template=lambda *args, **kwargs: "test mail",
    )
    exec(
        compile(
            ast.Module(body=[view], type_ignores=[]),
            "send_admin_emails",
            "exec",
        ),
        namespace,
    )
    with ui.app.test_request_context(
        "/admin/send_emails", method="POST", json={"whole_list": "true"}
    ):
        result = namespace["send_admin_emails"]()
    assert result["sent"] == 1
    assert result["emails"] == ["admin"]
    send.assert_called_once()

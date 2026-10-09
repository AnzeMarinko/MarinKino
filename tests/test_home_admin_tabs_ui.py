"""Home, admin tab placement, log access and chart regressions."""

import ast
from collections import deque
from pathlib import Path

import pytest
from flask import redirect, render_template, url_for
from flask_login import current_user, login_required
from test_admin_memes_ui import browser as browser_fixture
from test_admin_memes_ui import ui as ui_fixture

ui = ui_fixture
browser = browser_fixture
ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture
def sections(ui):
    app = ui.app
    stats = dict(
        movies_count=42,
        movies_duration=105,
        cartoons_count=12,
        cartoons_duration=25,
        music_count=360,
        memes_count=120,
        blog_count=8,
    )
    app.add_url_rule(
        "/",
        "home",
        lambda: render_template("index.html", pagetitle="MarinKino", **stats),
    )
    log_path = ui.files / "system.log"
    log_path.write_text("".join(f"LOG-{index:03}\n" for index in range(300)))
    namespace = dict(
        deque=deque,
        LOG_FILENAME=str(log_path),
        current_user=current_user,
        redirect=redirect,
        url_for=url_for,
        render_template=render_template,
        is_current_admin_view=lambda user: user.is_authenticated
        and user.is_admin,
    )
    tree = ast.parse((ROOT / "src/blueprints/admin_bp.py").read_text())
    for name, path in [
        ("admin_logs", "/admin/logs"),
        ("admin_gold", "/admin/gold"),
    ]:
        view = next(
            node
            for node in tree.body
            if isinstance(node, ast.FunctionDef) and node.name == name
        )
        view.decorator_list = []
        exec(
            compile(ast.Module(body=[view], type_ignores=[]), name, "exec"),
            namespace,
        )
        app.add_url_rule(path, name, login_required(namespace[name]))
    ui.log_path = log_path
    return ui


def test_admin_tabs_and_mail_template_placement(sections):
    html = sections.client.get("/admin").text
    admin_nav = html.split('aria-label="Administracija"')[1].split("</nav>")[0]
    assert 'href="/memes"' not in admin_nav
    assert 'href="/admin/logs"' in admin_nav
    assert 'href="/admin/gold"' in admin_nav
    assert 'id="gold-price-chart"' not in html
    assert "Predloge e-pošte in sistemskih strani" not in html
    html = sections.client.get("/admin/send_emails").text
    assert "Predloge e-pošte in sistemskih strani" in html
    assert "template_name=mail_newuser" in html


def test_log_tab_limits_output_without_changing_file(sections):
    before = sections.log_path.read_bytes()
    response = sections.client.get("/admin/logs")
    assert response.status_code == 200
    assert "LOG-099" not in response.text
    assert "LOG-100" in response.text and "LOG-299" in response.text
    assert sections.log_path.read_bytes() == before
    sections.log_path.unlink()
    assert "Dnevnik trenutno ni na voljo." in (
        sections.client.get("/admin/logs").text
    )


@pytest.mark.parametrize("path", ["/admin/logs", "/admin/gold"])
def test_new_admin_tabs_reject_non_admin_users(sections, path):
    sections.app.config["ADMIN"] = False
    assert sections.client.get(path).status_code == 302
    sections.app.config["AUTHENTICATED"] = False
    assert sections.client.get(path).status_code == 401


def test_home_links_and_statistics_render_without_javascript(sections):
    html = sections.client.get("/").text
    for path in [
        "/movies?onlyrecommended=on",
        "/pod_krinko",
        "/music",
        "/radio-stories",
        "/memes",
        "/weather",
        "/blog",
        "/suggestions",
    ]:
        assert f'href="{path}"' in html
    assert "42 filmov" in html
    assert "360 skladb" in html
    with sections.app.test_request_context("/"):
        html = render_template("index.html")
    assert "0 filmov" in html


def test_browser_home_and_admin_tabs_responsive(sections, browser):
    page = browser.page
    for width in [320, 390, 820, 1440]:
        page.set_viewport_size({"width": width, "height": 900})
        for path in ["/", "/admin/logs", "/admin/gold", "/admin/send_emails"]:
            page.goto(browser.base + path)
            assert page.evaluate(
                "document.documentElement.scrollWidth <= innerWidth + 1"
            ), (width, path)
            if path.startswith("/admin/"):
                assert (
                    page.locator(".admin-nav [aria-current=page]").count() == 1
                )
                assert page.locator('.admin-nav a[href="/memes"]').count() == 0
            if width in (390, 1440):
                filename = path.strip("/").replace("/", "-") or "home"
                page.screenshot(
                    path=f"/private/tmp/home-tabs-{width}-{filename}.png",
                    full_page=True,
                )
    page.goto(browser.base + "/")
    page.get_by_role("link", name="Razišči vsebine").click()
    assert page.locator("#home-explore-title").is_visible()


def test_browser_gold_failure_and_retry(sections, browser):
    page = browser.page
    page.goto(browser.base + "/admin/gold")
    page.get_by_text(
        "Grafa trenutno ni mogoče naložiti.", exact=False
    ).wait_for()
    assert page.locator("#retryGold").is_enabled()
    page.route(
        "https://www.bullionvault.com/chart/bullionvaultchart.js",
        lambda route: route.fulfill(
            content_type="text/javascript",
            body="""
        window.BullionVaultChart = function(options, id) {
            window.testGoldOptions = options;
            document.getElementById(id).textContent = 'Testni graf';
        };""",
        ),
    )
    page.locator("#retryGold").click()
    page.get_by_text("Testni graf", exact=True).wait_for()
    assert page.evaluate("window.testGoldOptions.currency") == "EUR"
    assert page.locator("#goldMessage").is_hidden()


def test_browser_chart_colors_are_distinct_and_stable(sections, browser):
    page = browser.page
    asset = Path("/private/tmp/marinkino-plotly.min.js")
    if not asset.exists():
        pytest.skip("Optional local Plotly asset unavailable")
    page.route(
        "https://cdn.plot.ly/**",
        lambda route: route.fulfill(
            path=str(asset), content_type="text/javascript"
        ),
    )
    page.goto(browser.base + "/admin")
    page.locator("#access-monthly-graph .main-svg").first.wait_for()
    colors = page.locator("#access-monthly-graph").evaluate(
        "(node) => node.data.map(trace => trace.line.color)"
    )
    assert colors == ["#1f77b4", "#ff7f0e"]
    page.locator("#access-user-graph .main-svg").first.wait_for()
    assert (
        page.locator("#access-user-graph").evaluate(
            "(node) => node.data[0].line.color"
        )
        == "#1f77b4"
    )

"""Welcome layout and first-login completion using the real route."""

import ast
from pathlib import Path
from unittest.mock import Mock

import pytest
from flask import redirect, render_template, request, url_for
from flask_login import current_user, login_required
from test_admin_memes_ui import browser as browser_fixture
from test_admin_memes_ui import ui as ui_fixture

ui = ui_fixture
browser = browser_fixture


@pytest.fixture
def welcome(ui):
    stats = dict(
        movies_count=42,
        movies_duration=105.4,
        cartoons_count=12,
        cartoons_duration=25.1,
        music_count=360,
        memes_count=120,
        blog_count=8,
    )
    users = {"test-admin": {"first_login": True}}
    save = Mock()
    root = Path(__file__).resolve().parents[1]
    tree = ast.parse((root / "src/blueprints/auth_bp.py").read_text())
    view = next(
        node
        for node in tree.body
        if isinstance(node, ast.FunctionDef) and node.name == "welcome"
    )
    view.decorator_list = []
    namespace = dict(
        users=users,
        current_user=current_user,
        request=request,
        save_users=save,
        redirect=redirect,
        url_for=url_for,
        render_template=render_template,
        get_welcome_stats=lambda: stats,
    )
    exec(
        compile(ast.Module(body=[view], type_ignores=[]), "welcome", "exec"),
        namespace,
    )
    ui.app.add_url_rule(
        "/welcome",
        "auth.welcome",
        login_required(namespace["welcome"]),
        methods=["GET", "POST"],
    )
    ui.app.add_url_rule("/", "home", lambda: "Home")
    ui.app.add_url_rule("/login", "auth.login", lambda: "Login")
    ui.app.login_manager.login_view = "auth.login"
    ui.users = users
    ui.save = save
    return ui


def test_welcome_get_and_first_login_post(welcome):
    response = welcome.client.get("/welcome")
    assert response.status_code == 200
    assert "42 filmov" in response.text
    assert "12 zbirk" in response.text
    assert "360 skladb" in response.text
    assert welcome.users["test-admin"]["first_login"] is True
    welcome.save.assert_not_called()
    response = welcome.client.post(
        "/welcome", data={"csrf_token": "test-csrf"}
    )
    assert response.status_code == 302
    assert response.location == "/"
    assert welcome.users["test-admin"]["first_login"] is False
    welcome.save.assert_called_once()
    welcome.app.config["AUTHENTICATED"] = False
    assert welcome.client.get("/welcome").status_code == 302


def test_browser_welcome_layout_and_both_continue_buttons(welcome, browser):
    page = browser.page
    for width in [320, 390, 820, 1440]:
        page.set_viewport_size({"width": width, "height": 844})
        page.goto(browser.base + "/welcome")
        assert page.get_by_role(
            "heading", name="Bog daj, test-admin!"
        ).is_visible()
        assert page.evaluate(
            "document.documentElement.scrollWidth <= innerWidth + 1"
        )
        assert page.locator(".home-feature, .home-card").count() == 8
        assert page.locator('a[href="/suggestions"]').count() >= 1
        for card in page.locator(".home-feature, .home-card").all():
            assert card.get_attribute("href").startswith("/")
        page.get_by_role("link", name="Najprej kratek ogled").click()
        assert page.locator("#welcome-explore-title").evaluate(
            "(el) => el.getBoundingClientRect().top >= 0"
        )
        page.screenshot(
            path=f"/private/tmp/welcome-{width}.png", full_page=True
        )
    for label in ["Začni raziskovati", "Nadaljuj na MarinKino"]:
        welcome.users["test-admin"]["first_login"] = True
        page.goto(browser.base + "/welcome")
        page.get_by_role("button", name=label).click()
        page.wait_for_url(browser.base + "/")
        assert welcome.users["test-admin"]["first_login"] is False
    assert welcome.save.call_count == 2

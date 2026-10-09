"""Account forms: isolated POST capture and opt-in browser checks."""

import pytest
from flask import flash, render_template, request
from test_admin_memes_ui import browser as browser_fixture
from test_admin_memes_ui import ui as ui_fixture

ui = ui_fixture
browser = browser_fixture


@pytest.fixture
def account(ui):
    ui.app.config["AUTHENTICATED"] = False
    submitted = []

    def view(template, **context):
        if request.method == "POST":
            submitted.append(dict(request.form))
            flash("Preveri vnesene podatke.", "error")
        return render_template(template, **context)

    ui.app.add_url_rule(
        "/login",
        "auth.login",
        lambda: view("login.html"),
        methods=["GET", "POST"],
    )
    ui.app.add_url_rule(
        "/forgot-password",
        "auth.forgot_password",
        lambda: view("forgot_password.html"),
        methods=["GET", "POST"],
    )
    ui.app.add_url_rule(
        "/password/change",
        "auth.change_password",
        lambda: view("change_password.html"),
        methods=["GET", "POST"],
    )
    ui.app.add_url_rule(
        "/reset-password",
        "auth.reset_password",
        lambda: view(
            "reset_password.html",
            token="test-token",
            username="Ana",
            is_initial_setup=True,
        ),
        methods=["GET", "POST"],
    )
    ui.app.add_url_rule(
        "/limit",
        "limit",
        lambda: view("limit_exceeded.html", section="te igre"),
    )
    ui.submitted = submitted
    return ui


def test_account_templates_and_retry_values(account):
    for path in [
        "/login",
        "/forgot-password",
        "/password/change",
        "/reset-password",
        "/limit",
    ]:
        response = account.client.get(path)
        assert response.status_code == 200
        assert "auth-form-title" in response.text
    html = account.client.post(
        "/login", data={"username": "<Ana>", "password": "secret-value"}
    ).text
    assert "&lt;Ana&gt;" in html
    assert "secret-value" not in html
    assert "Preveri vnesene podatke." in html
    html = account.client.post(
        "/forgot-password", data={"email": "ana@example.test"}
    ).text
    assert 'value="ana@example.test"' in html


def test_browser_account_layout(account, browser):
    page = browser.page
    for width in [320, 390, 820, 1440]:
        page.set_viewport_size({"width": width, "height": 844})
        for path in [
            "/login",
            "/forgot-password",
            "/password/change",
            "/reset-password",
            "/limit",
        ]:
            page.goto(browser.base + path)
            assert page.locator("h1").is_visible()
            assert page.evaluate(
                "document.documentElement.scrollWidth <= innerWidth + 1"
            )
            for field in page.locator(".auth-field input").all():
                assert field.evaluate(
                    "(el) => el.getBoundingClientRect().width >= 200"
                )
            if width in [390, 1440]:
                screenshot = f"auth-{path.replace('/', '-')}-{width}.png"
                page.screenshot(
                    path=f"/private/tmp/{screenshot}",
                    full_page=True,
                )


def test_browser_password_matching_generator_and_post(account, browser):
    page = browser.page
    page.goto(browser.base + "/password/change")
    page.locator("#current_password").fill("Current-password1!")
    page.locator("#password").fill("New-password123!")
    page.locator("#password_confirm").fill("Different-password123!")
    page.get_by_role("button", name="Shrani novo geslo").click()
    assert not account.submitted
    assert "Gesli se ne ujemata" in page.locator("#password_confirm").evaluate(
        "(el) => el.validationMessage"
    )
    page.locator("#password_confirm").fill("New-password123!")
    assert page.locator("#password_confirm").evaluate(
        "(el) => el.validity.valid"
    )
    page.get_by_role("button", name="Ustvari močno geslo").click()
    password = page.locator("#password").input_value()
    assert len(password) == 20
    assert any(c.islower() for c in password)
    assert any(c.isupper() for c in password)
    assert any(c.isdigit() for c in password)
    assert any(not c.isalnum() for c in password)
    assert page.locator("#password_confirm").input_value() == password
    assert (
        page.locator("#current_password").get_attribute("type") == "password"
    )
    toggle = page.locator('[data-password-toggle="password"]')
    assert toggle.get_attribute("aria-pressed") == "true"
    toggle.click()
    assert page.locator("#password").get_attribute("type") == "password"
    page.get_by_role("button", name="Shrani novo geslo").click()
    page.wait_for_load_state()
    assert account.submitted[-1]["csrf_token"] == "test-csrf"
    assert account.submitted[-1]["password"] == password
    assert page.locator("#password").input_value() == ""
    page.goto(browser.base + "/reset-password")
    assert page.locator("#username").get_attribute("readonly") is not None
    page.get_by_role("button", name="Ustvari močno geslo").click()
    page.get_by_role("button", name="Potrdi novo geslo").click()
    page.wait_for_load_state()
    assert account.submitted[-1]["token"] == "test-token"
    assert account.submitted[-1]["username"] == "Ana"


def test_browser_without_javascript(account, browser):
    # Native submission remains usable without JavaScript.
    context = browser.page.context.browser.new_context(
        java_script_enabled=False
    )
    page = context.new_page()
    try:
        page.goto(browser.base + "/login")
        assert not page.locator(".auth-reveal").is_visible()
        page.locator("#username").fill("Ana")
        page.locator("#password").fill("Password123!")
        page.get_by_role("button", name="Prijavi se", exact=True).click()
        page.wait_for_load_state()
        assert account.submitted[-1]["username"] == "Ana"
    finally:
        context.close()

"""Email structure and browser previews; no delivery calls."""

from pathlib import Path
from types import SimpleNamespace

import pytest
from bs4 import BeautifulSoup
from flask import Flask, render_template
from test_admin_memes_ui import browser as browser_fixture

from blog_i18n import BLOG_LANGUAGES, messages

browser = browser_fixture
ROOT = Path(__file__).resolve().parents[1]
TEMPLATES = {
    "welcome": "mail_newuser.html",
    "reset": "mail_reset_password.html",
    "post": "mail_blog_post.html",
    "confirmation": "mail_blog_subscription_confirmation.html",
    "notification": "mail_notification.html",
    "newsletter": "mail_newsletters/mail_monthly_recommendation.html",
}


@pytest.fixture
def ui():
    app = Flask(
        __name__,
        template_folder=str(ROOT / "src/templates"),
        static_folder=str(ROOT / "src/static"),
    )
    app.config.update(TESTING=True)
    app.jinja_env.globals.update(domain="example.test", current_year=2026)

    @app.route("/preview/<name>")
    def preview(name):
        from flask import request

        language = request.args.get("lang", "sl")
        token = "test-token-" + "a" * 180
        return render_template(
            TEMPLATES[name],
            is_for_mail=True,
            username="<Ana & Bine>",
            email="ana@example.test",
            expiry_minutes=1440,
            reset_link=f"https://example.test/reset-password?token={token}",
            confirmation_url=f"https://example.test/blog/confirm-subscription/{token}",
            mail_base_url="https://example.test",
            blog_url="https://example.test/blog",
            post_url="https://example.test/blog/objava",
            post=dict(
                title="Slovenski naslov",
                excerpt="Slovenski povzetek",
                subtitle="Podnaslov",
            ),
            mail_copy=messages(language),
            mail_language=language,
            mail_direction=BLOG_LANGUAGES[language]["direction"],
            mailtitle="Filmski izbor",
            meme_file="nasmeh.png",
            notification_title="Odgovor na komentar",
            notification_fields=[
                ("Film", "Poletni večer"),
                ("Avtor", "<Ana & Bine>"),
            ],
            notification_sections=[
                ("Komentar", "<script>alert(1)</script>\nDruga vrstica"),
                ("Odgovor", "Hvala za predlog."),
            ],
            notification_action_url="https://example.test/admin",
            notification_action_label="Odpri administracijo",
            film_recommendations=[
                dict(
                    title="Film za prijeten večer",
                    path="filmi/Poletni večer",
                    cover_filename="poster.jpg",
                    genres=["Drama", "Komedija"],
                    duration="90 min",
                    short_description="Kratek opis priporočenega filma.",
                )
            ],
        )

    return SimpleNamespace(app=app)


@pytest.mark.parametrize("name", TEMPLATES)
def test_email_templates_are_standalone_and_keep_action_links(ui, name):
    response = ui.app.test_client().get(f"/preview/{name}")
    assert response.status_code == 200
    soup = BeautifulSoup(response.text, "html.parser")
    assert soup.h1 and soup.html["lang"] == "sl"
    assert not soup.select("script, link[rel=stylesheet], input, form")
    assert "<Ana & Bine>" not in response.text
    assert soup.select("table[role=presentation]")
    for anchor in soup.select("a[href]"):
        assert anchor["href"].startswith("https://")
    action = {
        "welcome": "reset-password",
        "reset": "reset-password",
        "post": "/blog/objava",
        "confirmation": "confirm-subscription",
        "notification": "/admin",
        "newsletter": "/movies/play/",
    }[name]
    assert any(action in a["href"] for a in soup.select("a[href]"))
    if name == "newsletter":
        assert any(
            "Poletni%20ve%C4%8Der" in a["href"] for a in soup.select("a[href]")
        )


@pytest.mark.parametrize("language", BLOG_LANGUAGES)
def test_blog_email_language_and_direction_are_preserved(ui, language):
    for name in ["post", "confirmation"]:
        response = ui.app.test_client().get(f"/preview/{name}?lang={language}")
        soup = BeautifulSoup(response.text, "html.parser")
        assert soup.html["lang"] == language
        assert soup.html["dir"] == BLOG_LANGUAGES[language]["direction"]
        if language != "sl":
            assert "Slovenski naslov" not in soup.text
            assert messages(language)["automatic_notice"] in soup.text


def test_browser_email_mobile_and_desktop_layout(ui, browser):
    page = browser.page
    for width in [320, 390, 620, 900]:
        page.set_viewport_size({"width": width, "height": 900})
        for name in TEMPLATES:
            languages = (
                ["sl", "ar"] if name in ["post", "confirmation"] else ["sl"]
            )
            for language in languages:
                page.goto(browser.base + f"/preview/{name}?lang={language}")
                assert page.locator("h1").is_visible()
                assert page.evaluate(
                    "document.documentElement.scrollWidth <= innerWidth + 1"
                )
                if width in [390, 900]:
                    page.screenshot(
                        path=f"/private/tmp/mail-{name}-{language}-{width}.png",
                        full_page=True,
                    )

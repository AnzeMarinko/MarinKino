"""Exercise public translation links through the blog routes and templates."""

import copy
import importlib.util
import sys
from html.parser import HTMLParser
from pathlib import Path
from types import ModuleType, SimpleNamespace
from unittest.mock import Mock, patch
from urllib.parse import parse_qs, urlsplit

import pytest
from flask import Flask, render_template
from flask_login import LoginManager, UserMixin

from blog_i18n import BLOG_LANGUAGES, messages


class Links(HTMLParser):
    def __init__(self, html):
        super().__init__()
        self.anchors = []
        self.feed(html)

    def handle_starttag(self, tag, attrs):
        if tag == "a":
            self.anchors.append(dict(attrs))


def translation_links(html):
    return [
        anchor
        for anchor in Links(html).anchors
        if urlsplit(anchor.get("href", "")).hostname
        == "translate.google.com"
    ]


class User(UserMixin):
    def __init__(self, username):
        self.id = username
        self.is_admin = username == "admin"


@pytest.fixture
def blog(monkeypatch):
    monkeypatch.setenv("WWW_DOMAIN", "blog.example.com")
    monkeypatch.delenv("PUBLIC_BASE_URL", raising=False)
    monkeypatch.delenv("TURNSTILE_SITE_KEY", raising=False)
    utilities = ModuleType("utils")
    utilities.FLASK_ENV = "testing"
    utilities.load_blog_subscribers = Mock(return_value=[])
    utilities.redis_client = Mock()
    utilities.safe_path = Mock()
    utilities.save_blog_subscribers = Mock()
    utilities.send_mail = Mock()
    utilities.users = {}
    # Markdown conversion is unrelated to link eligibility and URL handling.
    markdown = ModuleType("markdown")
    markdown.markdown = Mock(side_effect=lambda content, **kwargs: content)
    source = Path(__file__).resolve().parents[1] / "src"
    spec = importlib.util.spec_from_file_location(
        "translation_test_blog", source / "blueprints" / "blog_bp.py"
    )
    module = importlib.util.module_from_spec(spec)
    with patch.dict(sys.modules, {"utils": utilities, "markdown": markdown}):
        spec.loader.exec_module(module)
    posts = {
        slug: {
            "id": slug,
            "title": title,
            "content": "Vsebina objave",
            "excerpt": "Kratek opis",
            "published": published,
            "created_at": "2026-09-01T12:00:00+00:00",
        }
        for slug, title, published in (
            ("javno", "Javna objava", True),
            ("osnutek", "Zasebni osnutek", False),
            ("čebelice", "Čebelice", True),
        )
    }
    module.load_blog_posts = Mock(side_effect=lambda: copy.deepcopy(posts))
    app = Flask(
        __name__,
        template_folder=str(source / "templates"),
        static_folder=str(source / "static"),
    )
    app.config.update(TESTING=True, SECRET_KEY="translation-tests-only")
    app.jinja_env.globals["csrf_token"] = lambda: "test-csrf-token"

    @app.context_processor
    def template_context():
        return {"domain": "blog.example.com", "current_year": 2026}

    manager = LoginManager(app)
    manager.user_loader(User)
    app.register_blueprint(module.blog_bp)

    @app.route("/movies")
    def movies():
        return render_template("base.html", pagetitle="Filmi")

    return SimpleNamespace(app=app, module=module, posts=posts)


@pytest.mark.parametrize(
    "path",
    [
        "/blog",
        "/blog/javno",
        "/blog/pogoji-uporabe",
        "/blog/politika-zasebnosti",
    ],
)
def test_public_pages_offer_google_translation_for_entire_page(blog, path):
    response = blog.app.test_client().get(path)
    assert response.status_code == 200
    html = response.get_data(as_text=True)
    links = translation_links(html)
    assert len(links) == len(BLOG_LANGUAGES) - 1
    parameters = [parse_qs(urlsplit(link["href"]).query) for link in links]
    assert {params["tl"][0] for params in parameters} == (
        set(BLOG_LANGUAGES) - {"sl"}
    )
    for params in parameters:
        assert params["sl"] == ["sl"]
        assert params["u"] == [
            f"https://blog.example.com{path}?lang={params['tl'][0]}"
        ]
    for link in links:
        assert link["target"] == "_blank"
        assert {"noopener", "noreferrer"} <= set(link["rel"].split())
    assert "<title>" in html
    assert "<nav " in html
    assert "<footer " in html
    assert "avtomatsk" in html
    assert "automatic" in html.lower()
    assert "automatisch" in html.lower()


def test_source_url_uses_configured_domain_and_drops_request_arguments(blog):
    response = blog.app.test_client().get(
        "/blog/javno?token=private-value&next=https://attacker.example",
        base_url="http://untrusted-host.example",
    )
    links = translation_links(response.get_data(as_text=True))
    assert len(links) == len(BLOG_LANGUAGES) - 1
    for link in links:
        params = parse_qs(urlsplit(link["href"]).query)
        assert params["u"] == [
            "https://blog.example.com/blog/javno?lang=" + params["tl"][0]
        ]
        assert "private-value" not in link["href"]
        assert "untrusted-host" not in link["href"]


def test_published_unicode_slug_survives_url_encoding(blog):
    response = blog.app.test_client().get("/blog/%C4%8Debelice")
    assert response.status_code == 200
    links = translation_links(response.get_data(as_text=True))
    assert len(links) == len(BLOG_LANGUAGES) - 1
    for link in links:
        source = parse_qs(urlsplit(link["href"]).query)["u"][0]
        assert urlsplit(source).path == "/blog/%C4%8Debelice"


def test_configured_public_origin_takes_precedence(blog, monkeypatch):
    monkeypatch.setenv("PUBLIC_BASE_URL", "https://public.example.com/")
    response = blog.app.test_client().get("/blog")
    links = translation_links(response.get_data(as_text=True))
    assert len(links) == len(BLOG_LANGUAGES) - 1
    for link in links:
        source = parse_qs(urlsplit(link["href"]).query)["u"][0]
        assert source.startswith("https://public.example.com/blog?lang=")


@pytest.mark.parametrize(
    "origin",
    [
        "javascript:alert(1)",
        "https://username:secret@public.example.com",
        "https://public.example.com?token=secret",
        "https://public.example.com#private-fragment",
    ],
)
def test_invalid_public_origin_has_no_translation_links(
    blog, monkeypatch, origin
):
    monkeypatch.setenv("PUBLIC_BASE_URL", origin)
    response = blog.app.test_client().get("/blog")
    assert response.status_code == 200
    assert not translation_links(response.get_data(as_text=True))


@pytest.mark.parametrize("username", ["admin", "member"])
def test_draft_preview_does_not_offer_translation(blog, username):
    client = blog.app.test_client()
    with client.session_transaction() as session:
        session["_user_id"] = username
        session["_fresh"] = True
    response = client.get("/blog/osnutek")
    assert response.status_code == 200
    assert not translation_links(response.get_data(as_text=True))


def test_anonymous_translation_source_contains_only_published_posts(blog):
    response = blog.app.test_client().get("/blog")
    html = response.get_data(as_text=True)
    assert "Javna objava" in html
    assert "Zasebni osnutek" not in html
    assert blog.app.test_client().get("/blog/osnutek").status_code == 404


def test_private_page_has_no_translation_control(blog):
    response = blog.app.test_client().get("/movies")
    html = response.get_data(as_text=True)
    assert not translation_links(html)
    assert "translation-notice" not in html


def test_blog_mail_has_no_translation_control(blog):
    with blog.app.test_request_context("/blog/javno"):
        html = render_template(
            "mail_blog_post.html",
            post=blog.posts["javno"],
            is_for_mail=True,
            blog_view="blog",
            mail_copy=messages("sl"),
            mail_language="sl",
            blog_translation_urls=blog.module.blog_translation_urls(),
        )
    assert not translation_links(html)
    assert "translation-notice" not in html

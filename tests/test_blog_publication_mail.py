"""Publication notifications preserve language and retry completed batches."""

import importlib.util
import json
import sys
from pathlib import Path
from types import ModuleType, SimpleNamespace
from unittest.mock import Mock, patch
from urllib.parse import parse_qs, urlsplit

import pytest
from flask import Flask
from flask_login import LoginManager

from blog_i18n import BLOG_LANGUAGES, messages


@pytest.fixture
def publication(tmp_path):
    utilities = ModuleType("utils")
    utilities.is_current_admin_view = Mock(return_value=True)
    utilities.load_blog_subscribers = Mock(return_value=[])
    utilities.redis_client = Mock()
    utilities.send_mail = Mock(return_value={})
    blog_module = ModuleType("blueprints.blog_bp")
    blog_module.public_base_url = lambda: "https://blog.example.com"
    config = ModuleType("content_preparation.config")
    config.LOG_FILENAME = str(tmp_path / "unused.log")
    imaging = ModuleType("PIL")
    imaging.Image = Mock()
    source = Path(__file__).resolve().parents[1] / "src"
    spec = importlib.util.spec_from_file_location(
        "publication_test_admin", source / "blueprints" / "admin_bp.py"
    )
    module = importlib.util.module_from_spec(spec)
    with patch.dict(
        sys.modules,
        {
            "utils": utilities,
            "blueprints.blog_bp": blog_module,
            "content_preparation.config": config,
            "pandas": ModuleType("pandas"),
            "PIL": imaging,
        },
    ):
        spec.loader.exec_module(module)
    module.BLOG_DATA_FILE = str(tmp_path / "posts.json")
    module.users = {
        "admin": {"is_admin": True, "emails": ["admin@example.com"]}
    }
    module.save_blog_posts(
        {
            "javno": {
                "id": "javno",
                "title": "Slovenski naslov",
                "excerpt": "Slovenski povzetek",
                "content": "Vsebina",
                "published": True,
                "mail_date": None,
            }
        }
    )
    app = Flask(
        __name__,
        template_folder=str(source / "templates"),
        static_folder=str(source / "static"),
    )
    app.config.update(
        TESTING=True, SECRET_KEY="mail-tests-only", LOGIN_DISABLED=True
    )
    manager = LoginManager(app)
    manager.user_loader(lambda user_id: None)
    app.register_blueprint(module.admin_bp)
    app.add_url_rule("/blog", endpoint="blog.blog_list", view_func=lambda: "")
    app.add_url_rule(
        "/blog/<post_id>",
        endpoint="blog.blog_post",
        view_func=lambda post_id: "",
    )
    return SimpleNamespace(
        app=app, module=module, utilities=utilities, client=app.test_client()
    )


def notify(publication):
    return publication.client.post("/admin/blog/send_mail/javno", json={})


def test_each_language_gets_its_own_private_localized_message(publication):
    publication.utilities.load_blog_subscribers.return_value = [
        {"email": f"{language.lower()}@example.com", "language": language}
        for language in BLOG_LANGUAGES
    ]
    assert notify(publication).json["success"] is True
    calls = publication.utilities.send_mail.call_args_list
    assert len(calls) == len(BLOG_LANGUAGES)
    for call, language in zip(calls, BLOG_LANGUAGES):
        payload = call.kwargs
        copy = messages(language)
        assert payload["to"] == "admin@example.com"
        assert payload["bcc"] == [f"{language.lower()}@example.com"]
        assert payload["blog"] is True
        assert copy["new_post_intro"] in payload["text"]
        assert copy["unsubscribe"] in payload["text"]
        assert f'lang="{language}"' in payload["html"]
        if language == "sl":
            assert payload["subject"] == "Nov blog: Slovenski naslov"
            assert "Slovenski povzetek" in payload["html"]
            assert "https://blog.example.com/blog/javno" in payload["text"]
        else:
            assert payload["subject"] == copy["new_post_subject"]
            assert "Slovenski naslov" not in payload["html"]
            assert "Slovenski povzetek" not in payload["html"]
            assert copy["automatic_notice"] in payload["text"]
            text_link = next(
                line.split(": ", 1)[1]
                for line in payload["text"].splitlines()
                if line.startswith(copy["read_post"] + ": ")
            )
            assert parse_qs(urlsplit(text_link).query)["tl"] == [language]
    post = publication.module.load_blog_posts()["javno"]
    assert post["mail_date"]
    assert set(post["mail_languages_sent"]) == set(BLOG_LANGUAGES)


def test_retry_skips_languages_already_delivered(publication):
    publication.utilities.load_blog_subscribers.return_value = [
        "legacy@example.com",
        {"email": "foreign@example.com", "language": "de"},
    ]
    send = publication.utilities.send_mail
    send.side_effect = [{}, RuntimeError("mail unavailable")]
    assert notify(publication).json["success"] is False
    post = publication.module.load_blog_posts()["javno"]
    assert post["mail_languages_sent"] == ["sl"]
    assert post["mail_date"] is None

    send.reset_mock()
    send.side_effect = None
    assert notify(publication).json["success"] is True
    send.assert_called_once()
    assert send.call_args.kwargs["bcc"] == ["foreign@example.com"]
    post = publication.module.load_blog_posts()["javno"]
    assert post["mail_languages_sent"] == ["de", "sl"]
    assert post["mail_date"]


def test_smtp_rejection_does_not_mark_delivery_complete(publication):
    publication.utilities.load_blog_subscribers.return_value = [
        {"email": "foreign@example.com", "language": "de"}
    ]
    publication.utilities.send_mail.return_value = {
        "foreign@example.com": (550, b"rejected")
    }
    assert notify(publication).json["success"] is False
    post = publication.module.load_blog_posts()["javno"]
    assert not post.get("mail_languages_sent")
    assert post["mail_date"] is None


def test_successful_notifications_cannot_be_sent_twice(publication):
    publication.utilities.load_blog_subscribers.return_value = [
        "legacy@example.com"
    ]
    assert notify(publication).json["success"] is True
    assert notify(publication).json["success"] is False
    publication.utilities.send_mail.assert_called_once()


def test_editing_post_preserves_completed_language_batches(publication):
    posts = publication.module.load_blog_posts()
    posts["javno"]["mail_languages_sent"] = ["sl"]
    publication.module.save_blog_posts(posts)
    response = publication.client.post(
        "/admin/blog/edit/javno",
        data={"title": "Nov naslov", "content": "Nova vsebina"},
        headers={"X-Requested-With": "XMLHttpRequest"},
    )
    assert response.json["success"] is True
    with open(publication.module.BLOG_DATA_FILE, encoding="utf-8") as stream:
        updated = json.load(stream)
    assert updated["javno"]["mail_languages_sent"] == ["sl"]

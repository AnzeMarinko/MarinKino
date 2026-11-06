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

from background_jobs import JobStore
from blog_i18n import BLOG_LANGUAGES, messages
from mail_jobs import deliver_blog_mail_job


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
    jobs = JobStore(tmp_path / "jobs.sqlite3")
    app.extensions["jobs"] = jobs
    manager = LoginManager(app)
    manager.user_loader(lambda user_id: None)
    app.register_blueprint(module.admin_bp)
    app.add_url_rule("/blog", endpoint="blog.blog_list", view_func=lambda: "")
    app.add_url_rule(
        "/blog/<post_id>",
        endpoint="blog.blog_post",
        view_func=lambda post_id: "",
    )

    def run():
        with patch.dict(sys.modules, {"utils": utilities}):
            jobs.run_once({"blog_mail": deliver_blog_mail_job})

    return SimpleNamespace(
        app=app,
        module=module,
        utilities=utilities,
        client=app.test_client(),
        jobs=jobs,
        run=run,
    )


def notify(publication):
    return publication.client.post("/admin/blog/send_mail/javno", json={})


def test_each_language_gets_its_own_private_localized_message(publication):
    publication.utilities.load_blog_subscribers.return_value = [
        {"email": f"{language.lower()}@example.com", "language": language}
        for language in BLOG_LANGUAGES
    ]
    assert notify(publication).json["success"] is True
    publication.utilities.send_mail.assert_not_called()
    assert not publication.module.load_blog_posts()["javno"].get("mail_date")
    publication.run()
    calls = publication.utilities.send_mail.call_args_list
    assert len(calls) == len(BLOG_LANGUAGES)
    for call, language in zip(calls, BLOG_LANGUAGES):
        payload = call.kwargs
        copy = messages(language)
        assert payload["to"] == "admin@example.com"
        assert payload["bcc"] == [f"{language.lower()}@example.com"]
        assert payload["blog"] is True
        assert copy["new_post_intro"] in payload["text"]
        assert copy["blog_title"] in payload["text"]
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
    queued = notify(publication)
    assert queued.json["success"] is True
    publication.run()
    assert (
        publication.client.get(queued.json["status_url"]).json["state"]
        == "failed"
    )
    post = publication.module.load_blog_posts()["javno"]
    assert post["mail_languages_sent"] == ["sl"]
    assert post["mail_date"] is None

    send.reset_mock()
    send.side_effect = None
    assert notify(publication).json["success"] is True
    publication.run()
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
        "foreign@example.com": (550, b"rejected"),
        "admin@example.com": (550, b"rejected"),
    }
    queued = notify(publication)
    assert queued.json["success"] is True
    publication.run()
    assert (
        publication.client.get(queued.json["status_url"]).json["state"]
        == "failed"
    )
    post = publication.module.load_blog_posts()["javno"]
    assert not post.get("mail_languages_sent")
    assert post["mail_date"] is None


def test_successful_notifications_cannot_be_sent_twice(publication):
    publication.utilities.load_blog_subscribers.return_value = [
        "legacy@example.com"
    ]
    assert notify(publication).json["success"] is True
    publication.run()
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


def test_repeated_click_keeps_one_pending_campaign(publication):
    publication.utilities.load_blog_subscribers.return_value = [
        "reader@example.com"
    ]
    first, second = notify(publication), notify(publication)
    assert first.json["status_url"] == second.json["status_url"]
    publication.utilities.send_mail.assert_not_called()
    publication.run()
    publication.utilities.send_mail.assert_called_once()
    assert publication.client.get(first.json["status_url"]).json == {
        "state": "done"
    }


def test_delivery_without_durable_progress_cannot_be_replayed(publication):
    publication.utilities.load_blog_subscribers.return_value = [
        "reader@example.com"
    ]
    queued = notify(publication)
    with patch(
        "mail_jobs.atomic_write_json", side_effect=OSError("disk full")
    ):
        publication.run()
    assert publication.client.get(queued.json["status_url"]).json == {
        "state": "uncertain"
    }
    assert notify(publication).json["status_url"] == queued.json["status_url"]
    publication.run()
    publication.utilities.send_mail.assert_called_once()


def test_partial_delivery_requires_verification_before_retry(publication):
    publication.utilities.load_blog_subscribers.return_value = [
        "reader@example.com"
    ]
    publication.utilities.send_mail.return_value = {
        "reader@example.com": (550, b"rejected")
    }
    queued = notify(publication)
    publication.run()
    assert publication.client.get(queued.json["status_url"]).json == {
        "state": "uncertain"
    }
    assert not publication.module.load_blog_posts()["javno"].get("mail_date")
    retried = notify(publication)
    assert retried.json["state"] == "uncertain"
    assert retried.json["status_url"] == queued.json["status_url"]
    publication.run()
    publication.utilities.send_mail.assert_called_once()


def test_interrupted_smtp_is_not_repeated(publication):
    import smtplib

    publication.utilities.load_blog_subscribers.return_value = [
        "reader@example.com"
    ]
    publication.utilities.send_mail.side_effect = (
        smtplib.SMTPServerDisconnected("connection lost")
    )
    queued = notify(publication)
    publication.run()
    assert publication.client.get(queued.json["status_url"]).json == {
        "state": "uncertain"
    }
    publication.run()
    publication.utilities.send_mail.assert_called_once()

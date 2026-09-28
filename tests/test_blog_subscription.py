"""Exercise localized double opt-in without sending email or using services."""

import copy
import json
from html import unescape
from html.parser import HTMLParser
from types import SimpleNamespace
from unittest.mock import Mock
from urllib.parse import parse_qs, urlsplit

import fakeredis
import pytest
from test_blog_translation import Links

from blog_i18n import BLOG_LANGUAGES, messages

pytest_plugins = ["test_blog_translation"]

LANGUAGES = (
    "sl", "en", "de", "es", "it", "fr", "pl", "uk",
    "pt", "ar", "zh-CN", "ja",
)
PENDING_PREFIX = "blog:subscription:pending:"


class Elements(HTMLParser):
    def __init__(self, html):
        super().__init__()
        self.elements = []
        self.feed(html)

    def handle_starttag(self, tag, attrs):
        self.elements.append((tag, dict(attrs)))

    def find(self, tag, **expected):
        return [
            attrs for element, attrs in self.elements
            if element == tag
            and all(attrs.get(key) == value for key, value in expected.items())
        ]


@pytest.fixture
def subscription(blog, monkeypatch):
    module = blog.module
    blog.app.config["SERVER_NAME"] = "blog.example.com"
    redis = fakeredis.FakeRedis(decode_responses=True)
    subscribers = []
    module.redis_client = redis
    module.load_blog_subscribers = Mock(
        side_effect=lambda: copy.deepcopy(subscribers)
    )

    def save(records):
        subscribers[:] = copy.deepcopy(records)

    module.save_blog_subscribers = Mock(side_effect=save)
    module.send_mail = Mock(return_value=[])
    module.notify_admins_about_subscriber = Mock()
    module.verify_turnstile = Mock(return_value=True)
    monkeypatch.setenv("TURNSTILE_SITE_KEY", "test-turnstile-site-key")
    # Even an accidental verification call must never reach the network.
    monkeypatch.setattr(
        module.requests,
        "post",
        Mock(side_effect=AssertionError("Unexpected network request")),
    )
    return SimpleNamespace(
        app=blog.app,
        client=blog.app.test_client(),
        module=module,
        redis=redis,
        subscribers=subscribers,
    )


def submit(subscription, language="en", **overrides):
    data = {
        "email": " Reader@Example.com ",
        "language": language,
        "terms_accepted": "yes",
        "cf-turnstile-response": "test-turnstile-token",
        "website": "",
        "csrf_token": "test-csrf-token",
    }
    data.update(overrides)
    return subscription.client.post("/blog/subscribe", data=data)


def pending(subscription):
    keys = subscription.redis.keys(PENDING_PREFIX + "*")
    assert len(keys) == 1
    key = keys[0]
    return key, json.loads(subscription.redis.get(key))


def assert_notice(subscription, response, language, message):
    assert response.status_code == 302
    target = urlsplit(response.location)
    assert target.path == "/blog/subscribe"
    assert parse_qs(target.query) == {"lang": [language]}
    page = subscription.client.get(response.location)
    assert page.status_code == 200
    assert messages(language)[message] in unescape(page.get_data(as_text=True))


@pytest.mark.parametrize("language", LANGUAGES)
def test_native_form_is_localized_with_same_origin_protections(
    subscription, language
):
    response = subscription.client.get(f"/blog/subscribe?lang={language}")
    assert response.status_code == 200
    assert response.headers["Cache-Control"] == "no-store"
    assert response.headers["Referrer-Policy"] == "no-referrer"
    html = response.get_data(as_text=True)
    elements = Elements(html)
    direction = "rtl" if language == "ar" else "ltr"
    assert elements.find("html", lang=language, dir=direction)
    assert elements.find("form", method="post", action="/blog/subscribe")
    assert elements.find(
        "input", name="csrf_token", value="test-csrf-token"
    )
    assert elements.find("input", name="language", value=language)
    assert elements.find(
        "input", name="email", type="email", dir="ltr"
    )
    assert elements.find(
        "div", **{
            "class": "cf-turnstile",
            "data-sitekey": "test-turnstile-site-key",
            "data-action": "blog_subscribe",
            "data-language": language.lower(),
        }
    )
    options = elements.find("option")
    assert {option["value"] for option in options} == set(LANGUAGES)
    assert [option["value"] for option in options if "selected" in option] == [
        language
    ]
    for key in ("subscription_heading", "email_label", "subscribe"):
        assert messages(language)[key] in unescape(html)
    assert f'>{messages(language)["blog_title"]}</a>' in unescape(html)
    assert "site-translation__control" not in html
    subscription.module.send_mail.assert_not_called()


@pytest.mark.parametrize("language", LANGUAGES)
def test_confirmation_email_and_persisted_preference_follow_selected_language(
    subscription, language
):
    response = submit(subscription, language)
    assert_notice(subscription, response, language, "check_email")
    key, record = pending(subscription)
    assert record == {"email": "reader@example.com", "language": language}
    assert 86390 <= subscription.redis.ttl(key) <= 86400
    assert subscription.subscribers == []
    subscription.module.save_blog_subscribers.assert_not_called()
    subscription.module.verify_turnstile.assert_called_once_with(
        "test-turnstile-token"
    )

    subscription.module.send_mail.assert_called_once()
    mail = subscription.module.send_mail.call_args.kwargs
    assert mail["to"] == "reader@example.com"
    assert mail["subject"] == messages(language)["confirmation_subject"]
    assert messages(language)["blog_title"] in unescape(mail["html"])
    for field in ("text", "html"):
        rendered = unescape(mail[field])
        for message in (
            "confirmation_intro", "confirmation_instruction", "expires",
            "confirmation_ignore",
        ):
            assert messages(language)[message] in rendered
        if language != "sl":
            assert messages(language)["automatic_notice"] in rendered
    direction = BLOG_LANGUAGES[language]["direction"]
    assert Elements(mail["html"]).find("html", lang=language, dir=direction)
    token = key.removeprefix(PENDING_PREFIX)
    confirmation_links = [
        anchor["href"]
        for anchor in Links(mail["html"]).anchors
        if token in anchor.get("href", "")
    ]
    assert len(confirmation_links) == 2
    for link in confirmation_links:
        parsed = urlsplit(link)
        assert parsed.scheme == "https"
        assert parsed.netloc == "blog.example.com"
        assert parsed.path == f"/blog/subscribe/confirm/{token}"
        assert parse_qs(parsed.query) == {"lang": [language]}
        assert link in mail["text"]
    for anchor in Links(mail["html"]).anchors:
        if "translate.google.com" in anchor.get("href", ""):
            assert token not in anchor["href"]

    confirmed = subscription.client.get(confirmation_links[0])
    assert_notice(subscription, confirmed, language, "confirmed")
    assert subscription.subscribers == [record]
    assert subscription.redis.get(key) is None
    subscription.module.notify_admins_about_subscriber.assert_called_once_with(
        "reader@example.com"
    )


def test_existing_preference_changes_only_after_ownership_confirmation(
    subscription,
):
    subscription.subscribers.append({
        "email": "reader@example.com", "language": "sl"
    })
    response = submit(subscription, "de")
    assert_notice(subscription, response, "de", "check_email")
    key, record = pending(subscription)
    assert record["language"] == "de"
    assert subscription.subscribers[0]["language"] == "sl"
    subscription.module.save_blog_subscribers.assert_not_called()
    token = key.removeprefix(PENDING_PREFIX)
    confirmed = subscription.client.get(
        f"/blog/subscribe/confirm/{token}?lang=de"
    )
    assert_notice(subscription, confirmed, "de", "confirmed")
    assert subscription.subscribers == [record]
    subscription.module.notify_admins_about_subscriber.assert_not_called()


def test_legacy_pending_email_confirms_as_slovenian(subscription):
    subscription.redis.set(
        PENDING_PREFIX + "legacy-token", "reader@example.com", ex=86400
    )
    response = subscription.client.get(
        "/blog/subscribe/confirm/legacy-token?lang=en"
    )
    assert_notice(subscription, response, "sl", "confirmed")
    assert subscription.subscribers == [{
        "email": "reader@example.com", "language": "sl"
    }]


def test_confirmation_payload_language_overrides_tampered_query(subscription):
    subscription.redis.set(
        PENDING_PREFIX + "arabic-token",
        json.dumps({"email": "reader@example.com", "language": "ar"}),
        ex=86400,
    )
    response = subscription.client.get(
        "/blog/subscribe/confirm/arabic-token?lang=en"
    )
    assert_notice(subscription, response, "ar", "confirmed")
    assert subscription.subscribers[0]["language"] == "ar"


def test_same_language_duplicate_does_not_send_confirmation(subscription):
    subscription.subscribers.append({
        "email": "reader@example.com", "language": "fr"
    })
    response = submit(subscription, "fr")
    assert_notice(subscription, response, "fr", "generic_success")
    subscription.module.send_mail.assert_not_called()
    subscription.module.save_blog_subscribers.assert_not_called()
    assert subscription.redis.keys(PENDING_PREFIX + "*") == []


@pytest.mark.parametrize("language", ["invalid", "../../en", "<script>"])
def test_unknown_language_falls_back_to_slovenian(subscription, language):
    response = subscription.client.get(
        "/blog/subscribe", query_string={"lang": language}
    )
    assert Elements(response.get_data(as_text=True)).find("html", lang="sl")
    response = submit(subscription, language)
    assert_notice(subscription, response, "sl", "check_email")
    assert pending(subscription)[1]["language"] == "sl"
    mail = subscription.module.send_mail.call_args.kwargs
    assert mail["subject"] == messages("sl")["confirmation_subject"]


@pytest.mark.parametrize("expired", [False, True])
def test_missing_and_expired_token_errors_use_requested_language(
    subscription, expired
):
    if expired:
        key = PENDING_PREFIX + "missing-token"
        subscription.redis.set(key, "reader@example.com")
        subscription.redis.expire(key, 0)
    response = subscription.client.get(
        "/blog/subscribe/confirm/missing-token?lang=it"
    )
    assert_notice(subscription, response, "it", "invalid_token")
    subscription.module.save_blog_subscribers.assert_not_called()
    subscription.module.send_mail.assert_not_called()


@pytest.mark.parametrize(
    ("overrides", "message"),
    [
        ({"email": "invalid"}, "invalid_email"),
        ({"email": "two@@example.com"}, "invalid_email"),
        ({"email": "two words@example.com"}, "invalid_email"),
        ({"terms_accepted": ""}, "terms_required"),
    ],
)
def test_invalid_submission_errors_are_localized(
    subscription, overrides, message
):
    response = submit(subscription, "es", **overrides)
    assert_notice(subscription, response, "es", message)
    subscription.module.send_mail.assert_not_called()
    assert subscription.redis.keys(PENDING_PREFIX + "*") == []


def test_turnstile_failure_is_localized_without_creating_subscription(
    subscription,
):
    subscription.module.verify_turnstile.return_value = False
    response = submit(subscription, "pl")
    assert_notice(subscription, response, "pl", "verify_failed")
    subscription.module.send_mail.assert_not_called()
    assert subscription.redis.keys(PENDING_PREFIX + "*") == []


def test_rate_limit_error_is_localized_and_does_not_send_more_mail(
    subscription,
):
    for _ in range(subscription.module.SUBSCRIPTION_EMAIL_LIMIT):
        submit(subscription, "uk")
    sent = subscription.module.send_mail.call_count
    assert sent == subscription.module.SUBSCRIPTION_EMAIL_LIMIT
    response = submit(subscription, "uk")
    assert_notice(subscription, response, "uk", "retry_later")
    assert subscription.module.send_mail.call_count == sent


@pytest.mark.parametrize("raises", [False, True])
def test_mail_failure_removes_pending_token_and_reports_localized_error(
    subscription, raises
):
    if raises:
        subscription.module.send_mail.side_effect = RuntimeError("SMTP down")
    else:
        subscription.module.send_mail.return_value = ["reader@example.com"]
    response = submit(subscription, "ja")
    assert_notice(subscription, response, "ja", "mail_failed")
    assert subscription.redis.keys(PENDING_PREFIX + "*") == []
    subscription.module.save_blog_subscribers.assert_not_called()
    assert subscription.subscribers == []


def test_honeypot_suppresses_mail_and_keeps_language(subscription):
    response = submit(subscription, "pt", website="https://spam.example")
    assert response.status_code == 302
    assert parse_qs(urlsplit(response.location).query) == {"lang": ["pt"]}
    subscription.module.send_mail.assert_not_called()
    subscription.module.verify_turnstile.assert_not_called()
    assert subscription.redis.keys(PENDING_PREFIX + "*") == []

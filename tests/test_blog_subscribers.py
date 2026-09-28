"""Subscriber migration and delivery grouping stay independent of Flask."""

from blog_i18n import BLOG_LANGUAGES
from blog_subscribers import group_subscribers, normalize_subscribers


def test_legacy_subscribers_keep_slovenian_and_normalize_addresses():
    assert normalize_subscribers([" One@Example.com ", "TWO@example.com"]) == [
        {"email": "one@example.com", "language": "sl"},
        {"email": "two@example.com", "language": "sl"},
    ]


def test_mixed_records_preserve_first_duplicate_and_supported_languages():
    records = [
        {"email": "ONE@example.com", "language": "de"},
        "one@example.com",
        {"email": "two@example.com", "language": "unsupported"},
        {"email": "three@example.com"},
    ]
    assert normalize_subscribers(records) == [
        {"email": "one@example.com", "language": "de"},
        {"email": "two@example.com", "language": "sl"},
        {"email": "three@example.com", "language": "sl"},
    ]


def test_supported_languages_survive_normalization():
    records = [
        {"email": f"{language.lower()}@example.com", "language": language}
        for language in BLOG_LANGUAGES
    ]
    assert normalize_subscribers(records) == records


def test_invalid_records_are_ignored():
    assert normalize_subscribers(None) == []
    assert normalize_subscribers({"email": "one@example.com"}) == []
    assert normalize_subscribers([None, 5, {}, {"email": 5}, " "]) == []


def test_language_groups_do_not_duplicate_recipients():
    assert group_subscribers(
        [
            "one@example.com",
            {"email": "two@example.com", "language": "de"},
            {"email": "ONE@example.com", "language": "en"},
            {"email": "three@example.com", "language": "de"},
        ]
    ) == {
        "sl": ["one@example.com"],
        "de": ["two@example.com", "three@example.com"],
    }

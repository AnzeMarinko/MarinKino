"""Normalize legacy subscriber records and group localized notifications."""

from blog_i18n import normalize_language


def normalize_subscribers(subscribers):
    """Read old email lists without losing existing Slovenian subscriptions."""
    if not isinstance(subscribers, list):
        return []

    normalized = []
    seen = set()
    for subscriber in subscribers:
        if isinstance(subscriber, str):
            email = subscriber
            language = "sl"
        elif isinstance(subscriber, dict):
            email = subscriber.get("email")
            language = subscriber.get("language")
        else:
            continue
        if not isinstance(email, str):
            continue
        email = email.strip().casefold()
        if not email or email in seen:
            continue
        seen.add(email)
        normalized.append(
            {"email": email, "language": normalize_language(language)}
        )
    return normalized


def group_subscribers(subscribers):
    """Return language-specific BCC lists with each address appearing once."""
    groups = {}
    for subscriber in normalize_subscribers(subscribers):
        groups.setdefault(subscriber["language"], []).append(
            subscriber["email"]
        )
    return groups

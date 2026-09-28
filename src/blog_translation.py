"""Free Google website links for public blog content only."""

from urllib.parse import urlencode, urlsplit, urlunsplit

from blog_i18n import normalize_language


def translate_url(source_url, language):
    """Strip arbitrary query data and carry only the validated language."""
    language = normalize_language(language)
    parsed = urlsplit(source_url)
    source_url = urlunsplit(
        (parsed.scheme, parsed.netloc, parsed.path, "", "")
    )
    if language == "sl":
        return source_url
    source_url += "?" + urlencode({"lang": language})
    query = urlencode({"sl": "sl", "tl": language, "u": source_url})
    return f"https://translate.google.com/translate?{query}"

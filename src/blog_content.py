"""Cache immutable blog revisions; callers receive independent post objects."""

from copy import deepcopy
from functools import lru_cache
from pathlib import Path

from security_storage import read_json


@lru_cache(maxsize=4)
def _read_posts(path, revision):
    return read_json(path, {})


def load_posts(path):
    target = Path(path).absolute()
    try:
        stat = target.stat()
        revision = (stat.st_dev, stat.st_ino, stat.st_mtime_ns, stat.st_size)
    except FileNotFoundError:
        revision = None
    # Views add display fields and administrators mutate drafts. The cached
    # source must never acquire either change before an atomic file write.
    return deepcopy(_read_posts(str(target), revision))


@lru_cache(maxsize=64)
def render_post_content(content):
    """Cache only sanitized content, never sessions, CSRF or CSP nonces."""
    import markdown
    import nh3

    return nh3.clean(
        markdown.markdown(content, extensions=["extra", "codehilite"]),
        attributes={
            "a": {"href", "title"},
            "img": {"src", "alt", "title"},
            "*": {"class"},
        },
        url_schemes={"http", "https", "mailto"},
    )

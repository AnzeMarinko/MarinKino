"""Bounded, read-only log views shared with the installed host exporter."""

from __future__ import annotations

import json
import os
import re
import stat
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import quote, quote_plus

MAX_LOG_BYTES = 64 * 1024
MAX_LINES = 200
MAX_SNAPSHOT_BYTES = 2 * 1024 * 1024
HOST_SNAPSHOT = Path("/app/cache/host-status/overview.json")
SECRET_NAME = re.compile(
    r"token|secret|password|passwd|credential|(?:^|_)key$", re.I
)
ASSIGNMENT = re.compile(
    r"""(?i)(["']?\b(?:[\w.-]*(?:token|secret|password|passwd|credential|api[_-]?key|private[_-]?key)|FLASK_KEY)["']?\s*[:=]\s*)"""
    r"""(?:"[^"\n]*"|'[^'\n]*'|[^\s,;}]+)"""
)
QUERY_SECRET = re.compile(
    r"(?i)([?&](?:[\w-]*(?:token|secret|password|key)|code|signature|auth)\s*=)[^&#\s\"']+"
)


def secret_values(values):
    return tuple(
        value
        for name, value in values.items()
        if SECRET_NAME.search(name)
        and isinstance(value, str)
        and len(value) >= 4
    )


def redact(text, secrets=()):
    """Hide known credentials and recognizable secrets before publication."""
    for value in sorted(set(secrets), key=len, reverse=True):
        for encoded in {value, quote(value, safe=""), quote_plus(value)}:
            text = text.replace(encoded, "[SKRITO]")
    text = re.sub(
        r"-----BEGIN [^-]*PRIVATE KEY-----.*?"
        r"(?:-----END [^-]*PRIVATE KEY-----|\Z)",
        "[ZASEBNI KLJUČ SKRIT]",
        text,
        flags=re.S,
    )
    text = re.sub(r"AGE-SECRET-KEY-[A-Z0-9]+", "[KLJUČ AGE SKRIT]", text)
    text = re.sub(
        r"(?i)(authorization[\"']?\s*[:=]\s*[\"']?(?:bearer|basic)\s+)\S+",
        r"\1[SKRITO]",
        text,
    )
    text = ASSIGNMENT.sub(r"\1[SKRITO]", text)
    text = QUERY_SECRET.sub(r"\1[SKRITO]", text)
    text = re.sub(
        r"([a-z][a-z0-9+.-]*://)[^/\s@:]+:[^/\s@]+@",
        r"\1[SKRITO]@",
        text,
        flags=re.I,
    )
    text = re.sub(
        r"(/(?:password/(?:reset|setup)|blog/subscribe/confirm)/)[^/?\s\"']+",
        r"\1[SKRITO]",
        text,
    )
    text = re.sub(r"\x1b\[[0-?]*[ -/]*[@-~]", "", text)
    text = re.sub(
        r"[\x00-\x08\x0b-\x1f\x7f\u202a-\u202e\u2066-\u2069]", "", text
    )
    # Invalid UTF-8 and redaction can expand the bounded source bytes.
    return text.encode("utf-8")[-MAX_LOG_BYTES:].decode(
        "utf-8", errors="ignore"
    )


@contextmanager
def regular_file(path):
    """Reject links and special files, including parent components."""
    path = Path(path).absolute()
    if ".." in path.parts:
        raise ValueError("Parent traversal is not allowed")
    flags = os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW | os.O_CLOEXEC
    parent = os.open(path.anchor, flags)
    descriptor = None
    try:
        for component in path.parts[1:-1]:
            following = os.open(component, flags, dir_fd=parent)
            os.close(parent)
            parent = following
        descriptor = os.open(
            path.name,
            os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK | os.O_CLOEXEC,
            dir_fd=parent,
        )
        if not stat.S_ISREG(os.fstat(descriptor).st_mode):
            raise ValueError("Only regular log files are allowed")
        yield descriptor
    finally:
        if descriptor is not None:
            os.close(descriptor)
        os.close(parent)


def tail_text(payload):
    return "\n".join(
        payload.decode("utf-8", errors="replace").splitlines()[-MAX_LINES:]
    ).rstrip()


def file_entry(identifier, title, path, secrets=()):
    path = Path(path)
    entry = dict(
        id=identifier,
        title=title,
        filename=redact(path.name, secrets),
        available=False,
    )
    try:
        with regular_file(path) as descriptor:
            info = os.fstat(descriptor)
            offset = max(0, info.st_size - MAX_LOG_BYTES)
            payload = os.pread(descriptor, MAX_LOG_BYTES, offset)
            if offset:
                payload = (
                    payload.partition(b"\n")[2]
                    if b"\n" in payload
                    else payload
                )
        entry.update(
            available=True,
            modified_at=datetime.fromtimestamp(
                info.st_mtime, timezone.utc
            ).isoformat(),
            text=redact(tail_text(payload), secrets) or "Dnevnik je prazen.",
        )
    except (OSError, ValueError):
        entry["text"] = "Dnevnik trenutno ni na voljo."
    return entry


def host_snapshot(path=HOST_SNAPSHOT):
    """Validate bounded data without interpreting paths or commands."""
    try:
        with regular_file(path) as descriptor:
            payload = os.read(descriptor, MAX_SNAPSHOT_BYTES + 1)
        if len(payload) > MAX_SNAPSHOT_BYTES:
            raise ValueError("Snapshot exceeds limit")
        document = json.loads(payload)
        generated = datetime.fromisoformat(document["generated_at"])
        if generated.tzinfo is None:
            raise ValueError("Snapshot requires a timezone")
        entries = document["entries"]
        if not isinstance(entries, list) or len(entries) > 24:
            raise ValueError("Invalid source list")
        seen = {"app"}
        cleaned = []
        secrets = secret_values(os.environ)
        for item in entries:
            identifier = item["id"]
            if (
                not re.fullmatch(r"[a-z0-9-]{1,48}", identifier)
                or identifier in seen
            ):
                raise ValueError("Invalid or duplicate source")
            seen.add(identifier)
            cleaned.append(
                dict(
                    id=identifier,
                    title=redact(str(item["title"])[:100], secrets),
                    filename=redact(
                        str(item.get("filename", ""))[:200], secrets
                    ),
                    modified_at=str(item.get("modified_at", ""))[:64],
                    available=item.get("available") is True,
                    text=redact(
                        str(item["text"])[: MAX_LOG_BYTES * 2], secrets
                    ),
                )
            )
        return dict(
            generated_at=generated.isoformat(),
            entries=cleaned,
            stale=(datetime.now(timezone.utc) - generated).total_seconds()
            > 180,
        )
    except (OSError, ValueError, KeyError, TypeError, AttributeError):
        return dict(generated_at=None, entries=[], stale=True)

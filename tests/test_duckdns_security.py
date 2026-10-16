"""DuckDNS uses documented GET without exposing tokens in arguments/errors."""

import sys
import urllib.parse
import urllib.request
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = (
    (ROOT / "scripts/duckdns_refresh.sh")
    .read_text()
    .split("<<'PY'\n", 1)[1]
    .rsplit("\nPY", 1)[0]
)


def setup_request(tmp_path, monkeypatch):
    (tmp_path / ".env").write_text(
        "MAIN_DOMAIN=example.test\nWWW_DOMAIN=www.example.test\nDUCKDNS_DOMAIN=sample.duckdns.org\nDUCKDNS_TOKEN=private-test-token\n"
    )
    monkeypatch.setattr(
        sys, "argv", ["-", str(tmp_path), str(ROOT / "scripts")]
    )
    monkeypatch.setattr(sys, "path", list(sys.path))


def test_update_uses_https_get_and_subdomain_only(tmp_path, monkeypatch):
    setup_request(tmp_path, monkeypatch)

    def open_request(request, timeout):
        assert request.get_method() == "GET"
        assert timeout == 10
        parsed = urllib.parse.urlsplit(request.full_url)
        assert (
            parsed.scheme == "https" and parsed.hostname == "www.duckdns.org"
        )
        assert urllib.parse.parse_qs(parsed.query)["domains"] == ["sample"]
        assert "private-test-token" not in " ".join(sys.argv)

        class Response:
            def __enter__(self):
                return self

            def __exit__(self, *args):
                pass

            def read(self, size):
                return b"OK"

        return Response()

    monkeypatch.setattr(urllib.request, "urlopen", open_request)
    exec(compile(SCRIPT, "<duckdns>", "exec"), {})


def test_update_does_not_print_secret_when_request_fails(
    tmp_path, monkeypatch
):
    setup_request(tmp_path, monkeypatch)

    def fail(*args, **kwargs):
        raise OSError("private-test-token: private upstream details")

    monkeypatch.setattr(urllib.request, "urlopen", fail)
    with pytest.raises(SystemExit, match="DuckDNS request failed") as result:
        exec(compile(SCRIPT, "<duckdns>", "exec"), {})
    assert "private-test-token" not in str(result.value)

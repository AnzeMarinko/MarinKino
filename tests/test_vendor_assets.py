"""Offline supply-chain checks for the npm asset updater."""

import base64
import hashlib
import importlib.util
import io
import json
import tarfile
from pathlib import Path

import pytest

SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "vendor_assets.py"
SPEC = importlib.util.spec_from_file_location("vendor_assets", SCRIPT)
vendor = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(vendor)


def archive(files):
    buffer = io.BytesIO()
    with tarfile.open(fileobj=buffer, mode="w:gz") as stream:
        for name, content in files.items():
            member = tarfile.TarInfo(name)
            if isinstance(content, bytes):
                member.size = len(content)
                stream.addfile(member, io.BytesIO(content))
            else:
                member.type = tarfile.SYMTYPE
                member.linkname = content
                stream.addfile(member)
    return buffer.getvalue()


def integrity(payload):
    digest = base64.b64encode(hashlib.sha512(payload).digest()).decode()
    return f"sha512-{digest}"


@pytest.fixture
def source(monkeypatch):
    monkeypatch.setattr(
        vendor,
        "SPECS",
        {
            "bootstrap": (5, None, {"dist/test.js": "test.js"}),
        },
    )
    payload = archive({"package/dist/test.js": b"verified"})
    release = {
        "version": "5.3.1",
        "dist": {
            "tarball": "https://registry.npmjs.org/bootstrap/-/bootstrap-5.3.1.tgz",
            "integrity": integrity(payload),
        },
    }
    metadata = {
        "versions": {
            "5.3.1": release,
            "5.4.0-beta.1": release,
            "6.0.0": release,
            "5.2.0": release,
        }
    }

    def fetch(url, maximum, host, data=None):
        if url == vendor.OSV:
            queries = json.loads(data)["queries"]
            assert queries[0]["version"] == "5.3.1"
            return b'{"results": [{}]}'
        if url.endswith(".tgz"):
            return payload
        return json.dumps(metadata).encode()

    return fetch, payload, release


def test_refresh_locks_stable_major_and_verified_assets(tmp_path, source):
    fetch, _, release = source
    manifest = vendor.update_assets(tmp_path, refresh=True, fetch=fetch)
    assert manifest["packages"]["bootstrap"]["version"] == "5.3.1"
    assert (
        manifest["packages"]["bootstrap"]["integrity"]
        == release["dist"]["integrity"]
    )
    assert (tmp_path / "src/static/vendor/test.js").read_bytes() == b"verified"
    assert (
        vendor.update_assets(tmp_path, fetch=fetch)["sha256"]
        == manifest["sha256"]
    )


def test_security_maintained_deprecated_plyr_is_still_checked():
    release = {
        "deprecated": "Plyr 3 receives security updates only",
        "dist": {
            "tarball": "https://registry.npmjs.org/plyr/-/plyr-3.8.5.tgz",
            "integrity": "sha512-example",
        },
    }
    selected = vendor.select_release(
        "plyr",
        {
            "versions": {"3.8.4": release, "3.8.5": release},
        },
    )
    assert selected["version"] == "3.8.5"
    seen = []

    def advisories(url, maximum, host, data=None):
        seen.extend(json.loads(data)["queries"])
        return b'{"results": [{"vulns": [{"id": "TEST-PLYR"}]}]}'

    with pytest.raises(ValueError, match="TEST-PLYR"):
        vendor._check_advisories({"plyr": selected}, advisories)
    assert seen[0]["package"]["name"] == "plyr"


def test_license_and_copyright_texts_preserved_under_safe_name(source):
    assets = vendor.extract_assets(
        "bootstrap",
        archive(
            {
                "package/dist/test.js": b"verified",
                "package/LICENSE.md": b"MIT permission text",
                "package/dist/COPYRIGHT": b"Copyright authors",
                "package/irrelevant.md": b"ignore",
            }
        ),
    )
    assert assets["test.js"] == b"verified"
    assert b"MIT permission text" in assets["licenses/bootstrap.txt"]
    assert b"Copyright authors" in assets["licenses/bootstrap.txt"]
    assert len(assets) == 2


@pytest.mark.parametrize("bad", ["sha1-abcd", "sha512-!", "sha512-YQ=="])
def test_weak_or_malformed_integrity_rejected(bad):
    with pytest.raises(ValueError):
        vendor.verify_integrity(b"payload", bad)


@pytest.mark.parametrize(
    "name,content",
    [
        ("package/../../escape.js", b"escape"),
        ("/package/dist/test.js", b"absolute"),
        ("package/dist/link", "/etc/passwd"),
    ],
)
def test_archive_traversal_absolute_and_symlinks_rejected(
    name,
    content,
    source,
):
    with pytest.raises(ValueError):
        vendor.extract_assets("bootstrap", archive({name: content}))


def test_integrity_failure_preserves_installed_assets_and_manifest(
    tmp_path,
    source,
):
    fetch, payload, _ = source
    vendor.update_assets(tmp_path, refresh=True, fetch=fetch)
    manifest = (tmp_path / "configuration/vendor-assets.json").read_bytes()

    def corrupted(url, maximum, host, data=None):
        if url.endswith(".tgz"):
            return payload + b"tampered"
        return fetch(url, maximum, host, data=data)

    with pytest.raises(ValueError, match="integrity"):
        vendor.update_assets(tmp_path, refresh=True, fetch=corrupted)
    assert (
        tmp_path / "configuration/vendor-assets.json"
    ).read_bytes() == manifest
    assert (tmp_path / "src/static/vendor/test.js").read_bytes() == b"verified"


def test_known_advisory_blocks_refresh(tmp_path, source):
    fetch, _, _ = source

    def vulnerable(url, maximum, host, data=None):
        if url == vendor.OSV:
            return b'{"results": [{"vulns": [{"id": "TEST-ADVISORY"}]}]}'
        return fetch(url, maximum, host, data=data)

    with pytest.raises(ValueError, match="TEST-ADVISORY"):
        vendor.update_assets(tmp_path, refresh=True, fetch=vulnerable)
    assert not (tmp_path / "src/static/vendor/test.js").exists()


@pytest.mark.parametrize(
    "url",
    [
        "http://registry.npmjs.org/bootstrap",
        "https://registry.npmjs.org.evil.test/bootstrap",
        "https://evil.test/bootstrap",
        "https://user@registry.npmjs.org/bootstrap",
    ],
)
def test_untrusted_download_urls_rejected(url):
    with pytest.raises(ValueError):
        vendor._checked_url(url, "registry.npmjs.org")


def test_symlink_publish_directory_rejected(tmp_path, source):
    fetch, _, _ = source
    outside = tmp_path / "outside"
    outside.mkdir()
    static = tmp_path / "src/static"
    static.mkdir(parents=True)
    (static / "vendor").symlink_to(outside, target_is_directory=True)
    with pytest.raises(ValueError, match="symlink"):
        vendor.update_assets(tmp_path, refresh=True, fetch=fetch)
    assert not list(outside.iterdir())

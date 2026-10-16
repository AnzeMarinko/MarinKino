#!/usr/bin/env python3
"""Vendor reviewed npm assets without executing package installation hooks."""

from __future__ import annotations

import argparse
import base64
import binascii
import fcntl
import gzip
import hashlib
import hmac
import io
import json
import os
import re
import tarfile
import tempfile
import time
import urllib.parse
import urllib.request
from datetime import datetime, timezone
from pathlib import Path, PurePosixPath

REGISTRY = "https://registry.npmjs.org"
OSV = "https://api.osv.dev/v1/querybatch"
MAX_METADATA = 64 * 1024 * 1024
MAX_COMPRESSED = 64 * 1024 * 1024
MAX_EXPANDED = 128 * 1024 * 1024
MAX_ASSET = 16 * 1024 * 1024
MAX_LICENSE = 1024 * 1024
MAX_MEMBERS = 20_000
VERSION = re.compile(r"^(0|[1-9]\d*)\.(0|[1-9]\d*)\.(0|[1-9]\d*)$")
FONT_BASE = "fonts/fontawesome-webfont"
LICENSE_NAMES = {
    f"{name}{suffix}"
    for name in ("license", "licence", "copying", "copyright", "notice")
    for suffix in ("", ".md", ".txt", ".rst", ".markdown", "-mit", "-apache")
}

# Archive member -> published path. No archive-controlled path is extracted.
SPECS = {
    "bootstrap": (
        5,
        None,
        {
            "dist/css/bootstrap.min.css": "bootstrap.min.css",
            "dist/js/bootstrap.bundle.min.js": "bootstrap.bundle.min.js",
        },
    ),
    "bootstrap-icons": (
        1,
        None,
        {
            "font/bootstrap-icons.min.css": "bootstrap-icons.min.css",
            "font/fonts/bootstrap-icons.woff": "fonts/bootstrap-icons.woff",
            "font/fonts/bootstrap-icons.woff2": "fonts/bootstrap-icons.woff2",
        },
    ),
    "hls.js": (1, None, {"dist/hls.min.js": "hls.min.js"}),
    "plyr": (
        3,
        None,
        {
            "dist/plyr.min.js": "plyr.min.js",
            "dist/plyr.css": "plyr.css",
            "dist/plyr.svg": "plyr.svg",
        },
    ),
    "plotly.js-dist-min": (3, None, {"plotly.min.js": "plotly.min.js"}),
    "leaflet": (
        1,
        None,
        {
            "dist/leaflet.css": "leaflet.css",
            "dist/leaflet.js": "leaflet.js",
            **{
                f"dist/images/{name}.png": f"images/{name}.png"
                for name in (
                    "layers",
                    "layers-2x",
                    "marker-icon",
                    "marker-icon-2x",
                    "marker-shadow",
                )
            },
        },
    ),
    "easymde": (
        2,
        None,
        {
            "dist/easymde.min.css": "simplemde.min.css",
            "dist/easymde.min.js": "simplemde.min.js",
        },
    ),
    "marked": (16, None, {"lib/marked.umd.js": "marked.min.js"}),
    "dompurify": (3, None, {"dist/purify.min.js": "purify.min.js"}),
    "font-awesome": (
        4,
        7,
        {
            "css/font-awesome.min.css": "font-awesome.min.css",
            **{
                f"{FONT_BASE}.{extension}": f"{FONT_BASE}.{extension}"
                for extension in ("eot", "svg", "ttf", "woff", "woff2")
            },
        },
    ),
}


def _checked_url(url: str, host: str) -> str:
    parsed = urllib.parse.urlsplit(url)
    if (
        parsed.scheme != "https"
        or parsed.hostname != host
        or parsed.port not in (None, 443)
        or parsed.username is not None
        or parsed.password is not None
        or parsed.fragment
        or parsed.query
    ):
        raise ValueError(f"Untrusted download URL: {url}")
    return url


class _RestrictedRedirect(urllib.request.HTTPRedirectHandler):
    def __init__(self, host):
        self.host = host

    def redirect_request(self, req, fp, code, msg, headers, newurl):
        _checked_url(newurl, self.host)
        return super().redirect_request(req, fp, code, msg, headers, newurl)


def fetch_bytes(url, maximum, host, data=None):
    """Require TLS; bound redirects, response size and download time."""
    _checked_url(url, host)
    headers = {"User-Agent": "MarinKino-security-vendor/1"}
    if data is not None:
        headers["Content-Type"] = "application/json"
    request = urllib.request.Request(url, data=data, headers=headers)
    opener = urllib.request.build_opener(_RestrictedRedirect(host))
    started = time.monotonic()
    with opener.open(request, timeout=30) as response:
        length = response.headers.get("Content-Length")
        if length and int(length) > maximum:
            raise ValueError("Download exceeds size limit")
        result = bytearray()
        while chunk := response.read(
            min(64 * 1024, maximum + 1 - len(result))
        ):
            result.extend(chunk)
            if len(result) > maximum or time.monotonic() - started > 120:
                raise ValueError("Download exceeds size/time limit")
    return bytes(result)


def _version_tuple(version, package):
    match = VERSION.fullmatch(version)
    if not match:
        raise ValueError(f"Unsupported version for {package}: {version}")
    numbers = tuple(map(int, match.groups()))
    major, minor, _ = SPECS[package]
    if numbers[0] != major or (minor is not None and numbers[1] != minor):
        raise ValueError(
            f"Version outside reviewed range: {package}@{version}"
        )
    return numbers


def select_release(package, metadata):
    candidates = []
    for version, release in metadata.get("versions", {}).items():
        try:
            numbers = _version_tuple(version, package)
        except ValueError:
            continue
        if release.get("deprecated") and package != "plyr":
            continue
        candidates.append((numbers, version, release))
    if not candidates:
        raise ValueError(f"No stable release in reviewed range: {package}")
    _, version, release = max(candidates, key=lambda value: value[0])
    distribution = release["dist"]
    return {
        "version": version,
        "integrity": distribution["integrity"],
        "tarball": _checked_url(distribution["tarball"], "registry.npmjs.org"),
    }


def verify_integrity(payload, integrity):
    """Require npm's SHA-512 SRI; never fall back to SHA-1."""
    values = [
        item[7:] for item in integrity.split() if item.startswith("sha512-")
    ]
    if len(values) != 1:
        raise ValueError("Exactly one SHA-512 integrity digest is required")
    try:
        expected = base64.b64decode(values[0], validate=True)
    except (ValueError, binascii.Error) as error:
        raise ValueError("Malformed SHA-512 digest") from error
    if len(expected) != 64 or not hmac.compare_digest(
        hashlib.sha512(payload).digest(), expected
    ):
        raise ValueError("npm archive integrity verification failed")


def extract_assets(package, payload):
    """Read bounded archives and return only explicitly named regular files."""
    if len(payload) > MAX_COMPRESSED:
        raise ValueError("Compressed archive exceeds size limit")
    with gzip.GzipFile(fileobj=io.BytesIO(payload)) as compressed:
        expanded = compressed.read(MAX_EXPANDED + 1)
    if len(expanded) > MAX_EXPANDED:
        raise ValueError("Expanded archive exceeds size limit")
    wanted = {
        f"package/{key}": value for key, value in SPECS[package][2].items()
    }
    assets = {}
    licenses = []
    license_size = 0
    seen = set()
    with tarfile.open(fileobj=io.BytesIO(expanded), mode="r:") as archive:
        for index, member in enumerate(archive):
            path = PurePosixPath(member.name)
            if (
                index >= MAX_MEMBERS
                or path.is_absolute()
                or ".." in path.parts
                or "\\" in member.name
                or "\x00" in member.name
                or not path.parts
                or path.parts[0] != "package"
                or member.name in seen
                or not (member.isfile() or member.isdir())
            ):
                raise ValueError(f"Unsafe npm archive member: {member.name}")
            seen.add(member.name)
            is_license = (
                member.isfile() and path.name.casefold() in LICENSE_NAMES
            )
            if member.name not in wanted and not is_license:
                continue
            maximum = MAX_LICENSE if is_license else MAX_ASSET
            if not member.isfile() or member.size > maximum:
                raise ValueError(f"Invalid asset: {member.name}")
            stream = archive.extractfile(member)
            if stream is None:
                raise ValueError(f"Missing asset content: {member.name}")
            content = stream.read(maximum + 1)
            if len(content) != member.size or len(content) > maximum:
                raise ValueError(f"Truncated/oversized asset: {member.name}")
            if is_license:
                license_size += len(content)
                if license_size > 8 * MAX_LICENSE:
                    raise ValueError("Package license texts exceed size limit")
                heading = f"===== {member.name} =====\n".encode()
                licenses.append(heading + content + b"\n")
                if member.name not in wanted:
                    continue
            if package == "font-awesome" and member.name.endswith(".css"):
                content = content.replace(b"../fonts/", b"./fonts/")
            assets[wanted[member.name]] = content
    if licenses:
        assets[f"licenses/{package}.txt"] = b"\n".join(licenses)
    missing = set(wanted.values()) - assets.keys()
    if missing:
        raise ValueError(
            f"Missing {package} assets: {', '.join(sorted(missing))}"
        )
    return assets


def _check_advisories(packages, fetch):
    names = sorted(packages)
    queries = [
        {
            "package": {"name": name, "ecosystem": "npm"},
            "version": packages[name]["version"],
        }
        for name in names
    ]
    response = json.loads(
        fetch(
            OSV,
            MAX_METADATA,
            "api.osv.dev",
            data=json.dumps({"queries": queries}).encode(),
        )
    )
    results = response.get("results")
    if not isinstance(results, list) or len(results) != len(names):
        raise ValueError("Invalid OSV advisory response")
    problems = [
        f"{name}@{packages[name]['version']}: {vuln['id']}"
        for name, result in zip(names, results)
        for vuln in result.get("vulns", [])
    ]
    if problems:
        raise ValueError("Known npm vulnerabilities: " + "; ".join(problems))


def _target(project, relative):
    path = project / relative
    for item in (path, *path.parents):
        if item == project:
            break
        if item.is_symlink():
            raise ValueError(f"Refusing symlink destination: {item}")
    return path


def update_assets(project, refresh=False, fetch=fetch_bytes):
    project = Path(project).resolve(strict=True)
    configuration = _target(project, "configuration")
    configuration.mkdir(mode=0o755, exist_ok=True)
    lock_path = _target(project, "configuration/.vendor-assets.lock")
    descriptor = os.open(
        lock_path, os.O_CREAT | os.O_RDWR | os.O_NOFOLLOW, 0o600
    )
    try:
        os.fchmod(descriptor, 0o600)
        fcntl.flock(descriptor, fcntl.LOCK_EX)
        return _update_locked(project, refresh, fetch)
    finally:
        os.close(descriptor)


def _update_locked(project, refresh, fetch):
    manifest_path = _target(project, "configuration/vendor-assets.json")
    if refresh:
        packages = {
            name: select_release(
                name,
                json.loads(
                    fetch(
                        f"{REGISTRY}/{urllib.parse.quote(name, safe='')}",
                        MAX_METADATA,
                        "registry.npmjs.org",
                    )
                ),
            )
            for name in SPECS
        }
    else:
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        if manifest.get("schema") != 1 or set(manifest["packages"]) != set(
            SPECS
        ):
            raise ValueError("Unrecognized vendor manifest; use --refresh")
        packages = manifest["packages"]
    for name, package in packages.items():
        _version_tuple(package["version"], name)
        _checked_url(package["tarball"], "registry.npmjs.org")
    _check_advisories(packages, fetch)

    # Nothing published changes until every archive and advisory check passes.
    with tempfile.TemporaryDirectory(
        prefix=".vendor-assets-", dir=project
    ) as td:
        stage = Path(td)
        hashes = {}
        for name, package in packages.items():
            payload = fetch(
                package["tarball"], MAX_COMPRESSED, "registry.npmjs.org"
            )
            verify_integrity(payload, package["integrity"])
            for relative, content in extract_assets(name, payload).items():
                if relative in hashes:
                    raise ValueError(
                        f"Duplicate asset destination: {relative}"
                    )
                destination = stage / "assets" / relative
                destination.parent.mkdir(parents=True, exist_ok=True)
                destination.write_bytes(content)
                destination.chmod(0o644)
                hashes[relative] = hashlib.sha256(content).hexdigest()
        manifest = {
            "schema": 1,
            "updated_at": datetime.now(timezone.utc).isoformat(),
            "packages": packages,
            "sha256": hashes,
        }
        staged_manifest = stage / "manifest.json"
        staged_manifest.write_text(
            json.dumps(manifest, indent=2) + "\n", encoding="utf-8"
        )
        staged_manifest.chmod(0o644)
        targets = {
            relative: _target(project, f"src/static/vendor/{relative}")
            for relative in hashes
        }
        for relative, destination in targets.items():
            destination.parent.mkdir(parents=True, exist_ok=True)
            os.replace(stage / "assets" / relative, destination)
        os.replace(staged_manifest, manifest_path)
    return manifest


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--project", type=Path, default=Path.cwd())
    parser.add_argument(
        "--refresh",
        action="store_true",
        help="Refresh reviewed version ranges and manifest",
    )
    args = parser.parse_args(argv)
    try:
        manifest = update_assets(args.project, refresh=args.refresh)
    except (OSError, ValueError, KeyError, tarfile.TarError) as error:
        parser.exit(1, f"Vendor update failed: {error}\n")
    print(
        f"Vendored {len(manifest['packages'])} packages, "
        f"{len(manifest['sha256'])} verified assets"
    )


if __name__ == "__main__":
    main()

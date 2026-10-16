#!/usr/bin/env python3
"""Validate deployment data and generate scoped host/container configuration.

Only the standard library is required. No .env content is evaluated as code.
The shell orchestrator validates staged Nginx configuration before promotion.
"""

from __future__ import annotations

import argparse
import glob
import ipaddress
import json
import os
import re
import secrets
import selectors
import shutil
import sqlite3
import stat
import subprocess
import sys
import time
from contextlib import contextmanager
from pathlib import Path
from urllib.parse import urlsplit

MAX_METADATA_BYTES = 32 * 1024 * 1024
MAX_ROUTE_BYTES = 1024 * 1024
MAX_ROUTE_RECORDS = 4096
ROUTE_TIMEOUT = 5
FIREWALL_TABLE = "marinkino_security"
BRIDGES = ("mk-edge", "mk-egress", "mk-backend")
PUBLIC_DIRS = ("music", "radio-stories", "movies", "memes", "blog_images")
MEDIA_SUFFIXES = {
    ".mp3",
    ".m4a",
    ".wav",
    ".aac",
    ".m3u8",
    ".m4s",
    ".ts",
    ".mp4",
    ".webm",
    ".mov",
    ".mkv",
    ".jpg",
    ".jpeg",
    ".png",
    ".gif",
    ".webp",
    ".avif",
    ".ico",
    ".vtt",
    ".srt",
    ".zip",
}
KEY_PATTERN = re.compile(r"[A-Za-z_][A-Za-z0-9_]*\Z")
DOMAIN_PATTERN = re.compile(
    r"(?=.{1,253}\Z)(?:[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?\.)+"
    r"[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?\Z"
)


def checked_path(path: Path) -> Path:
    """Reject symlink components and special files before privileged writes."""
    path = path.absolute()
    for component in (path, *path.parents):
        if component.is_symlink():
            raise ValueError("A managed path contains a symlink")
    if path.exists() and not (path.is_file() or path.is_dir()):
        raise ValueError("A managed path is not a regular file or directory")
    return path


def project_path(value: str | Path) -> Path:
    path = Path(value).resolve(strict=True)
    if not path.is_dir() or any(char in str(path) for char in "\r\n\0"):
        raise ValueError("Invalid project directory")
    return path


def atomic_write(path: Path, content: str | bytes, mode: int = 0o600) -> None:
    path = checked_path(path)
    with directory_descriptor(path.parent, create=True) as parent:
        temporary = f".{path.name}.{secrets.token_hex(12)}"
        descriptor = os.open(
            temporary,
            os.O_WRONLY
            | os.O_CREAT
            | os.O_EXCL
            | os.O_NOFOLLOW
            | os.O_CLOEXEC,
            mode,
            dir_fd=parent,
        )
        try:
            with os.fdopen(descriptor, "wb") as stream:
                os.fchmod(stream.fileno(), mode)
                stream.write(
                    content.encode() if isinstance(content, str) else content
                )
                stream.flush()
                os.fsync(stream.fileno())
            os.replace(
                temporary,
                path.name,
                src_dir_fd=parent,
                dst_dir_fd=parent,
            )
        finally:
            try:
                os.unlink(temporary, dir_fd=parent)
            except FileNotFoundError:
                pass


def parse_env(text: str) -> dict[str, str]:
    """Read dotenv lines, preserving literal dollars and backticks."""
    values = {}
    for number, raw in enumerate(text.splitlines(), 1):
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        if line.startswith("export "):
            line = line[7:].lstrip()
        key, separator, value = line.partition("=")
        key, value = key.strip(), value.strip()
        if not separator or not KEY_PATTERN.fullmatch(key) or key in values:
            raise ValueError(f"Invalid or duplicate .env key on line {number}")
        if value.startswith(("'", '"')):
            quote, result, index = value[0], [], 1
            while index < len(value):
                char = value[index]
                if char == quote:
                    tail = value[index + 1 :].strip()
                    if tail and not tail.startswith("#"):
                        raise ValueError(
                            f"Invalid .env quoting on line {number}"
                        )
                    value = "".join(result)
                    break
                if char == "\\" and index + 1 < len(value):
                    index += 1
                    escaped = value[index]
                    if quote == "'":
                        # Compose only removes backslashes escaping the quote;
                        # it preserves all other single-quoted backslashes.
                        result.append(
                            "'" if escaped == "'" else "\\" + escaped
                        )
                    else:
                        result.append(
                            {
                                "n": "\n",
                                "r": "\r",
                                "t": "\t",
                                "\\": "\\",
                                '"': '"',
                                "$": "$",
                            }.get(escaped, "\\" + escaped)
                        )
                else:
                    result.append(char)
                index += 1
            else:
                raise ValueError(f"Unclosed .env quote on line {number}")
        else:
            value = re.split(r"\s+#", value, maxsplit=1)[0].rstrip()
        if "\0" in value:
            raise ValueError(f"Invalid .env value on line {number}")
        values[key] = value
    return values


def read_env(project: Path) -> dict[str, str]:
    path = checked_path(project / ".env")
    if not path.is_file() or path.stat().st_size > 1024 * 1024:
        raise ValueError("A regular .env file of at most 1 MiB is required")
    return parse_env(path.read_text(encoding="utf-8-sig"))


def validate_domain(value: str, name: str) -> str:
    domain = value.lower()
    if not DOMAIN_PATTERN.fullmatch(domain):
        raise ValueError(f"{name} must be a plain DNS hostname")
    return domain


def deployment_config(project: Path) -> dict[str, str]:
    values = read_env(project)
    for key in ("MAIN_DOMAIN", "WWW_DOMAIN"):
        values[key] = validate_domain(values.get(key, ""), key)
    if values.get("DUCKDNS_DOMAIN"):
        values["DUCKDNS_DOMAIN"] = validate_domain(
            values["DUCKDNS_DOMAIN"],
            "DUCKDNS_DOMAIN",
        )
    email = values.get("GMAIL_USERNAME", "")
    if email:
        local, separator, domain = email.rpartition("@")
        if not separator or not re.fullmatch(r"[A-Za-z0-9._%+\-]+", local):
            raise ValueError("GMAIL_USERNAME must be an email address")
        validate_domain(domain, "GMAIL_USERNAME domain")
    base = values.get("PUBLIC_BASE_URL") or f"https://{values['WWW_DOMAIN']}"
    parsed = urlsplit(base)
    if (
        any(character.isspace() for character in base)
        or parsed.scheme != "https"
        or parsed.hostname != values["WWW_DOMAIN"]
        or parsed.port not in (None, 443)
        or parsed.username is not None
        or parsed.password is not None
        or parsed.path not in ("", "/")
        or parsed.query
        or parsed.fragment
    ):
        raise ValueError("PUBLIC_BASE_URL must be the canonical HTTPS origin")
    values["PUBLIC_BASE_URL"] = base.rstrip("/")
    return values


def env_literal(value: str) -> str:
    """Single quotes prevent Compose from interpolating credential dollars."""
    if not isinstance(value, str) or any(
        ord(character) < 32
        or ord(character) == 127
        or character in "\x85\u2028\u2029"
        for character in value
    ):
        raise ValueError(
            "Managed .env values must not contain control characters"
        )
    if value.endswith("\\"):
        raise ValueError("Managed .env values must not end with a backslash")
    for match in re.finditer(r"(\\+)'", value):
        if len(match[1]) % 2:
            raise ValueError(
                "Unsupported backslash before a managed .env quote"
            )
    return "'" + value.replace("'", "\\'") + "'"


def update_env(project: Path, updates: dict[str, str]) -> None:
    path = project / ".env"
    original = checked_path(path).stat()
    lines = path.read_text(encoding="utf-8-sig").splitlines()
    if any(not KEY_PATTERN.fullmatch(key) for key in updates):
        raise ValueError("Invalid managed .env key")
    pending = {key: env_literal(value) for key, value in updates.items()}
    for index, line in enumerate(lines):
        match = re.match(
            r"\s*(?:export\s+)?([A-Za-z_][A-Za-z0-9_]*)\s*=", line
        )
        if match and match[1] in pending:
            key = match[1]
            lines[index] = f"{key}={pending.pop(key)}"
    lines.extend(f"{key}={value}" for key, value in pending.items())
    atomic_write(path, "\n".join(lines) + "\n")
    if os.geteuid() == 0:
        set_permissions(path, 0o600, original.st_uid, original.st_gid)


@contextmanager
def directory_descriptor(path: Path, create=False, mode=0o755):
    """Walk from / using directory handles; never follow any symlink."""
    path = path.absolute()
    if ".." in path.parts:
        raise ValueError("Parent traversal is not allowed in managed paths")
    flags = os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW | os.O_CLOEXEC
    descriptor = os.open(path.anchor, flags)
    try:
        for component in path.parts[1:]:
            if create:
                try:
                    os.mkdir(component, mode=mode, dir_fd=descriptor)
                except FileExistsError:
                    pass
            following = os.open(component, flags, dir_fd=descriptor)
            os.close(descriptor)
            descriptor = following
        yield descriptor
    finally:
        os.close(descriptor)


@contextmanager
def safe_descriptor(path: Path, regular=False):
    """Pin the final inode as well as every parent before privileged work."""
    path = path.absolute()
    with directory_descriptor(path.parent) as parent:
        descriptor = os.open(
            path.name,
            os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK | os.O_CLOEXEC,
            dir_fd=parent,
        )
        try:
            info = os.fstat(descriptor)
            if not stat.S_ISREG(info.st_mode) and (
                regular or not stat.S_ISDIR(info.st_mode)
            ):
                raise ValueError(
                    "Managed paths must be regular files or directories"
                )
            yield descriptor
        finally:
            os.close(descriptor)


def descriptor_permissions(descriptor, mode, uid=None, gid=None):
    info = os.fstat(descriptor)
    if stat.S_IMODE(info.st_mode) != mode:
        os.fchmod(descriptor, mode)
    desired = (
        info.st_uid if uid is None else uid,
        info.st_gid if gid is None else gid,
    )
    if (info.st_uid, info.st_gid) != desired:
        os.fchown(descriptor, *desired)


def set_permissions(path: Path, mode: int, uid=None, gid=None) -> None:
    with safe_descriptor(path) as descriptor:
        descriptor_permissions(descriptor, mode, uid, gid)


def ensure_directory(path: Path, mode: int, uid: int, gid: int) -> None:
    with directory_descriptor(path, create=True, mode=mode) as descriptor:
        descriptor_permissions(descriptor, mode, uid, gid)


def walk_regular(root: Path):
    """Yield regular files; reject links without opening their targets."""
    checked_path(root)
    if not root.exists():
        return
    for directory, subdirs, files in os.walk(root, followlinks=False):
        parent = Path(directory)
        for name in subdirs:
            checked_path(parent / name)
        for name in files:
            path = checked_path(parent / name)
            if not path.is_file():
                raise ValueError("A runtime tree contains a special file")
            yield path


def prepare(project: Path, uid: int, gid: int) -> None:
    if not (0 < uid < 2**31 and 0 < gid < 2**31):
        raise ValueError("Application UID and GID must be nonzero integers")
    values = deployment_config(project)
    key = values.get("FLASK_KEY", "")
    placeholders = (
        "to_pomaga",
        "changeme",
        "change-me",
        "change_me",
        "placeholder",
        "replace",
        "example",
        "your-secret",
        "your_secret",
    )
    try:
        env_literal(key)
        representable_key = True
    except ValueError:
        representable_key = False
    if (
        not representable_key
        or len(key) < 32
        or any(marker in key.lower() for marker in placeholders)
    ):
        key = secrets.token_urlsafe(48)
    update_env(
        project,
        {
            "FLASK_KEY": key,
            "MARINKINO_UID": str(uid),
            "MARINKINO_GID": str(gid),
            "PUBLIC_BASE_URL": values["PUBLIC_BASE_URL"],
        },
    )
    set_permissions(project / ".env", 0o600, uid, gid)
    credentials = project / "credentials"
    if credentials.exists():
        ensure_directory(credentials, 0o700, uid, gid)
        for path in walk_regular(credentials):
            set_permissions(path, 0o600, uid, gid)
        for directory, _, _ in os.walk(credentials, followlinks=False):
            set_permissions(Path(directory), 0o700, uid, gid)
    for name in ("data", "cache"):
        ensure_directory(project / name, 0o755, uid, gid)
    data = project / "data"
    for path in data.iterdir():
        if path.is_symlink():
            raise ValueError("Runtime data must not contain symlinks")
        if path.is_file():
            set_permissions(path, 0o600, uid, gid)
    for name in PUBLIC_DIRS:
        root = data / name
        ensure_directory(root, 0o755, uid, gid)
        for path in walk_regular(root):
            public = path.suffix.lower() in MEDIA_SUFFIXES
            if public:
                # Media can be terabytes; do not recursively reassign files.
                set_permissions(path, 0o644)
            else:
                set_permissions(path, 0o600, uid, gid)
        for directory, _, _ in os.walk(root, followlinks=False):
            set_permissions(Path(directory), 0o755, uid, gid)
    albums = data / "users-music-albums"
    ensure_directory(albums, 0o700, uid, gid)
    for path in walk_regular(albums):
        set_permissions(path, 0o600, uid, gid)
    for name, mode in (
        ("downloads", 0o755),
        ("logs", 0o750),
        ("logs/server", 0o750),
        ("logs/nginx", 0o750),
        ("logs/security", 0o750),
    ):
        ensure_directory(project / "cache" / name, mode, uid, gid)
    for name in ("server", "nginx", "security"):
        for path in walk_regular(project / "cache/logs" / name):
            set_permissions(path, 0o640, uid, gid)
    # Nginx's root master opens its bind-mounted logs before dropping workers.
    nginx_uid, nginx_gid = (0, 0) if os.geteuid() == 0 else (uid, gid)
    set_permissions(project / "cache/logs/nginx", 0o755, nginx_uid, nginx_gid)
    for name in ("nginx/access.log", "nginx/error.log", "server/server.log"):
        path = project / "cache/logs" / name
        checked_path(path)
        if not path.exists():
            atomic_write(path, b"", 0o640)
        owner = (
            (nginx_uid, nginx_gid) if name.startswith("nginx/") else (uid, gid)
        )
        set_permissions(path, 0o640, *owner)


def security_headers(tls: bool = False) -> str:
    headers = (
        'add_header X-Content-Type-Options "nosniff" always;',
        'add_header X-Frame-Options "SAMEORIGIN" always;',
        'add_header Referrer-Policy $mk_referrer_policy always;',
        'add_header Permissions-Policy "camera=(), microphone=(), '
        'geolocation=(self)" always;',
        "add_header Content-Security-Policy \"base-uri 'self'; "
        "object-src 'none'; "
        "frame-ancestors 'self'; form-action 'self'\" always;",
    )
    if tls:
        headers += (
            'add_header Strict-Transport-Security "max-age=31536000; '
            'includeSubDomains" always;',
        )
    return "\n    ".join(headers)


def render_nginx(values: dict[str, str], bootstrap: bool = False) -> str:
    main, www = values["MAIN_DOMAIN"], values["WWW_DOMAIN"]
    names = " ".join(
        dict.fromkeys(
            filter(None, (main, www, values.get("DUCKDNS_DOMAIN"))),
        )
    )
    common = """# Generated by security_config.py; stage and nginx -t first.
server_tokens off;
client_max_body_size 64k;
client_header_timeout 10s;
client_body_timeout 30s;
send_timeout 30s;
reset_timedout_connection on;
autoindex off;
map $upstream_http_referrer_policy $mk_referrer_policy {
    default $upstream_http_referrer_policy;
    "" same-origin;
}
log_format marinkino '$remote_addr - $remote_user [$time_local] "$request" '
                     '$status $body_bytes_sent "$http_referer" '
                     '"$http_user_agent"';
access_log /var/log/nginx/access.log marinkino;
error_log /var/log/nginx/error.log warn;
limit_req_zone $binary_remote_addr zone=mk_site:10m rate=20r/s;
limit_req_zone $binary_remote_addr zone=mk_auth:10m rate=10r/m;
limit_req_zone $binary_remote_addr zone=mk_api:10m rate=5r/s;
limit_conn_zone $binary_remote_addr zone=mk_connections:10m;
map $request_method $mk_upload_key {
    default "";
    POST $binary_remote_addr;
}
limit_req_zone $mk_upload_key zone=mk_upload:1m rate=1r/m;
limit_req_zone $mk_upload_key zone=mk_upload_preview:1m rate=12r/m;
limit_conn_zone $mk_upload_key zone=mk_upload_connections:1m;
limit_req_status 429;
limit_conn_status 429;
proxy_connect_timeout 5s;
proxy_read_timeout 60s;
proxy_send_timeout 60s;
proxy_request_buffering on;
proxy_buffering on;
proxy_hide_header X-Powered-By;
proxy_hide_header Referrer-Policy;
proxy_set_header Host $host;
proxy_set_header X-Real-IP $remote_addr;
proxy_set_header X-Forwarded-For $remote_addr;
proxy_set_header X-Forwarded-Proto $scheme;
proxy_set_header Forwarded "";
proxy_http_version 1.1;
proxy_set_header Connection "";
server {
    keepalive_timeout 20s;
    listen 80 default_server;
    listen [::]:80 default_server;
    server_name _;
    return 444;
}
"""
    acme = """    location ^~ /.well-known/acme-challenge/ {
        root /var/www/certbot;
        default_type text/plain;
        try_files $uri =404;
    }
"""
    common += (
        "server {\n    keepalive_timeout 20s;\n"
        "    listen 80;\n    listen [::]:80;\n"
        f"    server_name {names};\n    {security_headers()}\n" + acme
    )
    if bootstrap:
        return (
            common
            + '    location / { return 200 "Certificate setup\\n"; }\n}\n'
        )
    common += (
        f"    location / {{ return 301 https://{www}$request_uri; }}\n}}\n"
    )
    certificate = (
        f"    ssl_certificate /etc/letsencrypt/live/{main}/fullchain.pem;\n"
        f"    ssl_certificate_key /etc/letsencrypt/live/{main}/privkey.pem;\n"
        "    ssl_protocols TLSv1.2 TLSv1.3;\n"
        "    ssl_session_cache shared:mk_tls:10m;\n"
        "    ssl_session_timeout 1d;\n"
        "    ssl_session_tickets off;\n"
    )
    common += """server {
    keepalive_timeout 20s;
    listen 443 ssl default_server;
    listen [::]:443 ssl default_server;
    server_name _;
    ssl_reject_handshake on;
    return 444;
}
"""
    redirects = " ".join(name for name in names.split() if name != www)
    if redirects:
        common += (
            "server {\n    keepalive_timeout 20s;\n"
            "    listen 443 ssl;\n    listen [::]:443 ssl;\n"
            f"    server_name {redirects};\n"
            + certificate
            + f"    {security_headers(True)}\n"
            + f"    return 301 https://{www}$request_uri;\n}}\n"
        )
    common += (
        "server {\n    keepalive_timeout 20s;\n"
        "    listen 443 ssl;\n    listen [::]:443 ssl;\n"
        f"    server_name {www};\n"
        + certificate
        + f"    {security_headers(True)}\n"
        + "    limit_conn mk_connections 40;\n"
        + "    location ~ (^|/)\\.(?!well-known/) { return 404; }\n"
        + "    location ~* \\.(?:env|json|sqlite3?|db|lock|py|sh|pem|key)"
        "(?:$|/) { return 404; }\n"
    )
    proxy = "proxy_pass http://unix:/run/marinkino/app.sock:;"
    common += (
        "    location ~ ^/admin/blog/image-preview/?$ {\n"
        "        client_max_body_size 40m;\n"
        "        limit_req zone=mk_upload_preview burst=10 nodelay;\n"
        "        limit_conn mk_upload_connections 1;\n"
        f"        {proxy}\n    }}\n"
        "    location ~ ^/admin/blog/(?:new|edit/[^/]+)/?$ {\n"
        "        client_max_body_size 40m;\n"
        "        limit_req zone=mk_upload burst=1 nodelay;\n"
        "        limit_conn mk_upload_connections 1;\n"
        f"        {proxy}\n    }}\n"
        "    location ~ ^/(?:login|forgot-password|reset-password|"
        "password/(?:change|forgot|reset))(?:/|$) {\n"
        "        limit_req zone=mk_auth burst=10 nodelay;\n"
        "        client_max_body_size 16k;\n"
        f"        {proxy}\n    }}\n"
        "    location ^~ /movies/download/ {\n"
        "        limit_req zone=mk_api burst=2 nodelay;\n"
        "        proxy_read_timeout 1900s;\n"
        f"        {proxy}\n    }}\n"
        "    location ~ ^/(?:api/|weather/(?:api|current-location)|"
        "blog/subscribe|csrf-token|music/(?:recommendation|session-playlist|"
        "private-albums)|movies/(?:page|rate|recommend|video-progress|"
        "progress-change|add-|edit-|delete-|get-comments|admin-comment)) {\n"
        "        limit_req zone=mk_api burst=20 nodelay;\n"
        f"        {proxy}\n    }}\n"
        "    location ~ ^/(?:movies/file|music/(?:file|hls)|"
        "radio-stories/(?:file|hls)|memes/file)/ {\n"
        "        limit_req zone=mk_site burst=80 nodelay;\n"
        f"        {proxy}\n    }}\n"
        "    location / {\n"
        "        limit_req zone=mk_site burst=40 nodelay;\n"
        f"        {proxy}\n    }}\n"
    )
    media = {
        "music": (
            "music_data",
            "mp3|m4a|wav|aac|m3u8|m4s|ts|mp4|jpg|jpeg|png|webp",
        ),
        "radio_stories": (
            "radio_stories_data",
            "mp3|m4a|wav|aac|m3u8|m4s|ts|mp4|jpg|jpeg|png|webp",
        ),
        "movies": ("movies_data", "mp4|m3u8|m4s|ts|vtt|srt|jpg|jpeg|png|webp"),
        "memes": ("memes_data", "mp4|webm|mov|jpg|jpeg|png|gif|webp|avif"),
        "blog_images": ("blog_images_data", "jpg|jpeg|png|gif|webp|avif"),
        "downloads": ("downloads_data", "zip"),
    }
    for name, (directory, suffixes) in media.items():
        common += (
            f"    location ^~ /protected_{name}/ {{\n"
            "        internal;\n"
            f"        alias /{directory}/;\n"
            "        disable_symlinks on;\n"
            f"        if ($uri !~* \\.({suffixes})$) {{ return 404; }}\n"
            "        limit_conn mk_connections 12;\n"
            "        max_ranges 1;\n"
            "        types {\n"
            "            application/vnd.apple.mpegurl m3u8;\n"
            "            video/mp2t ts;\n"
            "            video/iso.segment m4s;\n"
            "            video/mp4 mp4;\n"
            "            video/webm webm;\n"
            "            audio/mpeg mp3;\n"
            "            audio/mp4 m4a;\n"
            "            audio/wav wav;\n"
            "            audio/aac aac;\n"
            "            image/jpeg jpg jpeg;\n"
            "            image/png png;\n"
            "            image/gif gif;\n"
            "            image/webp webp;\n"
            "            image/avif avif;\n"
            "            text/vtt vtt;\n"
            "            text/plain srt;\n"
            "            application/zip zip;\n"
            "        }\n"
            "        default_type application/octet-stream;\n"
            "    }\n"
        )
    return common + "}\n"


def management_networks(values: dict[str, str], connection: str = ""):
    raw = values.get("MARINKINO_MGMT_CIDRS", "")
    networks = [
        ipaddress.ip_network(value, strict=False)
        for value in (
            re.split(r"[\s,]+", raw.strip())
            if raw.strip()
            else ["10.0.0.0/8", "172.16.0.0/12", "192.168.0.0/16", "fc00::/7"]
        )
    ]
    if any(network.prefixlen == 0 for network in networks):
        raise ValueError(
            "SSH management CIDRs must not allow the entire Internet"
        )
    if connection:
        source = ipaddress.ip_address(connection.split()[0])
        networks.append(
            ipaddress.ip_network(
                f"{source}/{source.max_prefixlen}",
                strict=False,
            )
        )
    return list(
        ipaddress.collapse_addresses(
            network for network in networks if network.version == 4
        )
    ) + list(
        ipaddress.collapse_addresses(
            network for network in networks if network.version == 6
        )
    )


def ssh_ports() -> list[int]:
    result = subprocess.run(
        [shutil.which("sshd") or "/usr/sbin/sshd", "-T"],
        check=True,
        capture_output=True,
        text=True,
        timeout=15,
    )
    ports = sorted(
        {
            int(line.split()[1])
            for line in result.stdout.splitlines()
            if line.startswith("port ")
        }
    )
    if not ports or any(not 0 < port < 65536 for port in ports):
        raise ValueError("Could not determine active SSH ports")
    return ports


def resolver_addresses() -> list[str]:
    addresses = []
    for line in Path("/etc/resolv.conf").read_text().splitlines():
        parts = line.split()
        if len(parts) >= 2 and parts[0] == "nameserver":
            address = ipaddress.ip_address(parts[1])
            if not address.is_loopback:
                addresses.append(str(address))
    return addresses


def _route_records(command):
    """Read bounded JSON from iproute2 without buffering arbitrary output."""
    payload = bytearray()
    deadline = time.monotonic() + ROUTE_TIMEOUT
    with subprocess.Popen(
        command,
        stdout=subprocess.PIPE,
        stderr=subprocess.DEVNULL,
    ) as process:
        try:
            with selectors.DefaultSelector() as selector:
                selector.register(process.stdout, selectors.EVENT_READ)
                while True:
                    remaining = deadline - time.monotonic()
                    if remaining <= 0 or not selector.select(remaining):
                        raise subprocess.TimeoutExpired(command, ROUTE_TIMEOUT)
                    chunk = os.read(
                        process.stdout.fileno(),
                        min(65536, MAX_ROUTE_BYTES + 1 - len(payload)),
                    )
                    if not chunk:
                        break
                    payload.extend(chunk)
                    if len(payload) > MAX_ROUTE_BYTES:
                        raise ValueError(
                            "Connected route output exceeds limit"
                        )
            process.wait(timeout=max(0.01, deadline - time.monotonic()))
            if process.returncode:
                raise subprocess.CalledProcessError(
                    process.returncode, command
                )
        except BaseException:
            process.kill()
            process.wait()
            raise
    records = json.loads(payload)
    if not isinstance(records, list) or len(records) > MAX_ROUTE_RECORDS:
        raise ValueError("Invalid or excessive connected route records")
    return records


def connected_networks():
    """Find on-link LAN prefixes, including publicly numbered IPv4/IPv6."""
    networks = set()
    for family, command in (
        (4, ["ip", "-j", "-4", "route", "show", "scope", "link"]),
        (6, ["ip", "-j", "-6", "route", "show"]),
    ):
        for route in _route_records(command):
            if not isinstance(route, dict):
                continue
            device = route.get("dev")
            if (
                not isinstance(device, str)
                or not device
                or device in {"lo", "docker0"}
                or device.startswith(("br-", "mk-"))
                or "gateway" in route
                or "via" in route
                or route.get("nexthops")
                or route.get("multipath")
                or route.get("type", "unicast") != "unicast"
            ):
                continue
            if not isinstance(route.get("dst"), str):
                continue
            try:
                network = ipaddress.ip_network(
                    route.get("dst", ""), strict=False
                )
            except (TypeError, ValueError):
                continue
            if network.version != family or network.prefixlen == 0:
                continue
            networks.add(network)
            if len(networks) > 256:
                raise ValueError("Too many connected LAN networks")
    return sorted(
        networks,
        key=lambda net: (
            net.version,
            int(net.network_address),
            net.prefixlen,
        ),
    )


def render_firewall(values, ports, connection="", resolvers=(), connected=()):
    networks = management_networks(values, connection)
    connected = tuple(connected)
    if connection:
        parts = connection.split()
        if len(parts) == 4 and parts[3].isdigit():
            ports = sorted({*ports, int(parts[3])})
    if not ports or any(not 0 < port < 65536 for port in ports):
        raise ValueError("Invalid SSH listening port")
    port_set = ", ".join(str(port) for port in ports)
    bridge_set = ", ".join(json.dumps(bridge) for bridge in BRIDGES)
    rules = [
        f"table inet {FIREWALL_TABLE} {{",
        "    chain input {",
        "        type filter hook input priority -5; policy drop;",
        "        ct state invalid drop",
        "        ct state established,related accept",
        '        iifname "lo" accept',
        f"        iifname {{ {bridge_set} }} drop",
        "        meta l4proto icmp accept",
        "        meta l4proto ipv6-icmp accept",
        "        udp sport 67 udp dport 68 accept",
        "        udp sport 547 udp dport 546 accept",
    ]
    for version, selector in ((4, "ip"), (6, "ip6")):
        allowed = ", ".join(
            str(network) for network in networks if network.version == version
        )
        if allowed:
            rules.append(
                f"        {selector} saddr {{ {allowed} }} tcp dport "
                f"{{ {port_set} }} ct state new accept"
            )
    rules += [
        "        tcp dport { 80, 443 } ct state new accept",
        "    }",
        "    chain forward {",
        "        type filter hook forward priority -5; policy accept;",
        "        ct state established,related accept",
    ]
    for bridge in BRIDGES:
        rules.append(f'        iifname "{bridge}" oifname "{bridge}" accept')
    edge_set = '"mk-edge", "mk-egress"'
    for resolver in resolvers:
        address = ipaddress.ip_address(resolver)
        selector = "ip" if address.version == 4 else "ip6"
        rules.append(
            f"        iifname {{ {edge_set} }} {selector} daddr {address} "
            "meta l4proto { tcp, udp } th dport 53 accept"
        )
    for version, family in ((4, "ip"), (6, "ip6")):
        prefixes = sorted(
            {
                str(network)
                for prefix in connected
                if (
                    network := ipaddress.ip_network(prefix, strict=False)
                ).version
                == version
                and network.prefixlen > 0
            }
        )
        if prefixes:
            ranges = ", ".join(prefixes)
            rules.append(
                f"        iifname {{ {edge_set} }} "
                f"{family} daddr {{ {ranges} }} "
                "ct state new reject with icmpx type admin-prohibited"
            )
    for family, ranges in (
        (
            "ip",
            "0.0.0.0/8, 10.0.0.0/8, 100.64.0.0/10, 127.0.0.0/8, "
            "169.254.0.0/16, 172.16.0.0/12, 192.168.0.0/16",
        ),
        ("ip6", "::/128, ::1/128, fc00::/7, fe80::/10"),
    ):
        rules.append(
            f"        iifname {{ {edge_set} }} {family} daddr {{ {ranges} }} "
            "ct state new reject with icmpx type admin-prohibited"
        )
    rules += ["    }", "}", ""]
    return "\n".join(rules)


def apply_firewall(rules: str) -> None:
    if os.geteuid() != 0:
        raise ValueError("Applying firewall rules requires root")
    result = subprocess.run(
        ["nft", "list", "table", "inet", FIREWALL_TABLE],
        capture_output=True,
        text=True,
        timeout=15,
    )
    prefix = (
        f"delete table inet {FIREWALL_TABLE}\n"
        if result.returncode == 0
        else ""
    )
    candidate = prefix + rules
    for args in (["nft", "-c", "-f", "-"], ["nft", "-f", "-"]):
        subprocess.run(
            args, input=candidate, text=True, check=True, timeout=30
        )


def render_jails(project: Path, ports: list[int]) -> str:
    logs = project / "cache/logs"
    shared = (
        "ignoreip = 127.0.0.1/8 ::1\n"
        "bantime = 1h\nfindtime = 10m\n"
        "bantime.increment = true\nusedns = no\n"
    )
    output = "# Managed MarinKino jails; unrelated sections are unchanged.\n"
    output += (
        "[sshd]\nenabled = true\nbackend = systemd\n"
        f"port = {','.join(map(str, ports))}\nchain = INPUT\n"
        "banaction = iptables-multiport\nmaxretry = 3\n" + shared
    )
    for name, logfile, count in (
        ("nginx-http-auth", "nginx/error.log", 5),
        ("nginx-botsearch", "nginx/error.log", 5),
        ("nginx-404", "nginx/access.log", 60),
        ("marinkino-auth", "server/server.log", 10),
    ):
        # Fail2Ban splits the final word as head/tail; preceding spaces belong
        # to the pathname. Escape ConfigParser interpolation and glob syntax.
        logpath = glob.escape(str(logs / logfile)).replace("%", "%%")
        output += (
            f"\n[{name}]\nenabled = true\nfilter = {name}\n"
            "backend = polling\nport = http,https\nchain = DOCKER-USER\n"
            "banaction = iptables-multiport\n"
            f"logpath = {logpath} tail\n" + shared + f"maxretry = {count}\n"
        )
    return output


def quoted_path(path: Path) -> str:
    return '"' + str(path).replace("\\", "\\\\").replace('"', '\\"') + '"'


def systemd_argument(value: str) -> str:
    return quoted_path(Path(value)).replace("%", "%%").replace("$", "$$")


def render_firewall_service(project: Path) -> str:
    return (
        "[Unit]\nDescription=MarinKino host and LAN isolation rules\n"
        "Wants=network-online.target\n"
        "After=network-online.target docker.service\n"
        "PartOf=docker.service\n\n[Service]\nType=oneshot\nRemainAfterExit=yes\n"
        "ExecStart=/usr/bin/python3 "
        "/usr/local/lib/marinkino/security_config.py "
        f"firewall --project {systemd_argument(str(project))} --apply\n"
        "\n[Install]\nWantedBy=multi-user.target docker.service\n"
    )


def render_logrotate(project: Path) -> str:
    nginx = quoted_path(project / "cache/logs/nginx/*.log")
    security = quoted_path(project / "cache/logs/security/*.log")
    return (
        f"{nginx} {{\n    daily\n    rotate 7\n    compress\n"
        "    delaycompress\n"
        "    missingok\n    notifempty\n    create 0640 root root\n"
        "    su root root\n    sharedscripts\n    postrotate\n"
        "        /usr/bin/docker kill --signal USR1 marinkino-nginx "
        ">/dev/null 2>&1 || true\n"
        "    endscript\n}\n"
        f"{security} {{\n    daily\n    rotate 14\n    compress\n"
        "    missingok\n    notifempty\n    copytruncate\n"
        "    su root root\n}\n"
    )


def install_host(project: Path) -> None:
    if os.geteuid() != 0:
        raise ValueError("Host configuration installation requires root")
    values = deployment_config(project)
    ports = ssh_ports()
    filters = project / "configuration/fail2ban/filter.d"
    for name in ("nginx-404", "marinkino-auth"):
        source = checked_path(filters / f"{name}.conf")
        if not source.is_file():
            raise ValueError(f"Missing Fail2Ban filter: {name}")
        atomic_write(
            Path("/etc/fail2ban/filter.d") / source.name,
            source.read_bytes(),
            0o644,
        )
    atomic_write(
        Path("/etc/fail2ban/jail.d/marinkino.local"),
        render_jails(project, ports),
        0o644,
    )
    atomic_write(
        Path("/etc/logrotate.d/marinkino"),
        render_logrotate(project),
        0o644,
    )
    helper = Path("/usr/local/lib/marinkino/security_config.py")
    checked_path(helper.parent)
    helper.parent.mkdir(parents=True, exist_ok=True, mode=0o755)
    helper.parent.chmod(0o755)
    os.chown(helper.parent, 0, 0)
    atomic_write(helper, Path(__file__).read_bytes(), 0o644)
    os.chown(helper, 0, 0)
    atomic_write(
        Path("/etc/systemd/system/marinkino-firewall.service"),
        render_firewall_service(project),
        0o644,
    )
    # Keep the current SSH source for reboots as well as this invocation.
    connection = os.environ.get("SSH_CONNECTION", "")
    if connection:
        networks = management_networks(values, connection)
        update_env(
            project, {"MARINKINO_MGMT_CIDRS": ",".join(map(str, networks))}
        )
        values = deployment_config(project)
    rules = render_firewall(
        values,
        ports,
        connection,
        resolver_addresses(),
        connected_networks(),
    )
    apply_firewall(rules)
    subprocess.run(["systemctl", "daemon-reload"], check=True, timeout=30)
    subprocess.run(
        ["systemctl", "enable", "marinkino-firewall.service"],
        check=True,
        timeout=30,
    )


def sqlite_snapshot(source, target, expected):
    def unchanged_source():
        with safe_descriptor(source, regular=True) as descriptor:
            current = os.fstat(descriptor)
            if (current.st_dev, current.st_ino) != (
                expected.st_dev,
                expected.st_ino,
            ):
                raise ValueError("SQLite source changed during backup")

    unchanged_source()
    uri = source.absolute().as_uri() + "?mode=ro"
    with sqlite3.connect(uri, uri=True, timeout=15) as original:
        unchanged_source()
        with sqlite3.connect(target) as snapshot:
            started = time.monotonic()
            page_size = original.execute("PRAGMA page_size").fetchone()[0]

            def bounded_progress(_status, _remaining, total):
                if total * page_size > MAX_METADATA_BYTES:
                    raise ValueError(
                        "SQLite snapshot exceeds the backup limit"
                    )
                if time.monotonic() - started > 30:
                    raise ValueError("SQLite backup exceeded its time limit")

            original.backup(snapshot, pages=128, progress=bounded_progress)
    unchanged_source()
    set_permissions(target, 0o600)
    with safe_descriptor(target, regular=True) as descriptor:
        if os.fstat(descriptor).st_size > MAX_METADATA_BYTES:
            target.unlink()
            raise ValueError("SQLite snapshot exceeds the backup limit")


def backup_file(source, target):
    with safe_descriptor(source, regular=True) as descriptor:
        info = os.fstat(descriptor)
        if info.st_size > MAX_METADATA_BYTES:
            raise ValueError("Metadata file exceeds the 32 MiB backup limit")
        if source.suffix.lower() in {".sqlite3", ".db"}:
            sqlite_snapshot(source, target, info)
        else:
            with os.fdopen(os.dup(descriptor), "rb") as stream:
                payload = stream.read(MAX_METADATA_BYTES + 1)
            if len(payload) > MAX_METADATA_BYTES:
                raise ValueError("Metadata grew beyond the backup limit")
            atomic_write(target, payload)


def backup_metadata(project: Path, destination: Path) -> None:
    destination = checked_path(destination.absolute())
    if destination.exists() and any(destination.iterdir()):
        raise ValueError("Backup staging directory must be empty")
    ensure_directory(destination, 0o700, os.geteuid(), os.getegid())
    data = checked_path(project / "data")
    candidates = [checked_path(project / ".env")]
    for path in data.iterdir():
        checked_path(path)
        if path.is_file() and path.suffix.lower() in {
            ".json",
            ".sqlite3",
            ".db",
        }:
            candidates.append(path)
    for name in ("movies", "users-music-albums"):
        for path in walk_regular(data / name):
            if path.suffix.lower() == ".json":
                candidates.append(path)
    for source in candidates:
        relative = source.relative_to(project)
        target = checked_path(destination / relative)
        ensure_directory(target.parent, 0o700, os.geteuid(), os.getegid())
        for parent in (target.parent, *target.parent.parents):
            if parent == destination.parent:
                break
            set_permissions(parent, 0o700)
        backup_file(source, target)


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    for command in (
        "prepare",
        "value",
        "render-nginx",
        "install-host",
        "firewall",
        "backup",
    ):
        subparser = commands.add_parser(command)
        subparser.add_argument("--project", required=True)
        if command == "prepare":
            subparser.add_argument("--uid", required=True, type=int)
            subparser.add_argument("--gid", required=True, type=int)
        elif command == "value":
            subparser.add_argument("name")
        elif command == "render-nginx":
            subparser.add_argument("--bootstrap", action="store_true")
            subparser.add_argument("--output", type=Path)
        elif command == "firewall":
            subparser.add_argument("--apply", action="store_true")
        elif command == "backup":
            subparser.add_argument("--destination", required=True, type=Path)
    args = parser.parse_args(argv)
    try:
        project = project_path(args.project)
        if args.command == "prepare":
            prepare(project, args.uid, args.gid)
        elif args.command == "value":
            print(read_env(project).get(args.name, ""))
        elif args.command == "render-nginx":
            output = (
                args.output or project / "configuration/nginx/conf/app.conf"
            )
            atomic_write(
                output,
                render_nginx(deployment_config(project), args.bootstrap),
                0o644,
            )
        elif args.command == "install-host":
            install_host(project)
        elif args.command == "firewall":
            rules = render_firewall(
                read_env(project),
                ssh_ports(),
                os.environ.get("SSH_CONNECTION", ""),
                resolver_addresses(),
                connected_networks(),
            )
            if args.apply:
                apply_firewall(rules)
            else:
                print(rules, end="")
        elif args.command == "backup":
            backup_metadata(project, args.destination)
    except (
        ValueError,
        OSError,
        subprocess.SubprocessError,
        sqlite3.Error,
    ) as error:
        # Validation messages never include environment values or credentials.
        print(f"Security configuration failed: {error}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

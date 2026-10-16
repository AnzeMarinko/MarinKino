"""Deployment generation must stay literal, scoped, and safe to stage."""

import configparser
import importlib.util
import ipaddress
import json
import os
import re
import sqlite3
import stat
import subprocess
import sys
from pathlib import Path

import pytest

SOURCE = Path(__file__).resolve().parents[1] / "scripts/security_config.py"
SPEC = importlib.util.spec_from_file_location("security_config_tests", SOURCE)
security = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(security)


@pytest.fixture
def project(tmp_path):
    root = tmp_path / "Marin Kino"
    root.mkdir()
    (root / ".env").write_text(
        "# Existing configuration\n"
        "MAIN_DOMAIN=example.si\nWWW_DOMAIN=www.example.si\n"
        "GMAIL_USERNAME=admin@example.si\nGMAIL_TOKEN='literal $secret'\n"
        "FLASK_KEY=changeme\n",
    )
    return root


def test_dotenv_is_literal_and_supports_quotes_comments():
    parsed = security.parse_env(
        'export NAME="a\\nb\\t\\"c" # comment\n'
        "SECRET='$(touch /tmp/not-executed) `uname` $HOME'\n"
        "URL=https://example.si/#fragment # trailing comment\n",
    )
    assert parsed == {
        "NAME": 'a\nb\t"c',
        "SECRET": "$(touch /tmp/not-executed) `uname` $HOME",
        "URL": "https://example.si/#fragment",
    }


@pytest.mark.parametrize(
    "content",
    [
        "NO_ASSIGNMENT",
        "INVALID-KEY=x",
        "KEY='unclosed",
        'KEY="x"suffix',
        "KEY=x\nKEY=y",
        "KEY=null\0byte",
    ],
)
def test_invalid_dotenv_rejected(content):
    with pytest.raises(ValueError):
        security.parse_env(content)


@pytest.mark.parametrize(
    "domain",
    [
        "$(id).example.si",
        "`id`.example.si",
        "example.si;id",
        "*.example.si",
        "example.si/path",
        "example.si:443",
        "....si",
        "example.si\nother.si",
    ],
)
def test_deployment_domain_cannot_inject_configuration(project, domain):
    with pytest.raises(ValueError):
        security.validate_domain(domain, "MAIN_DOMAIN")


def test_public_origin_must_be_canonical_https(project):
    with (project / ".env").open("a") as stream:
        stream.write("PUBLIC_BASE_URL=https://evil.example\n")
    with pytest.raises(ValueError, match="canonical HTTPS"):
        security.deployment_config(project)


def test_public_origin_rejects_hidden_newline(project):
    with (project / ".env").open("a") as stream:
        stream.write('PUBLIC_BASE_URL="https://www.example.si\\n"\n')
    with pytest.raises(ValueError, match="canonical HTTPS"):
        security.deployment_config(project)


def test_prepare_rotates_placeholder_and_preserves_other_values(project):
    if os.getuid() == 0:
        pytest.skip("Permission test uses the unprivileged test user's UID")
    data = project / "data"
    media = data / "movies/group/film"
    media.mkdir(parents=True)
    (media / "readme.json").write_text('{"private":true}')
    (media / "film.mp4").write_bytes(b"video")
    (data / "users.json").write_text("{}")
    source = project / "app.py"
    source.write_text("unchanged")
    source.chmod(0o644)
    credentials = project / "credentials"
    credentials.mkdir()
    (credentials / "service-account.json").write_text('{"private_key":"test"}')
    security.prepare(project, os.getuid(), os.getgid())
    values = security.read_env(project)
    assert len(values["FLASK_KEY"]) >= 32
    assert values["PUBLIC_BASE_URL"] == "https://www.example.si"
    assert values["GMAIL_TOKEN"] == "literal $secret"
    assert values["MARINKINO_UID"] == str(os.getuid())
    assert (project / ".env").stat().st_mode & 0o777 == 0o600
    assert (media / "film.mp4").stat().st_mode & 0o777 == 0o644
    assert (media / "readme.json").stat().st_mode & 0o777 == 0o600
    assert (data / "users.json").stat().st_mode & 0o777 == 0o600
    assert (project / "cache/downloads").stat().st_mode & 0o777 == 0o755
    assert (project / "cache/logs/server").stat().st_mode & 0o777 == 0o750
    assert source.stat().st_mode & 0o777 == 0o644
    assert credentials.stat().st_mode & 0o777 == 0o700
    assert (
        credentials / "service-account.json"
    ).stat().st_mode & 0o777 == 0o600
    previous = values["FLASK_KEY"]
    security.prepare(project, os.getuid(), os.getgid())
    assert security.read_env(project)["FLASK_KEY"] == previous


def test_prepare_cannot_use_root_identity(project):
    with pytest.raises(ValueError, match="nonzero"):
        security.prepare(project, 0, 1000)


def test_nginx_has_scoped_aliases_proxy_and_limits(project):
    config = security.render_nginx(security.deployment_config(project))
    assert "proxy_pass http://unix:/run/marinkino/app.sock:;" in config
    assert "proxy_set_header X-Forwarded-For $remote_addr;" in config
    assert "$proxy_add_x_forwarded_for" not in config
    assert "ssl_protocols TLSv1.2 TLSv1.3;" in config
    assert "ssl_reject_handshake on;" in config
    assert "server_name example.si;" in config
    assert "server_name www.example.si;" in config
    assert "https://www.example.si$request_uri" in config
    assert "limit_req zone=mk_auth" in config
    assert "limit_req zone=mk_api" in config
    assert "limit_conn mk_connections" in config
    assert "Access-Control-Allow-Origin" not in config
    assert "disable_symlinks on;" in config
    for name in (*security.PUBLIC_DIRS, "downloads"):
        protected = name.replace("-", "_")
        assert f"location ^~ /protected_{protected}/" in config
    assert config.count("internal;") == 6
    assert "if ($uri !~* \\.(zip)$) { return 404; }" in config
    assert "object-src 'none'" in config
    assert "always;" in config


@pytest.mark.parametrize("bootstrap", [False, True])
def test_keepalive_overrides_stock_http_setting_only_in_servers(
    project, bootstrap
):
    config = security.render_nginx(
        security.deployment_config(project), bootstrap=bootstrap
    )
    # Stock nginx.conf sets keepalive_timeout in http before including conf.d.
    # Each virtual host can override it, but the included http scope cannot.
    assert "keepalive_timeout" not in config.split("server {", 1)[0]
    servers = re.findall(r"(?m)^server \{", config)
    overrides = re.findall(
        r"(?m)^server \{\n    keepalive_timeout 20s;", config
    )
    assert len(servers) == len(overrides) > 0
    assert config.count("keepalive_timeout") == len(servers)


def test_bootstrap_has_acme_and_no_tls_or_backend(project):
    config = security.render_nginx(
        security.deployment_config(project),
        bootstrap=True,
    )
    assert "location ^~ /.well-known/acme-challenge/" in config
    assert 'return 200 "Certificate setup' in config
    assert "listen 443" not in config
    assert "proxy_pass" not in config


def test_nginx_output_can_be_staged_without_overwriting_live(project):
    live = project / "configuration/nginx/conf/app.conf"
    live.parent.mkdir(parents=True)
    live.write_text("live configuration")
    staged = project / "candidate.conf"
    assert (
        security.main(
            [
                "render-nginx",
                "--project",
                str(project),
                "--output",
                str(staged),
            ]
        )
        == 0
    )
    assert live.read_text() == "live configuration"
    assert "ssl_protocols" in staged.read_text()


def test_managed_files_refuse_symlinks(project, tmp_path):
    outside = tmp_path / "do-not-overwrite"
    outside.write_text("unchanged")
    target = project / "candidate.conf"
    target.symlink_to(outside)
    with pytest.raises(ValueError, match="symlink"):
        security.atomic_write(target, "replacement")
    assert outside.read_text() == "unchanged"


def test_firewall_limits_only_own_interfaces_and_preserves_ssh(project):
    config = security.render_firewall(
        security.deployment_config(project),
        [22, 2222],
        "198.51.100.12 12345 192.168.1.9 22",
        ["192.168.1.1"],
    )
    assert "table inet marinkino_security" in config
    assert "flush ruleset" not in config
    assert "hook input priority -5; policy drop;" in config
    assert "hook forward priority -5; policy accept;" in config
    assert "198.51.100.12/32" in config
    assert "tcp dport { 22, 2222 }" in config
    assert config.index('"mk-backend" } drop') < config.index("tcp dport { 22")
    assert 'iifname "mk-egress" oifname "mk-egress" accept' in config
    assert (
        "ip daddr 192.168.1.1 meta l4proto { tcp, udp } th dport 53 accept"
        in config
    )
    assert "reject with icmpx type admin-prohibited" in config


def test_firewall_rejects_unrestricted_management_subnet():
    with pytest.raises(ValueError, match="entire Internet"):
        security.management_networks({"MARINKINO_MGMT_CIDRS": "0.0.0.0/0"})


def test_firewall_validates_before_atomic_replacement(monkeypatch):
    commands = []
    monkeypatch.setattr(security.os, "geteuid", lambda: 0)

    def run(args, **kwargs):
        commands.append((args, kwargs))
        return subprocess.CompletedProcess(args, 0)

    monkeypatch.setattr(security.subprocess, "run", run)
    security.apply_firewall("table inet marinkino_security {}\n")
    assert commands[1][0] == ["nft", "-c", "-f", "-"]
    assert commands[2][0] == ["nft", "-f", "-"]
    assert commands[1][1]["input"] == commands[2][1]["input"]
    assert commands[2][1]["input"].startswith(
        "delete table inet marinkino_security\n",
    )


def test_invalid_firewall_is_never_applied(monkeypatch):
    commands = []
    monkeypatch.setattr(security.os, "geteuid", lambda: 0)

    def run(args, **kwargs):
        commands.append(args)
        if "-c" in args:
            raise subprocess.CalledProcessError(1, args)
        return subprocess.CompletedProcess(args, 0)

    monkeypatch.setattr(security.subprocess, "run", run)
    with pytest.raises(subprocess.CalledProcessError):
        security.apply_firewall("invalid")
    assert ["nft", "-f", "-"] not in commands


def test_jails_parse_without_duplicate_keys_and_scope_web_to_docker(project):
    parser = configparser.ConfigParser()
    parser.read_string(security.render_jails(project, [2222]))
    assert parser["sshd"]["chain"] == "INPUT"
    assert parser["sshd"]["port"] == "2222"
    assert parser["sshd"]["backend"] == "systemd"
    for name in (
        "nginx-http-auth",
        "nginx-botsearch",
        "nginx-404",
        "marinkino-auth",
    ):
        assert parser[name]["chain"] == "DOCKER-USER"
        assert parser[name]["ignoreip"] == "127.0.0.1/8 ::1"
    assert parser["marinkino-auth"]["logpath"].endswith("/server.log tail")
    assert "server_start" not in parser["marinkino-auth"]["logpath"]
    assert "[recidive]" not in parser


def test_firewall_service_uses_root_owned_helper_without_shell(project):
    service = security.render_firewall_service(project)
    assert "/usr/local/lib/marinkino/security_config.py firewall" in service
    assert "PartOf=docker.service" in service
    assert f'--project "{project}" --apply' in service
    assert "/bin/sh" not in service
    rotated = security.render_logrotate(project)
    assert "kill --signal USR1 marinkino-nginx" in rotated
    assert "daily" in rotated and "rotate 7" in rotated


def test_backup_includes_metadata_and_consistent_sqlite_not_media(
    project, tmp_path
):
    data = project / "data"
    movie = data / "movies/group/film"
    movie.mkdir(parents=True)
    (movie / "readme.json").write_text('{"title":"film"}')
    (movie / "film.mp4").write_bytes(b"large media excluded")
    (data / "users.json").write_text('{"admin":{}}')
    albums = data / "users-music-albums"
    albums.mkdir()
    (albums / "admin.json").write_text("{}")
    database = data / "fitness.sqlite3"
    with sqlite3.connect(database) as connection:
        connection.execute("CREATE TABLE records (value TEXT)")
        connection.execute("INSERT INTO records VALUES ('preserved')")
    destination = tmp_path / "private snapshot"
    security.backup_metadata(project, destination)
    assert (destination / ".env").read_bytes() == (
        project / ".env"
    ).read_bytes()
    assert (destination / "data/users.json").is_file()
    assert (destination / "data/movies/group/film/readme.json").is_file()
    assert (destination / "data/users-music-albums/admin.json").is_file()
    assert not (destination / "data/movies/group/film/film.mp4").exists()
    with sqlite3.connect(destination / "data/fitness.sqlite3") as copied:
        assert (
            copied.execute("SELECT value FROM records").fetchone()[0]
            == "preserved"
        )
    for path in destination.rglob("*"):
        expected = 0o700 if path.is_dir() else 0o600
        assert stat.S_IMODE(path.stat().st_mode) == expected


def test_backup_rejects_symlink_and_oversized_metadata(project, tmp_path):
    data = project / "data"
    data.mkdir()
    outside = tmp_path / "private.json"
    outside.write_text("{}")
    (data / "users.json").symlink_to(outside)
    with pytest.raises(ValueError, match="symlink"):
        security.backup_metadata(project, tmp_path / "snapshot-one")
    (data / "users.json").unlink()
    with (data / "users.json").open("wb") as stream:
        stream.truncate(security.MAX_METADATA_BYTES + 1)
    with pytest.raises(ValueError, match="32 MiB"):
        security.backup_metadata(project, tmp_path / "snapshot-two")


def test_global_lan_prefixes_are_blocked_without_blocking_public_internet():
    rendered = security.render_firewall(
        {},
        [22],
        resolvers=["203.0.113.1"],
        connected=["203.0.113.0/24", "2001:db8:1234::/64"],
    )
    expected = (
        "ip daddr { 203.0.113.0/24 }",
        "ip6 daddr { 2001:db8:1234::/64 }",
    )
    for fragment in expected:
        line = next(line for line in rendered.splitlines() if fragment in line)
        assert 'iifname { "mk-edge", "mk-egress" }' in line
        assert "ct state new reject" in line
    assert "203.0.114.0/24" not in rendered
    assert "2001:db8:1235::/64" not in rendered
    assert "daddr { 0.0.0.0/0 }" not in rendered
    assert "daddr { ::/0 }" not in rendered
    denied = [
        ipaddress.ip_network(prefix.strip())
        for group in re.findall(
            r"(?:ip|ip6) daddr \{ ([^}]+) \} ct state new reject",
            rendered,
        )
        for prefix in group.split(",")
    ]
    for address in ("203.0.113.55", "2001:db8:1234::5"):
        assert any(
            ipaddress.ip_address(address) in subnet for subnet in denied
        )
    for address in ("1.1.1.1", "2606:4700:4700::1111"):
        assert not any(
            ipaddress.ip_address(address) in subnet for subnet in denied
        )
    assert "hook forward priority -5; policy accept;" in rendered
    assert rendered.index("th dport 53 accept") < rendered.index(
        "ip daddr { 203.0.113.0/24 }",
    )
    assert rendered.index('iifname "mk-edge" oifname "mk-edge" accept') < (
        rendered.index("ip6 daddr { 2001:db8:1234::/64 }")
    )


def fake_route_process(monkeypatch, script_for_command):
    original = subprocess.Popen
    commands = []

    def popen(command, **options):
        commands.append(command)
        return original(
            [sys.executable, "-c", script_for_command(command)],
            **options,
        )

    monkeypatch.setattr(security.subprocess, "Popen", popen)
    return commands


def test_connected_networks_only_include_direct_non_docker_routes(monkeypatch):
    ipv4 = [
        {"dst": "203.0.113.23/24", "dev": "eth0", "protocol": "kernel"},
        {"dst": "203.0.113.0/24", "dev": "eth0"},
        {"dst": "192.168.1.0/24", "dev": "wlan0"},
        {"dst": "default", "dev": "eth0", "gateway": "203.0.113.1"},
        {"dst": "198.51.100.0/24", "dev": "eth0", "gateway": "203.0.113.1"},
        {"dst": "127.0.0.0/8", "dev": "lo"},
        {"dst": "172.17.0.0/16", "dev": "docker0"},
        {"dst": "172.18.0.0/16", "dev": "br-abc123"},
        {"dst": "172.19.0.0/16", "dev": "mk-egress"},
        {"dst": "not-a-network", "dev": "eth0"},
        {"dst": "192.0.2.0/24"},
        "invalid-record",
    ]
    ipv6 = [
        {"dst": "2001:db8:1234::/64", "dev": "eth0", "protocol": "kernel"},
        {"dst": "fe80::/64", "dev": "eth0"},
        {"dst": "::/0", "dev": "eth0"},
        {"dst": "default", "dev": "eth0", "gateway": "fe80::1"},
        {"dst": "2001:db8:4567::/64", "dev": "eth0", "via": "fe80::2"},
        {"dst": "2001:db8:aaaa::/64", "dev": "mk-backend"},
        {"dst": "2001:db8:bbbb::/64", "dev": "eth0", "nexthops": [{}]},
        {"dst": "2001:db8:cccc::/64", "dev": "eth0", "type": "unreachable"},
    ]
    commands = fake_route_process(
        monkeypatch,
        lambda command: "print("
        + repr(
            json.dumps(
                ipv4 if "-4" in command else ipv6,
            )
        )
        + ")",
    )
    assert {str(network) for network in security.connected_networks()} == {
        "203.0.113.0/24",
        "192.168.1.0/24",
        "2001:db8:1234::/64",
        "fe80::/64",
    }
    assert commands == [
        ["ip", "-j", "-4", "route", "show", "scope", "link"],
        ["ip", "-j", "-6", "route", "show"],
    ]


@pytest.mark.parametrize("payload", ["invalid-json", "{}", "[1]" * 5])
def test_connected_networks_reject_invalid_json(monkeypatch, payload):
    fake_route_process(monkeypatch, lambda _command: f"print({payload!r})")
    with pytest.raises(ValueError):
        security.connected_networks()


def test_connected_networks_bound_output_and_execution_time(monkeypatch):
    monkeypatch.setattr(security, "MAX_ROUTE_BYTES", 1024)
    fake_route_process(monkeypatch, lambda _command: "print('x' * 2048)")
    with pytest.raises(ValueError, match="output exceeds"):
        security.connected_networks()


def test_connected_network_collection_timeout_kills_child(monkeypatch):
    monkeypatch.setattr(security, "ROUTE_TIMEOUT", 0.1)
    fake_route_process(
        monkeypatch, lambda _command: "import time; time.sleep(5)"
    )
    with pytest.raises(subprocess.TimeoutExpired):
        security.connected_networks()


def test_connected_networks_reject_excess_records(monkeypatch):
    monkeypatch.setattr(security, "MAX_ROUTE_RECORDS", 4)
    payload = json.dumps([{}] * 5)
    fake_route_process(monkeypatch, lambda _command: f"print({payload!r})")
    with pytest.raises(ValueError, match="excessive connected route"):
        security.connected_networks()


def test_firewall_cli_uses_connected_prefixes(project, monkeypatch, capsys):
    monkeypatch.setattr(security, "ssh_ports", lambda: [22])
    monkeypatch.setattr(security, "resolver_addresses", lambda: [])
    monkeypatch.setattr(
        security,
        "connected_networks",
        lambda: [
            ipaddress.ip_network("2001:db8:1234::/64"),
        ],
    )
    assert security.main(["firewall", "--project", str(project)]) == 0
    assert "ip6 daddr { 2001:db8:1234::/64 }" in capsys.readouterr().out


def test_permission_changes_refuse_replaced_final_symlink(
    tmp_path, monkeypatch
):
    victim = tmp_path / "private-file"
    victim.write_text("private")
    victim.chmod(0o600)
    managed = tmp_path / "managed.json"
    managed.write_text("metadata")
    original_open = os.open

    def replace_before_open(path, flags, *args, **kwargs):
        if path == managed.name and kwargs.get("dir_fd") is not None:
            managed.unlink()
            managed.symlink_to(victim)
        return original_open(path, flags, *args, **kwargs)

    monkeypatch.setattr(security.os, "open", replace_before_open)
    with pytest.raises(OSError):
        security.set_permissions(managed, 0o644)
    assert stat.S_IMODE(victim.stat().st_mode) == 0o600
    assert victim.read_text() == "private"


@pytest.mark.parametrize("action", ["chmod", "mkdir"])
def test_parent_replacement_cannot_redirect_privileged_operations(
    tmp_path,
    monkeypatch,
    action,
):
    outside = tmp_path / "outside"
    outside.mkdir()
    (outside / "file.json").write_text("private")
    (outside / "file.json").chmod(0o600)
    parent = tmp_path / "managed"
    parent.mkdir()
    (parent / "file.json").write_text("metadata")
    original_open = os.open

    def replace_parent(path, flags, *args, **kwargs):
        if path == parent.name and kwargs.get("dir_fd") is not None:
            parent.rename(tmp_path / "original-managed")
            parent.symlink_to(outside, target_is_directory=True)
        return original_open(path, flags, *args, **kwargs)

    monkeypatch.setattr(security.os, "open", replace_parent)
    with pytest.raises(OSError):
        if action == "chmod":
            security.set_permissions(parent / "file.json", 0o644)
        else:
            security.ensure_directory(
                parent / "new/private",
                0o700,
                os.getuid(),
                os.getgid(),
            )
    assert stat.S_IMODE((outside / "file.json").stat().st_mode) == 0o600
    assert not (outside / "new").exists()


def test_atomic_write_stays_in_opened_directory_after_rename(
    tmp_path, monkeypatch
):
    parent = tmp_path / "managed"
    parent.mkdir()
    outside = tmp_path / "outside"
    outside.mkdir()
    victim = outside / "server.log"
    victim.write_text("unchanged")
    original_replace = os.replace
    moved = tmp_path / "original-managed"

    def move_before_replace(source, target, **options):
        parent.rename(moved)
        parent.symlink_to(outside, target_is_directory=True)
        return original_replace(source, target, **options)

    monkeypatch.setattr(security.os, "replace", move_before_replace)
    security.atomic_write(parent / "server.log", "safe log content")
    assert victim.read_text() == "unchanged"
    assert (moved / "server.log").read_text() == "safe log content"


def test_backup_refuses_file_swapped_for_symlink(tmp_path, monkeypatch):
    private = tmp_path / "private.json"
    private.write_text("must not copy")
    source = tmp_path / "users.json"
    source.write_text("safe original")
    target = tmp_path / "snapshot.json"
    original_open = os.open

    def swap_before_open(path, flags, *args, **kwargs):
        if path == source.name and kwargs.get("dir_fd") is not None:
            source.unlink()
            source.symlink_to(private)
        return original_open(path, flags, *args, **kwargs)

    monkeypatch.setattr(security.os, "open", swap_before_open)
    with pytest.raises(OSError):
        security.backup_file(source, target)
    assert not target.exists()


def test_safe_descriptor_refuses_fifo_without_waiting(tmp_path):
    fifo = tmp_path / "metadata.json"
    os.mkfifo(fifo)
    program = (
        "import importlib.util,pathlib; "
        "spec=importlib.util.spec_from_file_location("
        f"'helper',{str(SOURCE)!r}); "
        "helper=importlib.util.module_from_spec(spec); "
        "spec.loader.exec_module(helper); "
        f"path=pathlib.Path({str(fifo)!r}); "
        "helper.backup_file(path,path.with_name('target.json'))"
    )
    result = subprocess.run(
        [sys.executable, "-c", program],
        capture_output=True,
        timeout=3,
    )
    assert result.returncode != 0
    assert b"regular files" in result.stderr


def test_nginx_large_bodies_only_allowed_on_rate_limited_admin_forms(project):
    config = security.render_nginx(security.deployment_config(project))
    assert "client_max_body_size 64k;" in config
    assert "client_max_body_size 16k;" in config
    assert config.count("client_max_body_size 40m;") == 2
    preview = config.split(
        "location ~ ^/admin/blog/image-preview/?$ {",
        1,
    )[1].split("\n    }", 1)[0]
    save = config.split(
        "location ~ ^/admin/blog/(?:new|edit/[^/]+)/?$ {",
        1,
    )[1].split("\n    }", 1)[0]
    assert "limit_req zone=mk_upload_preview burst=10 nodelay;" in preview
    assert "limit_req zone=mk_upload burst=1 nodelay;" in save
    for location in (preview, save):
        assert "client_max_body_size 40m;" in location
        assert "limit_conn mk_upload_connections 1;" in location
    assert "zone=mk_upload:1m rate=1r/m;" in config
    assert "zone=mk_upload_preview:1m rate=12r/m;" in config
    post_only = config.split("map $request_method $mk_upload_key {", 1)[1]
    post_only = post_only.split("}", 1)[0]
    assert 'default "";' in post_only
    assert "POST $binary_remote_addr;" in post_only
    assert "geolocation=(self)" in config


@pytest.mark.parametrize(
    "value",
    [
        "$",
        "$FOO",
        "${HOME}",
        "`uname`",
        "$(notexec)",
        "both 'single' and \"double\" quotes",
        r"path\to\file",
        r"path\\to\\file",
        r"even\\'quote",
        "spaces # are literal",
    ],
)
def test_managed_env_values_roundtrip_without_interpolation(project, value):
    security.update_env(project, {"TEST_LITERAL": value})
    serialized = (project / ".env").read_text()
    line = next(
        line
        for line in serialized.splitlines()
        if line.startswith("TEST_LITERAL=")
    )
    assert line.startswith("TEST_LITERAL='") and line.endswith("'")
    assert security.read_env(project)["TEST_LITERAL"] == value


@pytest.mark.parametrize(
    "value",
    [
        "trailing\\",
        "line\nfeed",
        "carriage\rreturn",
        "tab\tvalue",
        "null\0byte",
        "delete\x7f",
        "line\u2028separator",
        r"odd\'quote",
    ],
)
def test_unrepresentable_managed_env_values_leave_file_unchanged(
    project, value
):
    original = (project / ".env").read_bytes()
    with pytest.raises(ValueError):
        security.update_env(project, {"TEST_LITERAL": value})
    assert (project / ".env").read_bytes() == original


def test_trailing_backslash_is_rejected_with_clear_error():
    with pytest.raises(ValueError, match="end with a backslash"):
        security.env_literal("secret\\")


def test_prepare_preserves_strong_key_with_literal_dollars(project):
    if os.getuid() == 0:
        pytest.skip("Permission test uses the unprivileged test user's UID")
    key = "Z9R7X6G8!literal$FOO:${HOME}:`uname`:$(notexec):long-key"
    text = (project / ".env").read_text()
    (project / ".env").write_text(
        text.replace(
            "FLASK_KEY=changeme",
            "FLASK_KEY=" + json.dumps(key),
        )
    )
    security.prepare(project, os.getuid(), os.getgid())
    assert security.read_env(project)["FLASK_KEY"] == key
    assert (
        (project / ".env")
        .read_text()
        .split("FLASK_KEY=", 1)[1]
        .startswith("'")
    )
    security.prepare(project, os.getuid(), os.getgid())
    assert security.read_env(project)["FLASK_KEY"] == key


@pytest.mark.parametrize("suffix", ["\nline", "\rline", "\\"])
def test_prepare_rotates_unrepresentable_legacy_flask_key_once(
    project, suffix
):
    if os.getuid() == 0:
        pytest.skip("Permission test uses the unprivileged test user's UID")
    key = "Z9R7X6G8!legacy-long-key-with-strong-prefix" + suffix
    text = (project / ".env").read_text()
    (project / ".env").write_text(
        text.replace(
            "FLASK_KEY=changeme",
            "FLASK_KEY=" + json.dumps(key),
        )
    )
    security.prepare(project, os.getuid(), os.getgid())
    replacement = security.read_env(project)["FLASK_KEY"]
    assert replacement != key
    assert len(replacement) >= 32
    assert re.fullmatch(r"[A-Za-z0-9_-]+", replacement)
    security.prepare(project, os.getuid(), os.getgid())
    assert security.read_env(project)["FLASK_KEY"] == replacement

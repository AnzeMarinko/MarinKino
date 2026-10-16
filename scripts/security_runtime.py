#!/usr/bin/env python3
"""Deployment snapshots, public dependency audit and isolated smoke tests."""

import argparse
import importlib.util
import json
import os
import re
import secrets
import subprocess
import tempfile
import time
import urllib.request
from pathlib import Path


def run(*args, **kwargs):
    return subprocess.run(
        args, check=True, text=True, capture_output=True, **kwargs
    ).stdout


def escape_compose(value):
    # Compose interpolates JSON strings as well as YAML strings.
    if isinstance(value, str):
        return value.replace("$", "$$")
    if isinstance(value, dict):
        return {key: escape_compose(item) for key, item in value.items()}
    if isinstance(value, list):
        return [escape_compose(item) for item in value]
    return value


def snapshot(project, output):
    ids = run(
        "docker",
        "compose",
        "--project-directory",
        str(project),
        "ps",
        "-aq",
        "app",
        "nginx",
        "redis",
        "redis-auth",
    ).split()
    if not ids:
        return False
    containers = json.loads(run("docker", "inspect", *ids))
    document = {
        "name": containers[0]["Config"]["Labels"][
            "com.docker.compose.project"
        ],
        "services": {},
        "networks": {},
        "volumes": {},
    }
    for container in containers:
        config, host = container["Config"], container["HostConfig"]
        service_name = config["Labels"]["com.docker.compose.service"]
        service = {
            "container_name": container["Name"].lstrip("/"),
            "image": container["Image"],
            "pull_policy": "never",
            "entrypoint": config.get("Entrypoint") or [],
            "command": config.get("Cmd") or [],
            "environment": config.get("Env") or [],
            "working_dir": config.get("WorkingDir") or "/",
            "user": config.get("User") or "",
            "restart": "unless-stopped",
            "read_only": host.get("ReadonlyRootfs", False),
            "networks": {},
            "volumes": [],
        }
        for network, details in container["NetworkSettings"][
            "Networks"
        ].items():
            key = "net" + str(len(document["networks"]))
            for existing, value in document["networks"].items():
                if value["name"] == network:
                    key = existing
                    break
            document["networks"][key] = {"external": True, "name": network}
            service["networks"][key] = {"aliases": [service_name]}
        for mount in container["Mounts"]:
            if mount["Type"] == "tmpfs":
                continue
            mode = "rw" if mount["RW"] else "ro"
            if mount["Type"] == "volume":
                key = "vol" + str(len(document["volumes"]))
                for existing, value in document["volumes"].items():
                    if value["name"] == mount["Name"]:
                        key = existing
                        break
                document["volumes"][key] = {
                    "external": True,
                    "name": mount["Name"],
                }
                source = key
            else:
                source = mount["Source"]
            service["volumes"].append(
                f"{source}:{mount['Destination']}:{mode}"
            )
        ports = []
        for target, bindings in (host.get("PortBindings") or {}).items():
            for binding in bindings or []:
                address = binding.get("HostIp") or "0.0.0.0"
                if ":" in address:
                    address = "[" + address + "]"
                ports.append(f"{address}:{binding['HostPort']}:{target}")
        if ports:
            service["ports"] = ports
        for original, target in [
            ("CapAdd", "cap_add"),
            ("CapDrop", "cap_drop"),
            ("SecurityOpt", "security_opt"),
            ("Tmpfs", "tmpfs"),
        ]:
            if host.get(original):
                value = host[original]
                service[target] = (
                    [f"{k}:{v}" for k, v in value.items()]
                    if original == "Tmpfs"
                    else value
                )
        if host.get("Memory"):
            service["mem_limit"] = host["Memory"]
        if host.get("PidsLimit", 0) > 0:
            service["pids_limit"] = host["PidsLimit"]
        logging = host.get("LogConfig") or {}
        if logging.get("Type"):
            service["logging"] = {
                "driver": logging["Type"],
                "options": logging.get("Config") or {},
            }
        health = config.get("Healthcheck") or {}
        if health.get("Test") == ["NONE"]:
            service["healthcheck"] = {"disable": True}
        elif health.get("Test"):
            converted = {"test": health["Test"]}
            for source, target in [
                ("Interval", "interval"),
                ("Timeout", "timeout"),
                ("StartPeriod", "start_period"),
            ]:
                if health.get(source):
                    converted[target] = str(health[source]) + "ns"
            if health.get("Retries"):
                converted["retries"] = health["Retries"]
            service["healthcheck"] = converted
        document["services"][service_name] = service
    output.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
    descriptor, temporary = tempfile.mkstemp(dir=output.parent)
    try:
        with os.fdopen(descriptor, "w") as stream:
            os.fchmod(stream.fileno(), 0o600)
            json.dump(escape_compose(document), stream, indent=2)
        os.replace(temporary, output)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)
    return True


def audit(image):
    code = (
        "import importlib.metadata as m,json; "
        'print(json.dumps(sorted({(d.metadata["Name"],d.version) '
        "for d in m.distributions()})))"
    )
    inventory = json.loads(
        run(
            "docker",
            "run",
            "--rm",
            "--network",
            "none",
            "--read-only",
            "--cap-drop",
            "ALL",
            "--security-opt",
            "no-new-privileges",
            "--entrypoint",
            "python",
            image,
            "-c",
            code,
        )
    )
    queries = [
        {"package": {"name": name, "ecosystem": "PyPI"}, "version": version}
        for name, version in inventory
    ]
    request = urllib.request.Request(
        "https://api.osv.dev/v1/querybatch",
        json.dumps({"queries": queries}).encode(),
        {"Content-Type": "application/json"},
    )
    with urllib.request.urlopen(request, timeout=45) as response:
        result = json.load(response)
    if len(result.get("results", [])) != len(inventory):
        raise RuntimeError(
            "Incomplete vulnerability response; deployment refused"
        )
    vulnerabilities = [
        (name, version, [v["id"] for v in item.get("vulns", [])])
        for (name, version), item in zip(inventory, result["results"])
        if item.get("vulns")
    ]
    if vulnerabilities:
        raise RuntimeError(
            "Vulnerable candidate dependencies: " + json.dumps(vulnerabilities)
        )
    print(f"Dependency audit passed: {len(inventory)} installed packages")


def smoke(image, uid, gid):
    name = f"mk-security-{os.getpid()}"
    network = name + "-net"
    try:
        run("docker", "network", "create", "--internal", network)
        run(
            "docker",
            "run",
            "-d",
            "--name",
            name,
            "--network",
            network,
            "--network-alias",
            "redis",
            "--read-only",
            "--tmpfs",
            "/data",
            "--tmpfs",
            "/tmp",
            "redis:7-alpine",
            "redis-server",
            "--save",
            "",
            "--appendonly",
            "no",
        )
        for _ in range(30):
            try:
                run("docker", "exec", name, "redis-cli", "ping")
                break
            except subprocess.CalledProcessError:
                import time

                time.sleep(1)
        arguments = [
            "docker",
            "run",
            "--rm",
            "--network",
            network,
            "--read-only",
            "--cap-drop",
            "ALL",
            "--security-opt",
            "no-new-privileges",
        ]
        for path in ["/app/data", "/app/cache", "/run/marinkino", "/tmp"]:
            arguments += [
                "--tmpfs",
                f"{path}:uid={uid},gid={gid},mode=0755,size=96m",
            ]
        for value in [
            "FLASK_ENV=testing",
            "FLASK_KEY=SmokeTestPrivateKeyOnlyForDisposableContainer",
            "WWW_DOMAIN=localhost",
            "REDIS_HOST=redis",
            "REDIS_PORT=6379",
            "AUTH_REDIS_HOST=redis",
            "AUTH_REDIS_PORT=6379",
        ]:
            arguments += ["--env", value]
        print(
            run(
                *arguments,
                "--entrypoint",
                "python",
                image,
                "-m",
                "security_smoke",
            ).strip()
        )
    finally:
        subprocess.run(
            ["docker", "rm", "-f", name],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        subprocess.run(
            ["docker", "network", "rm", network],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )


def check_uid(project, uid, gid):
    ids = run(
        "docker",
        "compose",
        "--project-directory",
        str(project),
        "ps",
        "-aq",
        "app",
    ).split()
    if not ids:
        return
    config = json.loads(run("docker", "inspect", ids[0]))[0]["Config"]
    previous = config.get("User", "")
    if previous not in {"", "0", "root", "0:0", f"{uid}:{gid}"}:
        raise RuntimeError(
            "Runtime UID/GID changed; migrate private socket ownership "
            "before deployment"
        )


def migrate_redis(project):
    ids = run(
        "docker",
        "compose",
        "--project-directory",
        str(project),
        "ps",
        "-aq",
        "redis",
    ).split()
    if not ids:
        return
    container = json.loads(run("docker", "inspect", ids[0]))[0]
    mount = next(
        item for item in container["Mounts"] if item["Destination"] == "/data"
    )
    configuration = _configuration()
    selected = (
        configuration.read_env(project).get(
            "MARINKINO_REDIS_VOLUME", "marinkino-redis-data"
        )
        or "marinkino-redis-data"
    )
    if not re.fullmatch(r"[a-zA-Z0-9][a-zA-Z0-9_.-]{0,127}", selected):
        raise ValueError("Invalid Redis volume name")
    if mount.get("Type") == "volume" and mount.get("Name") == selected:
        return
    # Every retry gets a fresh volume. A failed/rolled-back attempt is retained
    # for manual recovery and is never overwritten or silently reused.
    selected = "marinkino-redis-migration-" + secrets.token_hex(12)
    run(
        "docker",
        "volume",
        "create",
        "--label",
        "io.marinkino.security=redis",
        "--label",
        "io.marinkino.security.project=" + str(project.resolve()),
        selected,
    )
    # Copy through the already-mounted source, never a replaceable host path.
    run(
        "docker",
        "compose",
        "--project-directory",
        str(project),
        "stop",
        "app",
        "redis",
    )
    run(
        "docker",
        "run",
        "--rm",
        "--read-only",
        "--network",
        "none",
        "--cap-drop",
        "ALL",
        "--cap-add",
        "DAC_OVERRIDE",
        "--cap-add",
        "CHOWN",
        "--cap-add",
        "FOWNER",
        "--volumes-from",
        ids[0] + ":ro",
        "-v",
        selected + ":/migration",
        "--entrypoint",
        "sh",
        "redis:7-alpine",
        "-ec",
        'test -z "$(ls -A /migration)" || { '
        'echo "Fresh Redis migration volume is not empty" >&2; '
        "exit 1; }; cp -a /data/. /migration/",
    )
    name = "mk-redis-migrate-" + secrets.token_hex(12)
    try:
        # Redis must load the legacy RDB before enabling AOF. Starting directly
        # with --appendonly yes ignores a standalone dump.rdb.
        _migration_redis(name, selected, "no")
        _wait_redis(name)
        _expire_legacy_stats(name)
        before = int(_redis(name, "DBSIZE").strip())
        if _redis(name, "CONFIG", "SET", "appendonly", "yes").strip() != "OK":
            raise RuntimeError("Redis refused AOF conversion")
        _wait_aof(name)
        _stop_migration_redis(name)
        _migration_redis(name, selected, "yes")
        _wait_redis(name)
        after = int(_redis(name, "DBSIZE").strip())
        if before != after:
            raise RuntimeError(
                f"Redis migration key count changed ({before} -> {after}); "
                "original retained. Expired keys may require a fresh retry."
            )
        _stop_migration_redis(name)
        configuration.update_env(project, {"MARINKINO_REDIS_VOLUME": selected})
    finally:
        try:
            run("docker", "rm", "-f", name)
        except subprocess.CalledProcessError:
            pass
    print(f"Redis migrated and AOF verified: {selected}; original retained")


def _configuration():
    """Load the installed sibling helper, never an application-owned import."""
    source = Path(__file__).resolve().with_name("security_config.py")
    spec = importlib.util.spec_from_file_location("mk_runtime_config", source)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _redis(name, *arguments, json_reply=False):
    return run(
        "docker",
        "exec",
        name,
        "redis-cli",
        "--json" if json_reply else "--raw",
        "-e",
        *arguments,
        timeout=15,
    )


def _wait_redis(name, timeout=60):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        try:
            if _redis(name, "PING").strip() == "PONG":
                return
        except (subprocess.CalledProcessError, subprocess.TimeoutExpired):
            pass
        time.sleep(0.25)
    raise RuntimeError("Redis migration instance failed readiness check")


def _persistence(name):
    return {
        key: value.strip()
        for line in _redis(name, "INFO", "persistence").splitlines()
        if ":" in line
        for key, value in [line.split(":", 1)]
    }


def _wait_aof(name, timeout=120):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        state = _persistence(name)
        if (
            state.get("aof_enabled") == "1"
            and state.get("aof_rewrite_in_progress") == "0"
            and state.get("aof_rewrite_scheduled") == "0"
            and state.get("aof_last_bgrewrite_status") == "ok"
            and state.get("aof_last_write_status") == "ok"
            and int(state.get("aof_current_size", "0")) > 0
        ):
            return
        time.sleep(0.25)
    raise RuntimeError("Redis AOF rewrite did not complete successfully")


def _migration_redis(name, volume, appendonly):
    run(
        "docker",
        "run",
        "-d",
        "--name",
        name,
        "--network",
        "none",
        "--read-only",
        "--cap-drop",
        "ALL",
        "--cap-add",
        "CHOWN",
        "--cap-add",
        "SETUID",
        "--cap-add",
        "SETGID",
        "--cap-add",
        "DAC_OVERRIDE",
        "--security-opt",
        "no-new-privileges",
        "--memory",
        "256m",
        "--pids-limit",
        "64",
        "--tmpfs",
        "/tmp:size=16m",
        "-v",
        volume + ":/data",
        "redis:7-alpine",
        "redis-server",
        "--dir",
        "/data",
        "--save",
        "",
        "--appendonly",
        appendonly,
        "--bind",
        "127.0.0.1",
        "--protected-mode",
        "yes",
    )


def _stop_migration_redis(name):
    run("docker", "stop", "--time", "30", name, timeout=40)
    run("docker", "rm", name)


_EXPIRE_LEGACY = """
local page = redis.call('SCAN', ARGV[1], 'MATCH', ARGV[2], 'COUNT', 250)
local changed = 0
local maximum = tonumber(ARGV[3])
for _, key in ipairs(page[2]) do
    local ttl = redis.call('PTTL', key)
    if ttl == -1 or ttl > maximum then
        changed = changed + redis.call('PEXPIRE', key, maximum)
    end
end
return {page[1], changed}
"""


def _expire_legacy_stats(name, retention_seconds=400 * 24 * 60 * 60):
    deadline = time.monotonic() + 120
    changed = 0
    for pattern in ("stats:*", "blog:views:*", "mail:*"):
        cursor = "0"
        for _ in range(100_000):
            if time.monotonic() > deadline:
                raise RuntimeError("Legacy Redis expiration exceeded deadline")
            response = json.loads(
                _redis(
                    name,
                    "EVAL",
                    _EXPIRE_LEGACY,
                    "0",
                    cursor,
                    pattern,
                    str(retention_seconds * 1000),
                    json_reply=True,
                )
            )
            cursor, amount = response
            cursor = str(cursor)
            changed += int(amount)
            if cursor == "0":
                break
        else:
            raise RuntimeError("Legacy Redis expiration exceeded scan limit")
    return changed


def expire_legacy_stats(project):
    ids = run(
        "docker",
        "compose",
        "--project-directory",
        str(project),
        "ps",
        "-q",
        "redis",
    ).split()
    if not ids:
        raise RuntimeError("Live Redis container not found")
    changed = _expire_legacy_stats(ids[0])
    print(f"Legacy statistics expiration bounded: {changed} keys")


def prune(state, extra=None):
    keep = set()
    paths = [state / "current-compose.json", state / "previous-compose.json"]
    if extra:
        paths.append(extra)
    for path in paths:
        if path.is_file():
            document = json.loads(path.read_text())
            keep.update(
                service["image"]
                for service in document.get("services", {}).values()
            )
    containers = run("docker", "ps", "-aq").split()
    if containers:
        keep.update(
            item["Image"]
            for item in json.loads(run("docker", "inspect", *containers))
        )
    for line in run(
        "docker",
        "image",
        "ls",
        "--no-trunc",
        "--format",
        "{{json .}}",
        "marinkino-app",
    ).splitlines():
        image = json.loads(line)
        if image["Tag"].startswith("security-") and image["ID"] not in keep:
            run(
                "docker",
                "image",
                "rm",
                image["Repository"] + ":" + image["Tag"],
            )
    run(
        "docker",
        "image",
        "prune",
        "-f",
        "--filter",
        "label=io.marinkino.security.managed=true",
        "--filter",
        "until=168h",
    )
    # Reproducible build cache; retain volumes and operator image tags.
    run(
        "docker",
        "builder",
        "prune",
        "-f",
        "--filter",
        "until=168h",
        "--keep-storage",
        "2GB",
    )


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    snap = commands.add_parser("snapshot")
    snap.add_argument("--project", type=Path, required=True)
    snap.add_argument("--output", type=Path, required=True)
    uid_check = commands.add_parser("check-uid")
    uid_check.add_argument("--project", type=Path, required=True)
    uid_check.add_argument("--uid", type=int, required=True)
    uid_check.add_argument("--gid", type=int, required=True)
    migration = commands.add_parser("migrate-redis")
    migration.add_argument("--project", type=Path, required=True)
    expiration = commands.add_parser("expire-legacy-stats")
    expiration.add_argument("--project", type=Path, required=True)
    cleanup = commands.add_parser("prune")
    cleanup.add_argument("--state", type=Path, required=True)
    cleanup.add_argument("--keep", type=Path)
    for command in ["audit", "smoke"]:
        sub = commands.add_parser(command)
        sub.add_argument("--image", required=True)
        if command == "smoke":
            sub.add_argument("--uid", type=int, required=True)
            sub.add_argument("--gid", type=int, required=True)
    args = parser.parse_args()
    if args.command == "snapshot":
        snapshot(args.project, args.output)
    elif args.command == "check-uid":
        check_uid(args.project, args.uid, args.gid)
    elif args.command == "migrate-redis":
        migrate_redis(args.project)
    elif args.command == "expire-legacy-stats":
        expire_legacy_stats(args.project)
    elif args.command == "prune":
        prune(args.state, args.keep)
    elif args.command == "audit":
        audit(args.image)
    else:
        smoke(args.image, args.uid, args.gid)


if __name__ == "__main__":
    main()

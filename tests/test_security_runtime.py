"""Rollback preserves settings without expanding secret dollars."""

import importlib.util
import json
import stat
import subprocess
from pathlib import Path
from types import SimpleNamespace

import pytest

spec = importlib.util.spec_from_file_location(
    "security_runtime",
    Path(__file__).parents[1] / "scripts/security_runtime.py",
)
runtime = importlib.util.module_from_spec(spec)
spec.loader.exec_module(runtime)


def container():
    return {
        "Name": "/marinkino-app",
        "Image": "sha256:previous",
        "Config": {
            "Labels": {
                "com.docker.compose.project": "marinkino",
                "com.docker.compose.service": "app",
            },
            "Env": ["SECRET=a$b${another}$$literal", "SAFE=ok"],
            "Cmd": ["python", "-m", "serve"],
            "Entrypoint": None,
            "User": "1000:1000",
            "Healthcheck": {
                "Test": ["CMD", "python", "-m", "healthcheck"],
                "Interval": 20000000000,
                "Timeout": 5000000000,
                "Retries": 5,
            },
        },
        "HostConfig": {
            "ReadonlyRootfs": True,
            "Memory": 1024,
            "PidsLimit": 128,
            "CapDrop": ["ALL"],
            "SecurityOpt": ["no-new-privileges"],
            "Tmpfs": {"/tmp": "size=64m"},
            "LogConfig": {
                "Type": "local",
                "Config": {"max-size": "10m", "max-file": "3"},
            },
            "PortBindings": {},
        },
        "NetworkSettings": {
            "Networks": {"marinkino_backend": {"Aliases": ["app"]}}
        },
        "Mounts": [
            {
                "Type": "bind",
                "Source": "/srv/site/data",
                "Destination": "/app/data",
                "RW": True,
            },
            {
                "Type": "volume",
                "Name": "marinkino_app-socket",
                "Destination": "/run/marinkino",
                "RW": True,
            },
        ],
    }


def test_snapshot_preserves_private_runtime_and_literal_secrets(
    tmp_path, monkeypatch
):
    def fake_run(*args, **kwargs):
        if args[1] == "compose":
            return "container-id\n"
        if args[1] == "image":
            return ""
        assert args[:2] == ("docker", "inspect")
        return json.dumps([container()])

    monkeypatch.setattr(runtime, "run", fake_run)
    output = tmp_path / "snapshot.json"
    assert runtime.snapshot(tmp_path, output)
    document = json.loads(output.read_text())
    service = document["services"]["app"]
    assert service["environment"][0] == "SECRET=a$$b$${another}$$$$literal"
    assert service["image"].startswith("marinkino-rollback:security-")
    assert service["read_only"] is True and service["cap_drop"] == ["ALL"]
    assert service["healthcheck"]["interval"] == "20000000000ns"
    assert service["logging"]["options"]["max-file"] == "3"
    assert service["volumes"][0] == "/srv/site/data:/app/data:rw"
    assert document["networks"]["net0"] == {
        "external": True,
        "name": "marinkino_backend",
    }
    assert document["volumes"]["vol0"]["external"] is True
    assert stat.S_IMODE(output.stat().st_mode) == 0o600


def test_empty_deployment_has_no_fake_rollback_file(tmp_path, monkeypatch):
    monkeypatch.setattr(runtime, "run", lambda *a: "")
    output = tmp_path / "snapshot.json"
    assert not runtime.snapshot(tmp_path, output)
    assert not output.exists()


def test_missing_old_image_is_preserved_from_container(monkeypatch):
    commands = []

    def fake_run(*args, **kwargs):
        commands.append(args)
        if args[1:3] == ("image", "tag"):
            raise subprocess.CalledProcessError(1, args)
        return ""

    monkeypatch.setattr(runtime, "run", fake_run)
    reference = runtime.pin_rollback_image(container())
    assert commands[1] == ("docker", "commit", "/marinkino-app", reference)
    assert commands[2] == ("docker", "image", "inspect", reference)


def test_unrecoverable_old_image_aborts_before_snapshot_publication(
    tmp_path, monkeypatch
):
    def fake_run(*args, **kwargs):
        if args[1] == "compose":
            assert "-q" in args and "-aq" not in args
            return "running-id"
        if args[1] == "inspect":
            return json.dumps([container()])
        raise subprocess.CalledProcessError(1, args)

    monkeypatch.setattr(runtime, "run", fake_run)
    output = tmp_path / "snapshot.json"
    with pytest.raises(subprocess.CalledProcessError):
        runtime.snapshot(tmp_path, output)
    assert not output.exists()


def test_verify_snapshot_checks_images_before_compose(tmp_path, monkeypatch):
    output = tmp_path / "snapshot.json"
    output.write_text(
        json.dumps(
            {
                "services": {
                    "app": {"image": "marinkino-rollback:security-saved"}
                }
            }
        )
    )
    commands = []
    monkeypatch.setattr(runtime, "run", lambda *args: commands.append(args))
    runtime.verify_snapshot(output)
    assert commands == [
        ("docker", "image", "inspect", "marinkino-rollback:security-saved"),
        ("docker", "compose", "-f", str(output), "config", "-q"),
    ]


def test_prune_retains_pinned_snapshot_reference(tmp_path, monkeypatch):
    reference = "marinkino-rollback:security-saved"
    (tmp_path / "previous-compose.json").write_text(
        json.dumps({"services": {"app": {"image": reference}}})
    )
    commands = []

    def fake_run(*args, **kwargs):
        commands.append(args)
        if args[1:3] == ("image", "ls") and args[-1] == "marinkino-rollback":
            return json.dumps(
                {
                    "Repository": "marinkino-rollback",
                    "Tag": "security-saved",
                    "ID": "sha256:not-a-saved-reference",
                }
            )
        return ""

    monkeypatch.setattr(runtime, "run", fake_run)
    runtime.prune(tmp_path)
    assert not any(c[1:3] == ("image", "rm") for c in commands)


def test_smoke_runs_the_same_redis_candidate_as_deployment(monkeypatch):
    candidate = "marinkino-redis:security-smoke-test"
    commands = []
    monkeypatch.setenv("MARINKINO_REDIS_IMAGE", candidate)

    def fake_run(*args, **kwargs):
        commands.append(args)
        return "OK"

    monkeypatch.setattr(runtime, "run", fake_run)
    monkeypatch.setattr(runtime.subprocess, "run", lambda *a, **k: None)
    runtime.smoke("marinkino-app:security-test", 1000, 1000)
    redis_run = next(c for c in commands if c[1] == "run" and "--name" in c)
    assert candidate in redis_run
    assert "redis:7-alpine" not in redis_run
    assert "--internal" in commands[0]


@pytest.mark.parametrize("pids_limit", [None, 0, -1, 128])
def test_snapshot_handles_unlimited_legacy_pids_limit(
    tmp_path, monkeypatch, pids_limit
):
    original = container()
    original["HostConfig"]["PidsLimit"] = pids_limit

    def fake_run(*args, **kwargs):
        if args[1] == "compose":
            return "container-id\n"
        return json.dumps([original])

    monkeypatch.setattr(runtime, "run", fake_run)
    output = tmp_path / "snapshot.json"
    assert runtime.snapshot(tmp_path, output)
    service = json.loads(output.read_text())["services"]["app"]
    if pids_limit is not None and pids_limit > 0:
        assert service["pids_limit"] == pids_limit
    else:
        assert "pids_limit" not in service
    assert stat.S_IMODE(output.stat().st_mode) == 0o600


@pytest.mark.parametrize(
    "repository",
    [
        "marinkino-app",
        "marinkino-redis",
        "marinkino-certbot",
        "marinkino-rollback",
    ],
)
def test_prune_only_removes_updater_candidates_outside_retained_images(
    tmp_path, monkeypatch, repository
):
    (tmp_path / "current-compose.json").write_text(
        json.dumps({"services": {"app": {"image": "sha256:current"}}})
    )
    (tmp_path / "previous-compose.json").write_text(
        json.dumps({"services": {"app": {"image": "sha256:previous"}}})
    )
    commands = []

    def fake_run(*args, **kwargs):
        commands.append(args)
        if args[1:3] == ("ps", "-aq"):
            return "running"
        if args[1] == "inspect":
            return json.dumps([{"Image": "sha256:running"}])
        if args[1:3] == ("image", "ls"):
            if args[-1] != repository:
                return ""
            return "\n".join(
                json.dumps(
                    {
                        "Repository": repository,
                        "Tag": tag,
                        "ID": "sha256:" + name,
                    }
                )
                for name, tag in [
                    ("current", "security-today"),
                    ("previous", "security-yesterday"),
                    ("running", "security-used"),
                    ("stale", "security-stale"),
                    ("operator", "my-manual-backup"),
                ]
            )
        return ""

    monkeypatch.setattr(runtime, "run", fake_run)
    runtime.prune(tmp_path)
    removed = [args for args in commands if args[1:3] == ("image", "rm")]
    assert removed == [
        ("docker", "image", "rm", repository + ":security-stale")
    ]
    assert not any("volume" in args for args in commands)


def test_existing_private_redis_volume_is_never_copied_or_stopped(
    tmp_path, monkeypatch
):
    (tmp_path / ".env").write_text("")
    data = container()
    data["Mounts"] = [
        {
            "Type": "volume",
            "Name": "marinkino-redis-data",
            "Destination": "/data",
        }
    ]
    commands = []

    def fake_run(*args, **kwargs):
        commands.append(args)
        return "id" if args[1] == "compose" else json.dumps([data])

    monkeypatch.setattr(runtime, "run", fake_run)
    runtime.migrate_redis(tmp_path)
    assert len(commands) == 2


def test_snapshot_includes_auth_redis(tmp_path, monkeypatch):
    original = container()
    auth = container()
    auth["Name"] = "/marinkino-redis-auth"
    auth["Config"]["Labels"]["com.docker.compose.service"] = "redis-auth"
    commands = []

    def fake_run(*args, **kwargs):
        commands.append(args)
        if args[1] == "compose":
            return "app-id auth-id"
        return json.dumps([original, auth])

    monkeypatch.setattr(runtime, "run", fake_run)
    output = tmp_path / "snapshot.json"
    runtime.snapshot(tmp_path, output)
    assert "redis-auth" in commands[0]
    assert "redis-auth" in json.loads(output.read_text())["services"]


@pytest.fixture
def migration_docker(monkeypatch):
    previous = container()
    previous["Mounts"] = [
        {
            "Type": "bind",
            "Source": "/legacy/redis",
            "Destination": "/data",
        }
    ]
    state = {
        "commands": [],
        "selected": [],
        "sizes": [17, 17],
        "started": [],
        "rewrites": 0,
        "failed": False,
    }

    def fake_run(*args, **kwargs):
        state["commands"].append(args)
        if args[1] == "compose":
            return "old-redis" if "-aq" in args else ""
        if args[1] == "inspect":
            return json.dumps([previous])
        if args[1:3] == ("volume", "create"):
            return args[-1]
        if args[1] == "run" and "--name" in args:
            state["started"].append(args[args.index("--appendonly") + 1])
            return "temporary-redis"
        if args[1] != "exec":
            return ""
        command = args[6:]
        if command[0] == "PING":
            return "PONG"
        if command[0] == "EVAL":
            return '["0", 1]'
        if command[0] == "DBSIZE":
            return str(state["sizes"].pop(0))
        if command[0] == "CONFIG":
            return "OK"
        if command[0] == "INFO":
            state["rewrites"] += 1
            progress = int(state["rewrites"] == 1)
            return (
                "aof_enabled:1\n"
                f"aof_rewrite_in_progress:{progress}\n"
                "aof_rewrite_scheduled:0\n"
                "aof_last_bgrewrite_status:ok\n"
                "aof_last_write_status:ok\n"
                "aof_current_size:900\n"
            )
        raise AssertionError(f"Unexpected Redis command: {command}")

    helper = SimpleNamespace(
        read_env=lambda _: {"MARINKINO_REDIS_VOLUME": "failed-old-volume"},
        update_env=lambda _, updates: state["selected"].append(updates),
    )
    monkeypatch.setattr(runtime, "run", fake_run)
    monkeypatch.setattr(runtime, "_configuration", lambda: helper)
    monkeypatch.setattr(runtime.time, "sleep", lambda _: None)
    return state


def test_migration_loads_rdb_waits_for_aof_and_reopens_before_commit(
    tmp_path,
    migration_docker,
    monkeypatch,
):
    state = migration_docker
    candidate = "marinkino-redis:security-test"
    monkeypatch.setenv("MARINKINO_REDIS_IMAGE", candidate)
    runtime.migrate_redis(tmp_path)
    assert state["started"] == ["no", "yes"]
    assert state["rewrites"] == 2
    assert not state["sizes"]
    assert len(state["selected"]) == 1
    volume = state["selected"][0]["MARINKINO_REDIS_VOLUME"]
    assert volume.startswith("marinkino-redis-migration-")
    copies = [c for c in state["commands"] if "--volumes-from" in c]
    assert len(copies) == 1
    assert "old-redis:ro" in copies[0] and volume + ":/migration" in copies[0]
    redis_runs = [c for c in state["commands"] if c[1] == "run"]
    assert len(redis_runs) == 3
    assert all(
        candidate in c and "redis:7-alpine" not in c for c in redis_runs
    )
    assert "io.marinkino.security=redis" in next(
        c for c in state["commands"] if c[1:3] == ("volume", "create")
    )
    config = next(i for i, c in enumerate(state["commands"]) if "CONFIG" in c)
    reopen = next(
        i
        for i, c in enumerate(state["commands"])
        if "--appendonly" in c and c[-5] == "yes"
    )
    assert config < reopen
    assert not any(c[1:3] == ("volume", "rm") for c in state["commands"])


def test_failed_migration_never_commits_and_retry_uses_new_volume(
    tmp_path,
    migration_docker,
):
    state = migration_docker
    state["sizes"] = [17, 0]
    with pytest.raises(RuntimeError, match="key count changed"):
        runtime.migrate_redis(tmp_path)
    assert not state["selected"]
    first = next(
        c[-1] for c in state["commands"] if c[1:3] == ("volume", "create")
    )
    state["sizes"] = [17, 17]
    runtime.migrate_redis(tmp_path)
    second = state["selected"][0]["MARINKINO_REDIS_VOLUME"]
    assert first != second
    copies = [c for c in state["commands"] if "--volumes-from" in c]
    assert first + ":/migration" in copies[0]
    assert second + ":/migration" in copies[1]
    assert not any(c[1:3] == ("volume", "rm") for c in state["commands"])


def test_aof_timeout_aborts_without_committing(
    tmp_path, migration_docker, monkeypatch
):
    state = migration_docker
    monkeypatch.setattr(
        runtime,
        "_wait_aof",
        lambda _: (_ for _ in ()).throw(
            RuntimeError("Redis AOF rewrite did not complete successfully")
        ),
    )
    with pytest.raises(RuntimeError, match="AOF rewrite"):
        runtime.migrate_redis(tmp_path)
    assert not state["selected"]
    assert state["started"] == ["no"]


def test_legacy_expiration_scans_pages_and_caps_ttl_without_keys(monkeypatch):
    calls = []
    pages = iter(['["11", 2]', '["0", 1]', '["0", 0]', '["0", 3]'])

    def redis(*args, **kwargs):
        calls.append(args)
        assert kwargs == {"json_reply": True}
        return next(pages)

    monkeypatch.setattr(runtime, "_redis", redis)
    assert runtime._expire_legacy_stats("redis") == 6
    assert calls[0][-3:] == ("0", "stats:*", "34560000000")
    assert calls[1][-3] == "11"
    assert calls[2][-2] == "blog:views:*"
    assert calls[3][-2] == "mail:*"
    assert "'SCAN'" in calls[0][2] and "'PEXPIRE'" in calls[0][2]
    assert "'KEYS'" not in calls[0][2]


def test_failed_osv_inventory_response_cannot_pass_audit(monkeypatch):
    monkeypatch.setattr(
        runtime, "run", lambda *a: json.dumps([["Flask", "3.1.3"]])
    )

    class Response:
        def __enter__(self):
            return self

        def __exit__(self, *a):
            pass

        def read(self):
            return b'{"results": []}'

    monkeypatch.setattr(
        runtime.urllib.request, "urlopen", lambda *a, **k: Response()
    )
    with pytest.raises(RuntimeError, match="Incomplete"):
        runtime.audit("candidate")

"""Exercise device admission using Redis commands and the actual Lua script."""

from concurrent.futures import ThreadPoolExecutor
from threading import Barrier
from time import time

import fakeredis
import pytest

from device_sessions import (
    DEVICE_IDLE_SECONDS,
    MAX_DEVICES,
    DeviceSessionStore,
)


@pytest.fixture
def devices():
    redis = fakeredis.FakeRedis(decode_responses=True)
    return redis, DeviceSessionStore(redis)


def test_only_five_devices_allowed_and_existing_device_can_refresh(devices):
    redis, store = devices
    assert MAX_DEVICES == 3
    assert all(
        store.register("alice", f"device-{i}") for i in range(MAX_DEVICES)
    )
    assert not store.register("alice", "extra")
    assert store.register("alice", "device-0")
    assert redis.zcard(store.key("alice")) == MAX_DEVICES


def test_simultaneous_logins_cannot_exceed_device_limit(devices):
    redis, store = devices
    attempts = 12
    barrier = Barrier(attempts)

    def register(index):
        barrier.wait(timeout=10)
        return store.register("alice", f"device-{index}")

    with ThreadPoolExecutor(max_workers=attempts) as pool:
        results = list(pool.map(register, range(attempts)))

    assert sum(results) == MAX_DEVICES
    assert redis.zcard(store.key("alice")) == MAX_DEVICES


def test_expired_device_frees_slot_without_returning_to_site(devices):
    redis, store = devices
    now = time()
    redis.zadd(
        store.key("alice"),
        {
            "expired": now - DEVICE_IDLE_SECONDS,
            **{f"active-{i}": now - 60 for i in range(MAX_DEVICES - 1)},
        },
    )

    assert store.register("alice", "replacement")
    assert redis.zscore(store.key("alice"), "expired") is None
    assert redis.zcard(store.key("alice")) == MAX_DEVICES
    assert not store.touch("alice", "expired")


def test_request_refreshes_activity_and_redis_expiration(devices):
    redis, store = devices
    old_activity = time() - DEVICE_IDLE_SECONDS + 60
    redis.zadd(store.key("alice"), {"active": old_activity})
    redis.expire(store.key("alice"), 60)

    assert store.touch("alice", "active")
    assert redis.zscore(store.key("alice"), "active") > old_activity
    assert DEVICE_IDLE_SECONDS - 1 <= redis.ttl(store.key("alice"))
    assert redis.ttl(store.key("alice")) <= DEVICE_IDLE_SECONDS


def test_expired_or_unknown_device_cannot_be_restored_by_request(devices):
    redis, store = devices
    redis.zadd(
        store.key("alice"),
        {"expired": time() - DEVICE_IDLE_SECONDS - 1},
    )

    assert not store.touch("alice", "expired")
    assert not store.touch("alice", "unknown")
    assert redis.zcard(store.key("alice")) == 0


def test_logout_frees_slot_and_revoked_id_cannot_refresh(devices):
    _, store = devices
    for index in range(MAX_DEVICES):
        assert store.register("alice", f"device-{index}")

    store.release("alice", "device-1")

    assert not store.touch("alice", "device-1")
    assert store.register("alice", "replacement")


def test_limit_and_logout_are_scoped_to_each_user(devices):
    redis, store = devices
    for username in ("alice", "bob"):
        for index in range(MAX_DEVICES):
            assert store.register(username, f"device-{index}")

    store.release("alice", "device-0")

    assert redis.zcard(store.key("alice")) == MAX_DEVICES - 1
    assert redis.zcard(store.key("bob")) == MAX_DEVICES
    assert not store.register("bob", "extra")

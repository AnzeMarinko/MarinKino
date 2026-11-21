from datetime import datetime, timezone

import fakeredis

from analytics_privacy import migrate_statistics


def test_migration_preserves_totals_without_identifiers_or_expiry():
    store = fakeredis.FakeRedis(decode_responses=True)
    key = "blog:views:post:2026-11-06"
    store.hset(key, mapping={"192.0.2.1": 3, "2001:db8::1": 2, "views": 4})
    store.expire(key, 1000)
    store.hset("stats:geo:2026-11-06", "192.0.2.1", "city")
    store.set("stats:geo:seen:2026-11-06:digest", 1)
    store.hset("stats:referrer:2026-11-06", "google", 3)
    store.hset("stats:referrer_content:2026-11-06:blog", "google", 2)
    store.sadd("blog:unique:all:post", "old-digest")
    store.sadd("blog:unique:post:2026-11-06", "old-digest")
    store.sadd("blog:unique:current:post", "new-digest")
    store.set("auth:session:keep", "private")
    assert migrate_statistics(store) == {
        "aggregated_days": 1,
        "removed_geo_keys": 2,
        "removed_referrer_keys": 2,
        "removed_legacy_unique_keys": 2,
    }
    assert store.hgetall(key) == {"views": "9"}
    assert store.ttl(key) == -1
    assert store.get("auth:session:keep") == "private"
    assert not list(store.scan_iter("stats:referrer:*"))
    assert not list(store.scan_iter("stats:referrer_content:*"))
    assert store.get("blog:unique:exact-start") == datetime.now(
        timezone.utc
    ).date().isoformat()
    assert store.scard("blog:unique:current:post") == 1
    assert migrate_statistics(store) == {
        "aggregated_days": 0,
        "removed_geo_keys": 0,
        "removed_referrer_keys": 0,
        "removed_legacy_unique_keys": 0,
    }


def test_migration_removes_expiry_from_existing_day():
    store = fakeredis.FakeRedis(decode_responses=True)
    key = "blog:views:post:2026-08-08"
    store.hset(key, "192.0.2.1", 3)
    store.pexpire(key, 400)
    migrate_statistics(store)
    assert store.pttl(key) == -1


def test_migration_supports_redis_bytes_responses():
    store = fakeredis.FakeRedis()
    store.sadd("blog:unique:all:post", "digest")

    result = migrate_statistics(store)

    assert result["removed_legacy_unique_keys"] == 1
    assert store.get("blog:unique:exact-start")
    assert store.exists("blog:unique:all:post") == 0

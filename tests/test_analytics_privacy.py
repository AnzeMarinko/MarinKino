import fakeredis

from analytics_privacy import migrate_statistics


def test_migration_preserves_totals_and_expiry_without_identifiers():
    store = fakeredis.FakeRedis(decode_responses=True)
    key = "blog:views:post:2026-11-06"
    store.hset(key, mapping={"192.0.2.1": 3, "2001:db8::1": 2, "views": 4})
    store.expire(key, 1000)
    store.hset("stats:geo:2026-11-06", "192.0.2.1", "city")
    store.set("stats:geo:seen:2026-11-06:digest", 1)
    store.set("auth:session:keep", "private")
    assert migrate_statistics(store) == {
        "aggregated_days": 1,
        "removed_geo_keys": 2,
    }
    assert store.hgetall(key) == {"views": "9"}
    assert 0 < store.ttl(key) <= 1000
    assert store.get("auth:session:keep") == "private"
    assert migrate_statistics(store) == {
        "aggregated_days": 0,
        "removed_geo_keys": 0,
    }


def test_migration_does_not_extend_a_nearly_expired_day():
    store = fakeredis.FakeRedis(decode_responses=True)
    key = "blog:views:post:2026-08-08"
    store.hset(key, "192.0.2.1", 3)
    store.pexpire(key, 400)
    migrate_statistics(store)
    assert 0 < store.pttl(key) <= 400

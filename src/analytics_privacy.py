"""Remove legacy visitor analytics while preserving view totals."""

import os
import sys
from datetime import datetime, timezone

from redis import Redis

_AGGREGATE = """
if redis.call('TYPE', KEYS[1]).ok ~= 'hash' then return 0 end
local fields = redis.call('HGETALL', KEYS[1])
local total = 0
local legacy = false
for i = 1, #fields, 2 do
    total = total + (tonumber(fields[i + 1]) or 0)
    if fields[i] ~= 'views' then legacy = true end
end
if legacy then
    redis.call('DEL', KEYS[1])
    redis.call('HSET', KEYS[1], 'views', total)
end
redis.call('PERSIST', KEYS[1])
return legacy and 1 or 0
"""


def migrate_statistics(redis):
    """Preserve views, start exact unique tracking, and remove old IP sets."""
    aggregate = redis.register_script(_AGGREGATE)
    converted = sum(
        int(aggregate(keys=[key]))
        for key in redis.scan_iter(match="blog:views:*", count=100)
    )
    removed = 0
    for key in redis.scan_iter(match="stats:geo:*", count=100):
        removed += redis.unlink(key)
    removed_referrer = 0
    for pattern in ("stats:referrer:*", "stats:referrer_content:*"):
        for key in redis.scan_iter(match=pattern, count=100):
            removed_referrer += redis.unlink(key)
    tracking_start = datetime.now(timezone.utc).date().isoformat()
    redis.set("blog:unique:exact-start", tracking_start, nx=True)
    removed_unique = 0
    for key in redis.scan_iter(match="blog:unique:*", count=100):
        key_name = key.decode() if isinstance(key, bytes) else key
        if key_name == "blog:unique:exact-start" or key_name.startswith(
            "blog:unique:current:"
        ):
            continue
        removed_unique += redis.unlink(key)
    return {
        "aggregated_days": converted,
        "removed_geo_keys": removed,
        "removed_referrer_keys": removed_referrer,
        "removed_legacy_unique_keys": removed_unique,
    }


if __name__ == "__main__":
    client = Redis(
        host=os.getenv("REDIS_HOST", "localhost"),
        port=int(os.getenv("REDIS_PORT", "6379")),
        socket_timeout=10,
        socket_connect_timeout=2,
    )
    if not sys.argv[1:]:
        print(migrate_statistics(client))
    else:
        raise SystemExit("Unknown analytics_privacy option")

"""Remove legacy visitor identifiers while preserving daily view totals."""

import os

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
if not legacy then return 0 end
local ttl = redis.call('PTTL', KEYS[1])
redis.call('DEL', KEYS[1])
redis.call('HSET', KEYS[1], 'views', total)
local remaining = ttl >= 0 and math.min(ttl, 7776000000) or 7776000000
redis.call('PEXPIRE', KEYS[1], remaining)
return 1
"""


def migrate_statistics(redis):
    """Idempotent; each hash conversion is atomic with concurrent new views."""
    aggregate = redis.register_script(_AGGREGATE)
    converted = sum(
        int(aggregate(keys=[key]))
        for key in redis.scan_iter(match="blog:views:*", count=100)
    )
    removed = 0
    for key in redis.scan_iter(match="stats:geo:*", count=100):
        removed += redis.unlink(key)
    return {"aggregated_days": converted, "removed_geo_keys": removed}


if __name__ == "__main__":
    client = Redis(
        host=os.getenv("REDIS_HOST", "localhost"),
        port=int(os.getenv("REDIS_PORT", "6379")),
        socket_timeout=10,
        socket_connect_timeout=2,
    )
    print(migrate_statistics(client))

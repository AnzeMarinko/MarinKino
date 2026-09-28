"""Track active devices and reclaim slots after 7 days without activity."""

from redis import Redis

DEVICE_IDLE_SECONDS = 7 * 24 * 60 * 60
MAX_DEVICES = 3

_REFRESH_DEVICE = """
local key = KEYS[1]
local device_id = ARGV[1]
local idle_seconds = tonumber(ARGV[2])
local max_devices = tonumber(ARGV[3])
local allow_new = ARGV[4] == '1'
local previous_device_id = ARGV[5]
local server_time = redis.call('TIME')
local now = tonumber(server_time[1]) + tonumber(server_time[2]) / 1000000

redis.call('ZREMRANGEBYSCORE', key, '-inf', now - idle_seconds)

local previous_active = allow_new and previous_device_id ~= ''
    and redis.call('ZSCORE', key, previous_device_id)

if not redis.call('ZSCORE', key, device_id) then
    if not allow_new then
        return 0
    end
    if not previous_active and redis.call('ZCARD', key) >= max_devices then
        return 0
    end
end

if previous_active and previous_device_id ~= device_id then
    redis.call('ZREM', key, previous_device_id)
end

redis.call('ZADD', key, now, device_id)
redis.call('EXPIRE', key, idle_seconds)
return 1
"""


class DeviceSessionStore:
    """Keep device admission and idle expiration atomic across app workers."""

    def __init__(self, redis_client: Redis):
        self._redis = redis_client
        self._refresh_device = redis_client.register_script(_REFRESH_DEVICE)

    @staticmethod
    def key(user_id: str) -> str:
        return f"auth:devices:{user_id}"

    def _refresh(
        self,
        user_id: str,
        device_id: str,
        allow_new: bool,
        previous_device_id: str | None = None,
    ) -> bool:
        return bool(
            self._refresh_device(
                keys=[self.key(user_id)],
                args=[
                    device_id,
                    DEVICE_IDLE_SECONDS,
                    MAX_DEVICES,
                    int(allow_new),
                    previous_device_id or "",
                ],
            )
        )

    def register(
        self,
        user_id: str,
        device_id: str,
        previous_device_id: str | None = None,
    ) -> bool:
        """Admit a device or rotate its active slot, reclaiming idle slots."""
        return self._refresh(
            user_id,
            device_id,
            allow_new=True,
            previous_device_id=previous_device_id,
        )

    def touch(self, user_id: str, device_id: str) -> bool:
        """Refresh an active device; never restore expired or revoked IDs."""
        return self._refresh(user_id, device_id, allow_new=False)

    def release(self, user_id: str, device_id: str) -> None:
        """Free this device's slot immediately on logout."""
        self._redis.zrem(self.key(user_id), device_id)

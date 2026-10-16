"""Bounded, expiring caches for caller-controlled keys."""

import time
from collections import OrderedDict
from functools import wraps
from threading import Lock


def ttl_cache(ttl=600, maxsize=128):
    def decorate(function):
        values = OrderedDict()
        guard = Lock()

        @wraps(function)
        def cached(*args, **kwargs):
            key = (args, tuple(sorted(kwargs.items())))
            now = time.monotonic()
            with guard:
                hit = values.get(key)
                if hit and hit[0] > now:
                    values.move_to_end(key)
                    return hit[1]
                values.pop(key, None)
            result = function(*args, **kwargs)
            with guard:
                values[key] = (time.monotonic() + ttl, result)
                values.move_to_end(key)
                while len(values) > maxsize:
                    values.popitem(last=False)
            return result

        def clear():
            with guard:
                values.clear()

        cached.cache_clear = clear
        return cached

    return decorate

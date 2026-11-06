"""Bounded dashboard snapshots using standard-library aggregation."""

import json
from collections import Counter
from copy import deepcopy
from datetime import date, timedelta
from itertools import islice
from threading import Lock
from time import monotonic


def _hashes(redis, keys):
    """Batch round trips without retaining the complete Redis keyspace."""
    keys = iter(keys)
    while batch := list(islice(keys, 100)):
        pipe = redis.pipeline(transaction=False)
        for key in batch:
            pipe.hgetall(key)
        yield from zip(batch, pipe.execute())


def _daily_access(redis, today):
    cutoff = (today - timedelta(days=30)).isoformat()
    last_day = today.isoformat()
    keys = (
        key
        for key in redis.scan_iter("stats:daily:*", count=100)
        if cutoff <= key.split(":")[2] <= last_day
    )
    statuses = {}
    totals = Counter()
    for key, routes in _hashes(redis, keys):
        _, _, day, user, status = key.split(":", 4)
        status = status[0] + "xx"
        entry = (
            statuses.setdefault(status, {})
            .setdefault(day, {})
            .setdefault(user, {"routes": Counter(), "count": 0})
        )
        for route, count in routes.items():
            count = int(count)
            entry["routes"][route] += count
            entry["count"] += count
            if status in {"2xx", "3xx"}:
                totals[user] += count
    for days in statuses.values():
        for day, entries in days.items():
            for entry in entries.values():
                entry["routes"] = "\n".join(
                    f"{count}x {route}"
                    for count, route in sorted(
                        (
                            (count, route)
                            for route, count in entry["routes"].items()
                        ),
                        reverse=True,
                    )[:10]
                )
            days[day] = dict(
                sorted(entries.items(), key=lambda item: -totals[item[0]])
            )
    return {
        status: dict(sorted(days.items()))
        for status, days in sorted(statuses.items())
    }, [user for user, _count in totals.most_common()]


def _monthly_access(redis, today):
    cutoff = (today - timedelta(days=400)).isoformat()[:7]
    last_month = today.isoformat()[:7]
    keys = (
        key
        for key in redis.scan_iter("stats:monthly:*", count=100)
        if cutoff <= key.rsplit(":", 1)[-1] <= last_month
    )
    months = {}
    totals = Counter()
    for key, counts in _hashes(redis, keys):
        month = Counter()
        for method_route, count in counts.items():
            route = "/" + "/".join(method_route.split("/")[1:3])
            month[route] += int(count)
        months[key.rsplit(":", 1)[-1]] = month
        totals.update(month)
    top_routes = [route for route, _count in totals.most_common(20)]
    return {
        month: {route: counts[route] for route in top_routes}
        for month, counts in sorted(months.items())
    }


def _watch_statistics(redis):
    columns = [
        "Skupen čas",
        "Število začetih",
        "Število ogledanih",
        "Povprečen delež ogleda",
        "Zadnji začetek ogleda",
    ]
    rows = {}
    order = {}
    for key, values in _hashes(redis, redis.scan_iter("prog:*", count=100)):
        total = 0
        ratios = []
        watched = 0
        last_start = "-"
        for progress_json in values.values():
            progress = json.loads(progress_json)
            played = progress.get("total_play_time", 0)
            duration = progress.get("duration", 0)
            if not played or not duration:
                continue
            ratio = played / duration * 100
            if ratio < 5:
                continue
            total += played
            ratios.append(ratio)
            watched += ratio >= 70
            started = progress.get("last_start_time")
            if started and (last_start == "-" or started > last_start):
                last_start = started
        user = key.split(":", 1)[1]
        average = round(sum(ratios) / len(ratios), 1) if ratios else 0
        rows[user] = dict(
            zip(
                columns,
                (
                    f"{int(total // 3600)}h {int(total % 3600 // 60):02}m",
                    len(ratios),
                    watched,
                    f"{average} %",
                    last_start,
                ),
            )
        )
        # Compare seconds, not the formatted duration ("9h" > "10h").
        order[user] = (watched, total)
    return dict(
        sorted(rows.items(), key=lambda item: order[item[0]], reverse=True)
    ), columns if rows else []


def _referrers(redis, today):
    cutoff = (today - timedelta(days=90)).isoformat()
    last_day = today.isoformat()
    keys = (
        key
        for key in redis.scan_iter("stats:referrer:*", count=100)
        if cutoff <= key.rsplit(":", 1)[-1] <= last_day
    )
    sources = {}
    for key, counts in _hashes(redis, keys):
        day = key.rsplit(":", 1)[-1]
        for source, count in counts.items():
            sources.setdefault(source, {})[day] = int(count)
    return sources


def _blog_views(redis, posts, today):
    cutoff = (today - timedelta(days=90)).isoformat()
    last_day = today.isoformat()
    keys = (
        key
        for key in redis.scan_iter("blog:views:*", count=100)
        if key.removeprefix("blog:views:").rsplit(":", 1)[0] in posts
        and cutoff <= key.rsplit(":", 1)[-1] <= last_day
    )
    daily = Counter()
    by_post = {}
    for key, counts in _hashes(redis, keys):
        post_id, day = key.removeprefix("blog:views:").rsplit(":", 1)
        # During migration legacy hashes contain per-IP counts, new hashes
        # contain a single aggregate. Both represent page views, not people.
        views = sum(int(count) for count in counts.values())
        by_post.setdefault(post_id, {})[day] = views
        daily[day] += views
    post_daily = {}
    stats = []
    for post_id, post in posts.items():
        views = by_post.get(post_id, {})
        post_daily[post_id] = {
            "title": post["title"],
            "created_at": post["created_at"][:10],
            "views": views,
        }
        stats.append(
            {
                "id": post_id,
                "title": post["title"],
                "views": sum(views.values()),
                "created_at": post["created_at"][:16],
            }
        )
    return dict(daily), post_daily, stats


def collect_statistics(redis, posts, today):
    access, users = _daily_access(redis, today)
    watch, columns = _watch_statistics(redis)
    blog_daily, blog_posts, blog_stats = _blog_views(redis, posts, today)
    return {
        "access_stats_users": access,
        "users": users,
        "users_stats": watch,
        "users_stats_columns": columns,
        "access_stats_monthly": _monthly_access(redis, today),
        "blog_views_daily": blog_daily,
        "blog_posts_daily": blog_posts,
        "blog_stats": blog_stats,
        "total_blog_views": sum(blog_daily.values()),
        "referrer_stats": _referrers(redis, today),
    }


class AdminStatistics:
    """Share one 30-second aggregate across simultaneous dashboard requests."""

    def __init__(self, redis, ttl=30):
        self.redis = redis
        self.ttl = ttl
        self._lock = Lock()
        self._snapshot = None
        self._key = None
        self._expires = 0

    def snapshot(self, posts, today=None):
        today = today or date.today()
        key = (
            today,
            tuple(
                (post_id, post["title"], post["created_at"])
                for post_id, post in posts.items()
            ),
        )
        with self._lock:
            if self._key != key or monotonic() >= self._expires:
                self._snapshot = collect_statistics(self.redis, posts, today)
                self._key = key
                self._expires = monotonic() + self.ttl
            return deepcopy(self._snapshot)

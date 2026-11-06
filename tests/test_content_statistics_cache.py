"""Cache freshness and bounded statistics preserve visible data."""

import json
import os
from datetime import date
from unittest.mock import Mock

import fakeredis
import pytest

import admin_statistics
import blog_content


@pytest.fixture(autouse=True)
def clear_content_cache():
    blog_content._read_posts.cache_clear()
    blog_content.render_post_content.cache_clear()
    yield
    blog_content._read_posts.cache_clear()
    blog_content.render_post_content.cache_clear()


def test_atomic_replacement_is_visible_and_cached_posts_cannot_be_mutated(
    tmp_path,
):
    target = tmp_path / "posts.json"
    target.write_text('{"post":{"title":"old","images":[]}}')
    original = target.stat()
    loaded = blog_content.load_posts(target)
    loaded["post"]["images"].append("request-only.jpg")
    assert blog_content.load_posts(target)["post"]["images"] == []

    replacement = tmp_path / "replacement.json"
    replacement.write_text('{"post":{"title":"new","images":[]}}')
    os.utime(
        replacement, ns=(original.st_atime_ns, original.st_mtime_ns)
    )
    os.replace(replacement, target)
    assert blog_content.load_posts(target)["post"]["title"] == "new"


def test_cached_missing_file_becomes_visible_when_created(tmp_path):
    target = tmp_path / "posts.json"
    assert blog_content.load_posts(target) == {}
    target.write_text('{"post":{"title":"published"}}')
    assert blog_content.load_posts(target)["post"]["title"] == "published"


def test_cached_markdown_retains_formatting_without_executable_html():
    content = (
        "**Readable** <script>alert(1)</script> "
        '<img src="https://example.com/x.jpg" onerror="alert(2)"> '
        '<a href="javascript:alert(3)">link</a>'
    )
    first = blog_content.render_post_content(content)
    assert "<strong>Readable</strong>" in first
    assert "https://example.com/x.jpg" in first
    assert "<script" not in first
    assert "onerror" not in first
    assert "javascript:" not in first
    assert blog_content.render_post_content(content) == first


def test_statistics_aggregate_legacy_and_private_views_without_old_hash_reads(
    monkeypatch,
):
    redis = fakeredis.FakeRedis(decode_responses=True)
    posts = {
        "one": {"title": "First", "created_at": "2026-11-01T10:00:00"},
        "two": {"title": "Second", "created_at": "2026-11-02T10:00:00"},
    }
    redis.hset("blog:views:one:2026-11-05", mapping={"192.0.2.1": 2})
    redis.hset("blog:views:two:2026-11-05", mapping={"views": 3})
    expired = "blog:views:one:2025-01-01"
    redis.hset(expired, mapping={"192.0.2.1": 900})
    redis.hset(
        "stats:daily:2026-11-05:reader:200 OK",
        mapping={"GET /blog/<post_id>": 5},
    )
    read_keys = []
    make_pipeline = redis.pipeline

    def tracked_pipeline(*args, **kwargs):
        pipe = make_pipeline(*args, **kwargs)
        read_hash = pipe.hgetall

        def tracked_hash(key):
            read_keys.append(key)
            return read_hash(key)

        pipe.hgetall = tracked_hash
        return pipe

    scans = Mock(wraps=redis.scan_iter)
    monkeypatch.setattr(redis, "scan_iter", scans)
    monkeypatch.setattr(redis, "pipeline", tracked_pipeline)
    monkeypatch.setattr(
        redis, "keys", Mock(side_effect=AssertionError("blocking KEYS"))
    )
    result = admin_statistics.collect_statistics(
        redis, posts, date(2026, 11, 6)
    )
    assert result["total_blog_views"] == 5
    assert result["blog_views_daily"] == {"2026-11-05": 5}
    assert result["users"] == ["reader"]
    assert "192.0.2.1" not in json.dumps(result)
    assert expired not in read_keys
    assert sum(
        call.args[0] == "blog:views:*" for call in scans.call_args_list
    ) == 1


def test_statistics_cache_refreshes_after_ttl_and_preserves_snapshot(
    monkeypatch,
):
    redis = fakeredis.FakeRedis(decode_responses=True)
    posts = {"one": {"title": "First", "created_at": "2026-11-01"}}
    key = "blog:views:one:2026-11-05"
    redis.hset(key, mapping={"views": 2})
    clock = Mock(return_value=100)
    monkeypatch.setattr(admin_statistics, "monotonic", clock)
    cache = admin_statistics.AdminStatistics(redis)
    first = cache.snapshot(posts, date(2026, 11, 6))
    first["blog_stats"][0]["title"] = "request-only title"
    redis.hincrby(key, "views", 1)
    cached = cache.snapshot(posts, date(2026, 11, 6))
    assert cached["total_blog_views"] == 2
    assert cached["blog_stats"][0]["title"] == "First"
    clock.return_value = 131
    assert cache.snapshot(posts, date(2026, 11, 6))["total_blog_views"] == 3
    posts["one"]["title"] = "Updated title"
    assert (
        cache.snapshot(posts, date(2026, 11, 6))["blog_stats"][0]["title"]
        == "Updated title"
    )

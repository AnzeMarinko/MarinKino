"""Verify persistent aggregate and privacy-preserving unique blog counts."""

from test_blog_translation import blog as blog_fixture

blog = blog_fixture


def test_blog_views_count_requests_and_unique_hashed_ips(blog, monkeypatch):
    import fakeredis

    redis = fakeredis.FakeRedis(decode_responses=True)
    monkeypatch.setattr(blog.module, "redis_client", redis)
    client = blog.app.test_client()

    for ip in ("192.0.2.1", "192.0.2.1", "192.0.2.2"):
        response = client.get(
            "/blog/javno", environ_base={"REMOTE_ADDR": ip}
        )
        assert response.status_code == 200

    view_keys = list(redis.scan_iter("blog:views:javno:*"))
    assert len(view_keys) == 1
    assert redis.hget(view_keys[0], "views") == "3"
    assert redis.ttl(view_keys[0]) == -1

    unique_key = "blog:unique:current:javno"
    hashes = redis.smembers(unique_key)
    assert len(hashes) == 2
    assert redis.ttl(unique_key) == -1
    assert "192.0.2.1" not in hashes
    assert "192.0.2.2" not in hashes

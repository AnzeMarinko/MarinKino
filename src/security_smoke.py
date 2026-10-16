"""Run only inside the updater's disposable container and private Redis."""

import json
import os
from pathlib import Path


def main():
    if os.getenv("FLASK_ENV") != "testing":
        raise RuntimeError("Smoke tests require isolated testing mode")
    from werkzeug.security import generate_password_hash

    password = "Disposable-Only-Password!42"
    Path("data").mkdir(exist_ok=True)
    Path("data/test_users.json").write_text(
        json.dumps(
            {
                "member": {
                    "password_hash": generate_password_hash(password),
                    "is_admin": False,
                    "first_login": False,
                    "emails": [],
                }
            }
        )
    )
    Path("data/blog_posts.json").write_text(
        json.dumps(
            {
                "private-draft": {
                    "id": "private-draft",
                    "slug": "private-draft",
                    "title": "Private draft",
                    "content": "Secret draft",
                    "published": False,
                    "created_at": "2026-01-01T00:00:00+00:00",
                }
            }
        )
    )
    folder = Path("data/movies/01-films/Example")
    folder.mkdir(parents=True)
    (folder / "readme.json").write_text(
        json.dumps(
            {
                "Title": "Example",
                "Genres": [],
                "user_notes": {
                    "private@example.invalid": {
                        "comment": "PRIVATE-NOTE-SENTINEL"
                    }
                },
                "ratings": {},
            }
        )
    )
    from flask import request

    from app import app
    from blueprints.auth_bp import device_sessions

    @app.get("/_isolated_proxy_probe")
    def probe():
        return {"ip": request.remote_addr, "secure": request.is_secure}

    app.config["TESTING"] = True
    client = app.test_client()
    assert client.get("/healthz").status_code == 200
    assert (
        client.get("/login", headers={"Host": "attacker.invalid"}).status_code
        == 400
    )
    assert (
        client.post(
            "/login", data={"username": "member", "password": password}
        ).status_code
        == 400
    )
    assert client.get("/logout").status_code in {302, 405}
    assert client.get("/blog/private-draft").status_code == 404
    assert client.get("/music/file/readme.json").status_code == 302
    assert client.get("/login").headers["X-Content-Type-Options"] == "nosniff"
    token = client.get("/csrf-token").json["csrf_token"]
    response = client.post(
        "/login",
        data={"username": "member", "password": password, "csrf_token": token},
    )
    assert response.status_code == 302, response.status_code
    assert device_sessions._redis.zcard(device_sessions.key("member")) == 1
    response = client.get("/blog/private-draft")
    assert response.status_code == 200, response.status_code
    assert b"Secret draft" in response.data
    assert "no-store" in response.headers["Cache-Control"]
    for path in ["/blog", "/blog?q=draft"]:
        response = client.get(path)
        assert response.status_code == 200
        assert b"Private draft" not in response.data
        assert b"Secret draft" not in response.data
        assert b'href="/blog/private-draft"' not in response.data
    assert (
        client.get("/movies/file/01-films/Example/readme.json").status_code
        == 404
    )
    for path in ["/movies", "/movies/page"]:
        response = client.get(path)
        assert response.status_code == 200, (path, response.status_code)
        assert b"PRIVATE-NOTE-SENTINEL" not in response.data
        assert b"private@example.invalid" not in response.data
    # Validate the actual Waitress proxy boundary over a Unix socket.
    import http.client
    import socket
    import threading

    from waitress import create_server

    socket_path = os.path.join(
        os.getenv("MARINKINO_SMOKE_SOCKET_DIR", "/run/marinkino"), "smoke.sock"
    )
    server = create_server(
        app,
        unix_socket=socket_path,
        unix_socket_perms="600",
        trusted_proxy="localhost",
        trusted_proxy_count=1,
        trusted_proxy_headers={"x-forwarded-for", "x-forwarded-proto"},
    )
    closing = threading.Event()
    server_errors = []

    def run_server():
        import errno

        try:
            server.run()
        except Exception as error:
            # Closing a selected fd from another thread can wake select with
            # EBADF on macOS. Accept only this post-response shutdown race.
            if not (
                closing.is_set()
                and isinstance(error, OSError)
                and error.errno == errno.EBADF
            ):
                server_errors.append(error)

    thread = threading.Thread(target=run_server, daemon=True)
    thread.start()
    try:
        connection = http.client.HTTPConnection("localhost", timeout=5)
        sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        sock.connect(socket_path)
        connection.sock = sock
        connection.request(
            "GET",
            "/_isolated_proxy_probe",
            headers={
                "Host": "localhost",
                "X-Forwarded-For": "203.0.113.8",
                "X-Forwarded-Proto": "https",
            },
        )
        response = connection.getresponse()
        assert response.status == 200
        assert json.loads(response.read()) == {
            "ip": "203.0.113.8",
            "secure": True,
        }
        connection.close()
    finally:
        closing.set()
        server.close()
        thread.join(timeout=2)
        server.task_dispatcher.shutdown()
    assert not server_errors, server_errors
    print(
        "Smoke tests passed: CSRF, host validation, sessions, drafts, "
        "private movie data, trusted proxy"
    )


if __name__ == "__main__":
    main()

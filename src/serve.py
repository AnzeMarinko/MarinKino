"""Production entry point: only Nginx can reach the shared Unix socket."""

import os

from waitress import serve

from app import app

if __name__ == "__main__":
    os.umask(0o027)
    serve(
        app,
        unix_socket="/run/marinkino/app.sock",
        # Access is restricted by the private Docker volume and its directory.
        unix_socket_perms="666",
        trusted_proxy="localhost",
        trusted_proxy_count=1,
        trusted_proxy_headers={"x-forwarded-for", "x-forwarded-proto"},
        clear_untrusted_proxy_headers=True,
        threads=4,
        connection_limit=128,
        channel_timeout=60,
        max_request_body_size=40 * 1024 * 1024,
        max_request_header_size=16384,
        expose_tracebacks=False,
        ident="",
    )

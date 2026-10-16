"""Probe the private application socket."""

import http.client
import os
import socket


def check():
    connection = http.client.HTTPConnection("localhost", timeout=5)
    sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
    sock.settimeout(5)
    try:
        sock.connect("/run/marinkino/app.sock")
        connection.sock = sock
        connection.request(
            "GET",
            "/healthz",
            headers={"Host": os.getenv("WWW_DOMAIN", "localhost")},
        )
        return connection.getresponse().status == 200
    finally:
        connection.close()
        sock.close()


if __name__ == "__main__":
    raise SystemExit(0 if check() else 1)

"""Privacy-preserving, per-post lifetime IP identifiers."""

import hashlib
import hmac
import ipaddress


def blog_ip_digest(secret_key: str, client_ip: str) -> str:
    normalized_ip = ipaddress.ip_address(client_ip).compressed
    return hmac.new(
        secret_key.encode(),
        b"blog-unique-ip-lifetime-v1\0" + normalized_ip.encode(),
        hashlib.sha256,
    ).hexdigest()

"""Protection for the local web servers (the app and the voice studio).

They listen on 127.0.0.1 only, but a web page you visit could still try to reach them, either directly
(cross-site requests) or by pointing a domain it controls at 127.0.0.1 (DNS rebinding). Two checks
stop both:

- the Host header must be a loopback name, so a rebinding domain is refused;
- requests that change something must come from the same origin (or have no Origin at all, as with
  curl and other local tools), so another site can't post, upload or delete.
"""

from __future__ import annotations

from urllib.parse import urlparse

LOOPBACK = {"127.0.0.1", "localhost", "[::1]", "::1"}


def host_ok(host: str | None) -> bool:
    """True when the Host header names this machine (with or without a port)."""
    if not host:
        return False
    name = host.rsplit(":", 1)[0] if not host.startswith("[") else host.split("]")[0] + "]"
    return name.lower() in LOOPBACK


def origin_ok(origin: str | None, host: str | None) -> bool:
    """True for same-origin requests and for clients that send no Origin (curl, scripts)."""
    if not origin:
        return True
    if origin == "null":
        return False
    o = urlparse(origin)
    return o.netloc == host and o.scheme == "http"


def allowed(method: str, headers) -> bool:
    host = headers.get("Host")
    if not host_ok(host):
        return False
    if method in ("POST", "PUT", "PATCH", "DELETE"):
        return origin_ok(headers.get("Origin"), host)
    return True

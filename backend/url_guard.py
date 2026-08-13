"""Shared SSRF-safe URL fetching helpers.

Blocks server-side attackers from pointing our outbound HTTP fetches at
loopback, private, link-local, or cloud-metadata addresses. Every hop of
a redirect is re-checked.
"""
from __future__ import annotations

import ipaddress
import socket
from urllib.parse import urlparse

import httpx

# RFC1918 + loopback + link-local + IPv6 unique-local + IPv4 metadata (169.254.169.254)
_DENY_NETS = [
    ipaddress.ip_network("10.0.0.0/8"),
    ipaddress.ip_network("172.16.0.0/12"),
    ipaddress.ip_network("192.168.0.0/16"),
    ipaddress.ip_network("127.0.0.0/8"),
    ipaddress.ip_network("169.254.0.0/16"),  # includes cloud metadata
    ipaddress.ip_network("0.0.0.0/8"),
    ipaddress.ip_network("100.64.0.0/10"),  # CGNAT
    ipaddress.ip_network("::1/128"),
    ipaddress.ip_network("fc00::/7"),
    ipaddress.ip_network("fe80::/10"),
]


class UnsafeURLError(ValueError):
    """URL points at a disallowed target (private/internal/metadata)."""


def _is_denied(ip_str: str) -> bool:
    try:
        ip = ipaddress.ip_address(ip_str)
    except ValueError:
        return True  # unparseable -> deny
    return any(ip in net for net in _DENY_NETS)


def check_url(url: str) -> None:
    """Raise UnsafeURLError if the URL points at a disallowed target."""
    if not url:
        raise UnsafeURLError("Empty URL")
    parsed = urlparse(url)
    if parsed.scheme not in ("http", "https"):
        raise UnsafeURLError(f"Only http(s) URLs are allowed (got '{parsed.scheme}')")
    host = parsed.hostname
    if not host:
        raise UnsafeURLError("URL is missing a host")
    # Reject implicit hostnames that look like an IP literal or 'localhost'
    if host.lower() in ("localhost",):
        raise UnsafeURLError("Loopback hostnames are not allowed")
    # Resolve DNS and reject any A/AAAA that lands in a private range
    try:
        infos = socket.getaddrinfo(host, None)
    except socket.gaierror as e:
        raise UnsafeURLError(f"DNS resolution failed: {e}")
    for info in infos:
        ip = info[4][0]
        if _is_denied(ip):
            raise UnsafeURLError(
                f"Host '{host}' resolves to a disallowed address ({ip})"
            )


async def safe_get(url: str, *, timeout: float = 30.0) -> httpx.Response:
    """httpx.get with SSRF guard applied before each redirect hop."""
    check_url(url)
    # follow_redirects=False so we manually validate each hop
    async with httpx.AsyncClient(timeout=timeout, follow_redirects=False) as client:
        for _ in range(5):  # max 5 redirects
            r = await client.get(url)
            if r.is_redirect and r.headers.get("location"):
                next_url = str(r.next_request.url) if r.next_request else r.headers["location"]
                check_url(next_url)
                url = next_url
                continue
            return r
    raise UnsafeURLError("Too many redirects")

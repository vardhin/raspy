"""Network discovery helpers for the connectivity dashboard.

Pure, dependency-light probes that gather the box's reachable addresses so the UI
can show "type this link to reach Raspy from X":

  * local_addresses() — every non-loopback interface IP (IPv4 + IPv6), classified
    LAN/Tailscale/link-local so the UI can group them.
  * public_ip() — the internet-facing IP via a keyless lookup (best-effort; may be
    None offline or when blocked).

No external deps: interface enumeration uses the stdlib ``socket`` tricks that
work without ``netifaces``. Each address is returned with enough metadata for the
caller to build an ``http://<addr>:<port>`` link.
"""

from __future__ import annotations

import ipaddress
import socket
import urllib.request
from typing import Any

# Tailscale's CGNAT range (100.64.0.0/10) — used to tag interface IPs as the
# tailnet address even before we parse `tailscale status`.
_TAILSCALE_NET = ipaddress.ip_network("100.64.0.0/10")
# Tailscale's ULA IPv6 range.
_TAILSCALE_V6 = ipaddress.ip_network("fd7a:115c:a1e0::/48")


def _classify(ip: str) -> str:
    """Return a coarse class for grouping: 'tailscale' | 'lan' | 'link-local'."""
    try:
        addr = ipaddress.ip_address(ip)
    except ValueError:
        return "other"
    if addr.version == 4 and addr in _TAILSCALE_NET:
        return "tailscale"
    if addr.version == 6 and addr in _TAILSCALE_V6:
        return "tailscale"
    if addr.is_link_local:
        return "link-local"
    if addr.is_private:
        return "lan"
    return "public"


def _link_host(ip: str) -> str:
    """Bracket IPv6 for use in a URL host position."""
    return f"[{ip}]" if ":" in ip else ip


def local_addresses() -> list[dict[str, Any]]:
    """All non-loopback local IPs with classification + a URL-ready host.

    Enumerates via getaddrinfo on the hostname plus the classic "connect a UDP
    socket to a public IP and read the chosen source address" trick (which reveals
    the primary outbound interface even when the hostname doesn't resolve to it).
    Deduplicated, loopback dropped.
    """
    found: dict[str, dict[str, Any]] = {}

    def add(ip: str, family: int) -> None:
        if not ip or ip in found:
            return
        try:
            addr = ipaddress.ip_address(ip)
        except ValueError:
            return
        if addr.is_loopback or addr.is_unspecified:
            return
        found[ip] = {
            "ip": ip,
            "version": addr.version,
            "host": _link_host(ip),
            "class": _classify(ip),
        }

    # 1. Whatever the hostname resolves to.
    try:
        host = socket.gethostname()
        for fam in (socket.AF_INET, socket.AF_INET6):
            try:
                for info in socket.getaddrinfo(host, None, fam):
                    add(info[4][0].split("%")[0], fam)  # strip %scope on v6
            except socket.gaierror:
                pass
    except OSError:
        pass

    # 2. Primary outbound interface (the route to the internet), v4 + v6.
    for fam, probe in ((socket.AF_INET, "8.8.8.8"), (socket.AF_INET6, "2001:4860:4860::8888")):
        try:
            s = socket.socket(fam, socket.SOCK_DGRAM)
            try:
                s.connect((probe, 80))
                add(s.getsockname()[0].split("%")[0], fam)
            finally:
                s.close()
        except OSError:
            pass

    # Order: lan first (most useful), then tailscale, then the rest.
    rank = {"lan": 0, "tailscale": 1, "public": 2, "link-local": 3, "other": 4}
    return sorted(found.values(), key=lambda a: (rank.get(a["class"], 9), a["version"], a["ip"]))


def public_ip(timeout: float = 4.0) -> dict[str, str | None]:
    """Best-effort internet-facing IPs via keyless lookups. None if offline.

    Uses Cloudflare's trace endpoint (v4 + v6 hostnames) which returns a tiny
    text body containing ``ip=<addr>``. Failures are swallowed → None.
    """
    out: dict[str, str | None] = {"v4": None, "v6": None}
    for key, url in (("v4", "https://1.1.1.1/cdn-cgi/trace"),
                     ("v6", "https://[2606:4700:4700::1111]/cdn-cgi/trace")):
        try:
            req = urllib.request.Request(url, headers={"User-Agent": "raspy"})
            with urllib.request.urlopen(req, timeout=timeout) as resp:  # noqa: S310
                body = resp.read().decode(errors="replace")
            for line in body.splitlines():
                if line.startswith("ip="):
                    out[key] = line[3:].strip()
                    break
        except Exception:
            pass
    return out

"""FastAPI auth dependencies + token/IP extraction helpers.

Tokens are accepted from EITHER an HttpOnly cookie (web shell) OR an
``Authorization: Bearer`` header (future Flutter APK / scripts) — one code path,
two transports. The global gate middleware (see core/app.py) uses the same
helpers; ``require_auth`` is available for any route that wants an explicit
``Principal``.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from fastapi import Depends, HTTPException, Request

from ...config import AuthSettings
from .service import AuthService, AuthError

ACCESS_COOKIE = "raspy_at"
REFRESH_COOKIE = "raspy_rt"
CSRF_COOKIE = "raspy_csrf"
CSRF_HEADER = "x-csrf-token"


@dataclass
class Principal:
    username: str
    family_id: str


def get_auth(request: Request) -> AuthService:
    svc = getattr(request.app.state, "auth", None)
    if svc is None:
        raise HTTPException(503, "auth unavailable")
    return svc


def access_token_from(request: Request) -> str | None:
    """Bearer header takes precedence over the cookie (explicit native client)."""
    header = request.headers.get("authorization", "")
    if header.lower().startswith("bearer "):
        return header[7:].strip() or None
    return request.cookies.get(ACCESS_COOKIE)


def refresh_token_from(request: Request) -> str | None:
    """Refresh comes from the cookie, or an ``X-Refresh-Token`` header for the
    bearer (native) path where there are no cookies."""
    header = request.headers.get("x-refresh-token")
    if header:
        return header.strip() or None
    return request.cookies.get(REFRESH_COOKIE)


def client_ip(request: Request, settings: AuthSettings) -> str | None:
    """The client IP for rate limiting. Honor X-Forwarded-For only when the
    immediate peer is a trusted local proxy (cloudflared/Caddy), so it can't be
    spoofed by a remote client."""
    peer = request.client.host if request.client else None
    if peer in settings.trusted_proxies:
        xff = request.headers.get("x-forwarded-for")
        if xff:
            # Left-most is the original client per proxy convention.
            return xff.split(",")[0].strip()
    return peer


def principal_from_request(request: Request) -> Principal | None:
    """Verify the access token (if any) and return a Principal, else None.
    Never raises — callers decide how to react to None."""
    svc = getattr(request.app.state, "auth", None)
    if svc is None:
        return None
    token = access_token_from(request)
    if not token:
        return None
    try:
        claims = svc.verify_access(token)
    except AuthError:
        return None
    sub = claims.get("sub")
    fam = claims.get("fam")
    if not isinstance(sub, str) or not isinstance(fam, str):
        return None
    return Principal(username=sub, family_id=fam)


def require_auth(request: Request, svc: AuthService = Depends(get_auth)) -> Principal:
    principal = principal_from_request(request)
    if principal is None:
        raise HTTPException(401, "authentication required")
    return principal


def optional_auth(request: Request) -> Principal | None:
    return principal_from_request(request)


def check_csrf(request: Request, settings: AuthSettings) -> None:
    """Double-submit CSRF check for the *cookie* auth path on state-changing
    requests. The bearer path (no ambient credential) is exempt. Raises 403."""
    if not settings.csrf_enabled:
        return
    if request.method in ("GET", "HEAD", "OPTIONS"):
        return
    # Bearer auth carries no cookie => not CSRF-able; skip.
    if request.headers.get("authorization", "").lower().startswith("bearer "):
        return
    cookie = request.cookies.get(CSRF_COOKIE)
    header = request.headers.get(CSRF_HEADER)
    if not cookie or not header or cookie != header:
        raise HTTPException(403, "csrf token missing or invalid")

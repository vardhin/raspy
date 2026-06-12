"""Stateless, HMAC-signed tokens. No external JWT dep — stdlib only.

A token is ``base64url(json_claims) + "." + base64url(hmac_sha256(secret, body))``.
The access token is verified purely from its signature + ``exp`` (stateless, fast).
The refresh token additionally carries a family id + jti that the AuthService
checks against the DB so rotation + reuse-detection + revocation work.

Verification is constant-time on the signature (``hmac.compare_digest``). Claims
are never trusted before the signature checks out.
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import json
import time
from typing import Any


def _b64encode(raw: bytes) -> str:
    return base64.urlsafe_b64encode(raw).rstrip(b"=").decode("ascii")


def _b64decode(s: str) -> bytes:
    pad = "=" * (-len(s) % 4)
    return base64.urlsafe_b64decode(s + pad)


class TokenError(Exception):
    """Raised on any malformed / mistyped / expired / bad-signature token."""


def sign(secret: bytes, claims: dict[str, Any]) -> str:
    body = _b64encode(json.dumps(claims, separators=(",", ":"), sort_keys=True).encode())
    sig = hmac.new(secret, body.encode("ascii"), hashlib.sha256).digest()
    return f"{body}.{_b64encode(sig)}"


def verify(secret: bytes, token: str, *, expected_type: str | None = None) -> dict[str, Any]:
    """Return the claims if the signature is valid and the token isn't expired.

    Raises :class:`TokenError` otherwise. If ``expected_type`` is given, the
    token's ``typ`` claim must match (so an access token can't be replayed where
    a refresh token is expected, or vice versa).
    """
    try:
        body, sig_b64 = token.split(".", 1)
    except ValueError as exc:
        raise TokenError("malformed token") from exc

    expected = hmac.new(secret, body.encode("ascii"), hashlib.sha256).digest()
    try:
        got = _b64decode(sig_b64)
    except Exception as exc:  # noqa: BLE001
        raise TokenError("malformed signature") from exc
    if not hmac.compare_digest(expected, got):
        raise TokenError("bad signature")

    try:
        claims: dict[str, Any] = json.loads(_b64decode(body))
    except Exception as exc:  # noqa: BLE001
        raise TokenError("malformed claims") from exc

    if expected_type is not None and claims.get("typ") != expected_type:
        raise TokenError("wrong token type")

    exp = claims.get("exp")
    if not isinstance(exp, (int, float)) or exp <= time.time():
        raise TokenError("expired")

    return claims

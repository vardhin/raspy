"""Auth HTTP surface: /api/auth/*. All endpoints here are public (pre-auth) — the
gate middleware allow-lists them. Account *creation* lives in the CLI, not here,
so there is no HTTP setup attack surface.

Tokens are returned both as Set-Cookie (web shell) and in the JSON body (native
bearer clients). A readable CSRF cookie + matching header guards the cookie path.
"""

from __future__ import annotations

import secrets

from fastapi import APIRouter, Depends, HTTPException, Request, Response
from pydantic import BaseModel, Field

from ...config import Settings
from .deps import (
    ACCESS_COOKIE,
    CSRF_COOKIE,
    REFRESH_COOKIE,
    check_csrf,
    client_ip,
    get_auth,
    refresh_token_from,
)
from .service import AuthError, AuthService, LoginResult

router = APIRouter(prefix="/auth")


class LoginBody(BaseModel):
    username: str = Field(min_length=1, max_length=128)
    # auth_key = Argon2id(password) computed client-side; never the raw password.
    auth_key: str = Field(min_length=1, max_length=512)


class UnlockBody(BaseModel):
    pin: str = Field(min_length=1, max_length=256)


def _settings(request: Request) -> Settings:
    return request.app.state.settings


def _set_session_cookies(request: Request, response: Response, result: LoginResult) -> str:
    cfg = _settings(request).auth
    common = {"secure": cfg.cookie_secure, "samesite": cfg.cookie_samesite, "path": "/"}
    response.set_cookie(
        ACCESS_COOKIE, result.access_token, httponly=True,
        max_age=cfg.access_ttl_s, **common,
    )
    response.set_cookie(
        REFRESH_COOKIE, result.refresh_token, httponly=True,
        max_age=cfg.refresh_ttl_s, **common,
    )
    # CSRF token: readable by JS (not HttpOnly) so the client echoes it in a
    # header; the server compares the two (double-submit).
    csrf = secrets.token_urlsafe(24)
    response.set_cookie(
        CSRF_COOKIE, csrf, httponly=False, max_age=cfg.refresh_ttl_s, **common,
    )
    return csrf


def _clear_session_cookies(response: Response) -> None:
    for name in (ACCESS_COOKIE, REFRESH_COOKIE, CSRF_COOKIE):
        response.delete_cookie(name, path="/")


def _body(result: LoginResult, csrf: str) -> dict:
    # Native (bearer) clients read tokens from here; the web shell ignores them
    # and rides the cookies.
    return {
        "username": result.username,
        "access_token": result.access_token,
        "refresh_token": result.refresh_token,
        "csrf_token": csrf,
    }


def _ip(request: Request) -> str | None:
    return client_ip(request, _settings(request).auth)


def _auth_error(exc: AuthError) -> HTTPException:
    headers = {}
    if exc.retry_after is not None:
        headers["Retry-After"] = str(int(exc.retry_after) + 1)
        return HTTPException(429, str(exc), headers=headers)
    return HTTPException(401, str(exc))


@router.get("/kdf/{username}")
async def kdf_params(request: Request, username: str, svc: AuthService = Depends(get_auth)):
    """Public: the per-account KDF salts + Argon2 params the client needs to
    derive auth_key (for login) and master_key (for the vault) from the raw
    password. Salts are not secret. To avoid leaking which usernames exist, a
    missing account returns deterministic decoy salts derived from the username,
    so an attacker can't distinguish 'no such user' from 'user exists'."""
    salts = await svc.kdf_salts(username)
    if salts is None:
        salts = svc.decoy_salts(username)
    return salts


@router.post("/login")
async def login(
    request: Request, response: Response, body: LoginBody,
    svc: AuthService = Depends(get_auth),
):
    try:
        result = await svc.login(body.username, body.auth_key, ip=_ip(request))
    except AuthError as exc:
        raise _auth_error(exc)
    csrf = _set_session_cookies(request, response, result)
    return _body(result, csrf)


@router.post("/refresh")
async def refresh(request: Request, response: Response, svc: AuthService = Depends(get_auth)):
    token = refresh_token_from(request)
    if not token:
        raise HTTPException(401, "no refresh token")
    try:
        result = await svc.refresh(token, ip=_ip(request))
    except AuthError as exc:
        # Refresh failed (expired/revoked/reused) — clear cookies so the client
        # falls back to the password screen.
        _clear_session_cookies(response)
        raise _auth_error(exc)
    csrf = _set_session_cookies(request, response, result)
    return _body(result, csrf)


@router.post("/unlock")
async def unlock(
    request: Request, response: Response, body: UnlockBody,
    svc: AuthService = Depends(get_auth),
):
    token = refresh_token_from(request)
    if not token:
        raise HTTPException(401, "no refresh token")
    # CSRF applies: unlock is a state-changing, cookie-authenticated action.
    check_csrf(request, _settings(request).auth)
    try:
        result = await svc.unlock(token, body.pin, ip=_ip(request))
    except AuthError as exc:
        raise _auth_error(exc)
    csrf = _set_session_cookies(request, response, result)
    return _body(result, csrf)


@router.post("/logout", status_code=204)
async def logout(request: Request, response: Response, svc: AuthService = Depends(get_auth)):
    check_csrf(request, _settings(request).auth)
    await svc.logout(refresh_token_from(request))
    _clear_session_cookies(response)


@router.get("/session")
async def session(request: Request, svc: AuthService = Depends(get_auth)):
    """What screen the client should show. Public so the shell can ask before
    it has any valid token."""
    from .deps import principal_from_request

    principal = principal_from_request(request)
    if principal is not None:
        return {"authenticated": True, "needs": "none", "username": principal.username}
    needs = await svc.session_state(refresh_token_from(request))
    return {"authenticated": False, "needs": needs}

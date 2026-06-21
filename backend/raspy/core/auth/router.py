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
    Principal,
    check_csrf,
    client_ip,
    get_auth,
    refresh_token_from,
    require_admin,
    require_auth,
)
from .service import AuthError, AuthService, LoginResult

router = APIRouter(prefix="/auth")


class LoginBody(BaseModel):
    username: str = Field(min_length=1, max_length=128)
    # auth_key = Argon2id(password) computed client-side; never the raw password.
    auth_key: str = Field(min_length=1, max_length=512)
    # Required only for frozen child accounts using temporary credentials.
    pin: str | None = Field(default=None, min_length=1, max_length=256)


class UnlockBody(BaseModel):
    pin: str = Field(min_length=1, max_length=256)


class CompleteSetupBody(BaseModel):
    # New auth_key (= Argon2id(new password) client-side) + new PIN, set by a
    # frozen child on first sign-in. The admin never sees these.
    auth_key: str = Field(min_length=1, max_length=512)
    pin: str = Field(min_length=1, max_length=256)


class CreateChildBody(BaseModel):
    username: str = Field(min_length=1, max_length=128)
    # The browser generates the temp password and salts, derives auth_key from
    # that temp password, and sends only auth_key here. The admin relays the temp
    # password/PIN to the child; the server never needs to see the raw password.
    auth_key: str = Field(min_length=1, max_length=512)
    temp_pin: str = Field(min_length=1, max_length=256)
    auth_salt: str = Field(min_length=1, max_length=128)
    master_salt: str = Field(min_length=1, max_length=128)
    allowed_apps: list[str] = Field(default_factory=list)


class UpdateChildBody(BaseModel):
    allowed_apps: list[str] = Field(default_factory=list)


class SetRecoveryBody(BaseModel):
    """Opaque recovery wraps the browser computed (plan/35). All values are b64
    ciphertext / a public salt; the server stores them verbatim."""
    recovery_salt: str = Field(min_length=1, max_length=128)
    wrap_pw: str = Field(min_length=1, max_length=512)
    wrap_pw_nonce: str = Field(min_length=1, max_length=128)
    wrap_mn: str = Field(min_length=1, max_length=512)
    wrap_mn_nonce: str = Field(min_length=1, max_length=128)


class RecoverBody(BaseModel):
    """Break-glass password reset proven by the mnemonic (client-side). The server
    only takes the new auth_key (+ optional PIN); the wraps/DEK are untouched."""
    username: str = Field(min_length=1, max_length=128)
    new_auth_key: str = Field(min_length=1, max_length=512)
    new_pin: str | None = Field(default=None, min_length=1, max_length=256)


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
        "role": result.role,
        "must_reset": result.must_reset,
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


@router.get("/recovery/{username}")
async def recovery_material(
    request: Request, username: str, svc: AuthService = Depends(get_auth)
):
    """Public: the opaque recovery wraps + salt the client needs to recover the
    DEK from a mnemonic (or to detect whether migration has happened). Like
    /kdf, the values are non-secret. A missing account returns the same shape with
    nulls + dek_migrated:false, so it doesn't reveal whether the user exists."""
    material = await svc.recovery_material(username)
    if material is None:
        material = {
            "recovery_salt": None,
            "wrap_pw": None, "wrap_pw_nonce": None,
            "wrap_mn": None, "wrap_mn_nonce": None,
            "dek_migrated": False,
        }
    return material


@router.put("/recovery", status_code=204)
async def set_recovery(
    request: Request, body: SetRecoveryBody,
    svc: AuthService = Depends(get_auth),
    principal: Principal = Depends(require_auth),
):
    """Authed: the client stores its recovery wraps for its OWN account (migration
    or a wrap rotation). Scoped to the principal — a user can only write their own
    envelope."""
    check_csrf(request, _settings(request).auth)
    try:
        await svc.set_recovery(
            principal.username,
            recovery_salt=body.recovery_salt,
            wrap_pw=body.wrap_pw, wrap_pw_nonce=body.wrap_pw_nonce,
            wrap_mn=body.wrap_mn, wrap_mn_nonce=body.wrap_mn_nonce,
        )
    except AuthError as exc:
        raise HTTPException(400, str(exc))


@router.post("/recover", status_code=204)
async def recover(
    request: Request, response: Response, body: RecoverBody,
    svc: AuthService = Depends(get_auth),
):
    """Public, rate-limited: break-glass password reset proven by the mnemonic.
    The client has already unwrapped the DEK from wrap_mn locally; here we only
    reset the login hash, then the client re-PUTs wrap_pw under the new password.
    Sessions are revoked so the user signs in fresh."""
    try:
        await svc.recover_password(
            body.username, body.new_auth_key, body.new_pin, ip=_ip(request)
        )
    except AuthError as exc:
        raise _auth_error(exc)
    _clear_session_cookies(response)


@router.post("/login")
async def login(
    request: Request, response: Response, body: LoginBody,
    svc: AuthService = Depends(get_auth),
):
    try:
        result = await svc.login(body.username, body.auth_key, pin=body.pin, ip=_ip(request))
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
        # A frozen child holds a valid token but may do nothing except finish
        # setup — surface that as needs:'reset' so the client shows the reset
        # screen instead of the app.
        needs = "reset" if principal.must_reset else "none"
        return {
            "authenticated": True,
            "needs": needs,
            "username": principal.username,
            "role": principal.role,
        }
    needs = await svc.session_state(refresh_token_from(request))
    return {"authenticated": False, "needs": needs}


@router.post("/complete-setup", status_code=204)
async def complete_setup(
    request: Request, response: Response, body: CompleteSetupBody,
    svc: AuthService = Depends(get_auth),
):
    """A frozen child sets its real password + PIN on first sign-in. Requires the
    (valid) temp session; afterwards the session is revoked so the child logs in
    fresh with the new creds."""
    token = refresh_token_from(request)
    if not token:
        raise HTTPException(401, "no refresh token")
    check_csrf(request, _settings(request).auth)
    try:
        await svc.complete_setup(token, body.auth_key, body.pin, ip=_ip(request))
    except AuthError as exc:
        raise _auth_error(exc)
    # Revoked server-side — clear cookies so the client returns to the password
    # screen and signs in with the new credentials.
    _clear_session_cookies(response)


# --- admin: child account management (admin only) ----------------------------


@router.get("/admin/apps")
async def admin_list_apps(request: Request, _=Depends(require_admin)):
    """Grantable apps (id/title/icon) for the per-account permission checklist —
    excludes admin-only apps that can't be isolated (accounts/files/stats) and
    backend-only utilities with no sidebar app (e.g. identity), which aren't
    grantable: they're hidden from every manifest and always reachable anyway."""
    from ..manifest import _ADMIN_ONLY, _HIDDEN

    registry = request.app.state.registry
    return [
        {"id": e["id"], "title": e["title"], "icon": e["icon"]}
        for e in registry.manifest()
        if e["id"] not in _ADMIN_ONLY and e["id"] not in _HIDDEN
    ]


@router.get("/admin/accounts")
async def admin_list_accounts(svc: AuthService = Depends(get_auth), _=Depends(require_admin)):
    return await svc.list_accounts()


@router.post("/admin/accounts", status_code=201)
async def admin_create_account(
    request: Request, body: CreateChildBody,
    svc: AuthService = Depends(get_auth), _=Depends(require_admin),
):
    """Create a frozen child with browser-generated temp credentials."""
    check_csrf(request, _settings(request).auth)
    try:
        await svc.create_child(
            body.username, body.auth_key, body.temp_pin,
            auth_salt=body.auth_salt, master_salt=body.master_salt,
            allowed_apps=body.allowed_apps,
        )
    except AuthError as exc:
        raise HTTPException(409, str(exc))
    return {"username": body.username, "role": "child", "allowed_apps": sorted(set(body.allowed_apps))}


@router.patch("/admin/accounts/{username}", status_code=204)
async def admin_update_account(
    request: Request, username: str, body: UpdateChildBody,
    svc: AuthService = Depends(get_auth), _=Depends(require_admin),
):
    check_csrf(request, _settings(request).auth)
    try:
        await svc.set_allowed_apps(username, body.allowed_apps)
    except AuthError as exc:
        raise HTTPException(400, str(exc))


@router.delete("/admin/accounts/{username}", status_code=204)
async def admin_delete_account(
    request: Request, username: str,
    svc: AuthService = Depends(get_auth), _=Depends(require_admin),
):
    check_csrf(request, _settings(request).auth)
    try:
        await svc.delete_account(username)
    except AuthError as exc:
        raise HTTPException(400, str(exc))

"""Layer-0 auth tests: gate, login, refresh rotation + reuse, PIN unlock, lockout.

Uses deliberately weak server-side Argon2 params (fast). The browser-side KDF is
not what this file is testing, so fixtures use fixed auth_key strings instead of
spending the real 64 MiB client KDF on every login.
"""

from __future__ import annotations

import asyncio
from pathlib import Path

import httpx
import pytest

from raspy.config import AuthSettings, Settings
from raspy.core.app import create_app
from raspy.core.auth.service import AuthService, load_or_create_secret
from raspy.core.db import Database

USERNAME = "operator"
PASSWORD = "correct horse battery staple"
PIN = "8675309"
AUTH_KEY = "operator-auth-key"
TEMP_KEY = "kid-temp-auth-key"
NEW_KEY = "kid-new-auth-key"

# Fast Argon2 for the storage hash so the suite isn't slow.
_FAST = dict(argon_time_cost=1, argon_memory_kib=8, argon_parallelism=1)


@pytest.fixture
async def setup(tmp_path: Path):
    """Create an account on disk, then build the app over the same data dir."""
    settings = Settings(
        data_dir=tmp_path,
        auth=AuthSettings(cookie_secure=False, **_FAST),
        disabled_attachments=["calendar", "mail", "stats", "vibe"],
    )

    async def _seed():
        secret = load_or_create_secret(settings.auth_secret_path, create=True)
        db = Database(settings.db_path)
        db.connect()
        svc = AuthService(db=db, settings=settings.auth, secret=secret)
        await svc.init()
        auth_salt = "PrXc0GEAlOveYCpyIegc0Q"  # 16 bytes b64url
        master_salt = "V6fIW2LrJGyf0rsAew-3Xw"
        await svc.create_account(USERNAME, AUTH_KEY, PIN, auth_salt=auth_salt,
                                 master_salt=master_salt)
        db.close()
        return auth_salt

    auth_salt = await _seed()
    app = create_app(settings)
    async with app.router.lifespan_context(app):
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(
            transport=transport, base_url="http://testserver"
        ) as c:
            yield c, auth_salt


async def _login(client: httpx.AsyncClient, auth_salt: str, password: str = PASSWORD):
    auth_key = AUTH_KEY if password == PASSWORD else f"wrong:{password}"
    return await client.post(
        "/api/auth/login", json={"username": USERNAME, "auth_key": auth_key}
    )


# --- gate --------------------------------------------------------------------


async def test_healthz_public(setup):
    client, _ = setup
    assert (await client.get("/api/healthz")).status_code == 200


async def test_protected_route_401_without_token(setup):
    client, _ = setup
    # Fresh client w/o cookies — the TestClient persists cookies, so clear them.
    client.cookies.clear()
    assert (await client.get("/api/notifications")).status_code == 401


async def test_login_then_access(setup):
    client, salt = setup
    r = await _login(client, salt)
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["username"] == USERNAME
    assert body["access_token"] and body["refresh_token"]
    # Cookie now set on the client — protected route works.
    assert (await client.get("/api/notifications")).status_code == 200


async def test_bearer_path_no_cookies(setup):
    """The Flutter/native path: tokens via Authorization header, no cookies."""
    client, salt = setup
    body = (await _login(client, salt)).json()
    client.cookies.clear()
    r = await client.get(
        "/api/notifications",
        headers={"Authorization": f"Bearer {body['access_token']}"},
    )
    assert r.status_code == 200


async def test_wrong_password_rejected(setup):
    client, salt = setup
    r = await _login(client, salt, password="wrong password")
    assert r.status_code == 401


async def test_refresh_rotates(setup):
    client, salt = setup
    rt1 = (await _login(client, salt)).json()["refresh_token"]
    r = await client.post("/api/auth/refresh")
    assert r.status_code == 200
    rt2 = r.json()["refresh_token"]
    assert rt2 != rt1  # rotated


async def test_refresh_reuse_revokes_family(setup):
    client, salt = setup
    rt1 = (await _login(client, salt)).json()["refresh_token"]
    # Rotate once (cookie now holds rt2).
    assert (await client.post("/api/auth/refresh")).status_code == 200
    # Replay the old rt1 explicitly via header → reuse → family revoked.
    client.cookies.clear()
    r = await client.post("/api/auth/refresh", headers={"X-Refresh-Token": rt1})
    assert r.status_code == 401
    # And the rotated rt2 is now dead too (whole family revoked) — re-login needed.


async def test_unlock_with_pin(setup):
    client, salt = setup
    login = (await _login(client, salt)).json()
    csrf = login["csrf_token"]
    # Simulate a stale access token: drop just the access cookie, keep refresh.
    client.cookies.delete("raspy_at")
    r = await client.post(
        "/api/auth/unlock", json={"pin": PIN}, headers={"X-CSRF-Token": csrf}
    )
    assert r.status_code == 200, r.text
    assert (await client.get("/api/notifications")).status_code == 200


async def test_unlock_wrong_pin_then_downgrade(setup):
    client, salt = setup
    csrf = (await _login(client, salt)).json()["csrf_token"]
    client.cookies.delete("raspy_at")
    # pin_max_attempts defaults to 3 → after 3 wrong PINs the family downgrades.
    for _ in range(3):
        r = await client.post(
            "/api/auth/unlock", json={"pin": "0000"}, headers={"X-CSRF-Token": csrf}
        )
        assert r.status_code == 401
    # Now even the correct PIN is refused → must use password.
    r = await client.post(
        "/api/auth/unlock", json={"pin": PIN}, headers={"X-CSRF-Token": csrf}
    )
    assert r.status_code == 401
    assert "password" in r.json()["detail"].lower()


async def test_session_states(setup):
    client, salt = setup
    client.cookies.clear()
    assert (await client.get("/api/auth/session")).json()["needs"] == "password"
    login = (await _login(client, salt)).json()
    assert (await client.get("/api/auth/session")).json()["needs"] == "none"
    client.cookies.delete("raspy_at")
    assert (await client.get("/api/auth/session")).json()["needs"] == "pin"


async def test_lockout_after_failures(setup):
    client, salt = setup
    client.cookies.clear()
    # max_attempts defaults to 5 → the 5th failure locks; subsequent → 429.
    last = None
    for _ in range(6):
        last = await _login(client, salt, password="nope")
    assert last.status_code == 429
    assert "Retry-After" in last.headers


async def test_logout_revokes(setup):
    client, salt = setup
    csrf = (await _login(client, salt)).json()["csrf_token"]
    assert (
        await client.post("/api/auth/logout", headers={"X-CSRF-Token": csrf})
    ).status_code == 204
    # Access cookie cleared; refresh revoked → can't refresh.
    assert (await client.post("/api/auth/refresh")).status_code == 401


async def test_child_setup_requires_temp_pin_and_blocks_unallowed_apps(setup):
    client, salt = setup
    admin_csrf = (await _login(client, salt)).json()["csrf_token"]
    child_auth_salt = "bZVY7pC1n5EnlbS0K9uS3Q"
    child_master_salt = "GUedB4CKNLIhKylxjXI5qw"
    r = await client.post(
        "/api/auth/admin/accounts",
        json={
            "username": "kid",
            "auth_key": TEMP_KEY,
            "temp_pin": "246810",
            "auth_salt": child_auth_salt,
            "master_salt": child_master_salt,
            "allowed_apps": ["notes"],
        },
        headers={"X-CSRF-Token": admin_csrf},
    )
    assert r.status_code == 201, r.text

    child_salts = (await client.get("/api/auth/kdf/kid")).json()
    assert child_salts["auth_salt"] == child_auth_salt
    client.cookies.clear()
    assert (await client.post(
        "/api/auth/login", json={"username": "kid", "auth_key": TEMP_KEY}
    )).status_code == 401
    assert (await client.post(
        "/api/auth/login",
        json={"username": "kid", "auth_key": TEMP_KEY, "pin": "000000"},
    )).status_code == 401

    login = await client.post(
        "/api/auth/login",
        json={"username": "kid", "auth_key": TEMP_KEY, "pin": "246810"},
    )
    assert login.status_code == 200, login.text
    assert login.json()["must_reset"] is True
    assert (await client.get("/api/auth/session")).json()["needs"] == "reset"

    r = await client.post(
        "/api/auth/complete-setup",
        json={"auth_key": NEW_KEY, "pin": "135790"},
        headers={"X-CSRF-Token": login.json()["csrf_token"]},
    )
    assert r.status_code == 204, r.text

    relogin = await client.post(
        "/api/auth/login",
        json={"username": "kid", "auth_key": NEW_KEY, "pin": "135790"},
    )
    assert relogin.status_code == 200, relogin.text
    assert relogin.json()["must_reset"] is False
    app_ids = {a["id"] for a in (await client.get("/api/manifest")).json()["attachments"]}
    assert "notes" in app_ids
    assert "vault" not in app_ids
    assert (await client.get("/api/att/notes/notes")).status_code == 200
    assert (await client.get("/api/att/vault/manifest")).status_code == 403

"""Layer-0 auth tests: gate, login, refresh rotation + reuse, PIN unlock, lockout.

Uses deliberately weak Argon2 params (fast) and reproduces the client-side
auth_key derivation via raspy.core.auth.kdf so login matches what the CLI stored.
"""

from __future__ import annotations

import asyncio
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from raspy.config import AuthSettings, Settings
from raspy.core.app import create_app
from raspy.core.auth import kdf
from raspy.core.auth.service import AuthService, load_or_create_secret
from raspy.core.db import Database

USERNAME = "operator"
PASSWORD = "correct horse battery staple"
PIN = "8675309"

# Fast Argon2 for the storage hash so the suite isn't slow. The client-side KDF
# (kdf.py) has its own fixed params; we don't change those here.
_FAST = dict(argon_time_cost=1, argon_memory_kib=8, argon_parallelism=1)


@pytest.fixture
def setup(tmp_path: Path):
    """Create an account on disk, then build the app over the same data dir."""
    settings = Settings(data_dir=tmp_path, auth=AuthSettings(cookie_secure=False, **_FAST))

    async def _seed():
        secret = load_or_create_secret(settings.auth_secret_path, create=True)
        db = Database(settings.db_path)
        db.connect()
        svc = AuthService(db=db, settings=settings.auth, secret=secret)
        await svc.init()
        auth_salt = "PrXc0GEAlOveYCpyIegc0Q"  # 16 bytes b64url
        master_salt = "V6fIW2LrJGyf0rsAew-3Xw"
        auth_key = kdf.derive_auth_key(PASSWORD, auth_salt)
        await svc.create_account(USERNAME, auth_key, PIN, auth_salt=auth_salt,
                                 master_salt=master_salt)
        db.close()
        return auth_salt

    auth_salt = asyncio.run(_seed())
    app = create_app(settings)
    with TestClient(app) as c:
        yield c, auth_salt


def _login(client: TestClient, auth_salt: str, password: str = PASSWORD):
    auth_key = kdf.derive_auth_key(password, auth_salt)
    return client.post("/api/auth/login", json={"username": USERNAME, "auth_key": auth_key})


# --- gate --------------------------------------------------------------------


def test_healthz_public(setup):
    client, _ = setup
    assert client.get("/api/healthz").status_code == 200


def test_protected_route_401_without_token(setup):
    client, _ = setup
    # Fresh client w/o cookies — the TestClient persists cookies, so clear them.
    client.cookies.clear()
    assert client.get("/api/notifications").status_code == 401


def test_login_then_access(setup):
    client, salt = setup
    r = _login(client, salt)
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["username"] == USERNAME
    assert body["access_token"] and body["refresh_token"]
    # Cookie now set on the client — protected route works.
    assert client.get("/api/notifications").status_code == 200


def test_bearer_path_no_cookies(setup):
    """The Flutter/native path: tokens via Authorization header, no cookies."""
    client, salt = setup
    body = _login(client, salt).json()
    client.cookies.clear()
    r = client.get("/api/notifications",
                   headers={"Authorization": f"Bearer {body['access_token']}"})
    assert r.status_code == 200


def test_wrong_password_rejected(setup):
    client, salt = setup
    r = _login(client, salt, password="wrong password")
    assert r.status_code == 401


def test_refresh_rotates(setup):
    client, salt = setup
    rt1 = _login(client, salt).json()["refresh_token"]
    r = client.post("/api/auth/refresh")
    assert r.status_code == 200
    rt2 = r.json()["refresh_token"]
    assert rt2 != rt1  # rotated


def test_refresh_reuse_revokes_family(setup):
    client, salt = setup
    rt1 = _login(client, salt).json()["refresh_token"]
    # Rotate once (cookie now holds rt2).
    assert client.post("/api/auth/refresh").status_code == 200
    # Replay the old rt1 explicitly via header → reuse → family revoked.
    client.cookies.clear()
    r = client.post("/api/auth/refresh", headers={"X-Refresh-Token": rt1})
    assert r.status_code == 401
    # And the rotated rt2 is now dead too (whole family revoked) — re-login needed.


def test_unlock_with_pin(setup):
    client, salt = setup
    login = _login(client, salt).json()
    csrf = login["csrf_token"]
    # Simulate a stale access token: drop just the access cookie, keep refresh.
    client.cookies.delete("raspy_at")
    r = client.post("/api/auth/unlock", json={"pin": PIN},
                    headers={"X-CSRF-Token": csrf})
    assert r.status_code == 200, r.text
    assert client.get("/api/notifications").status_code == 200


def test_unlock_wrong_pin_then_downgrade(setup):
    client, salt = setup
    csrf = _login(client, salt).json()["csrf_token"]
    client.cookies.delete("raspy_at")
    # pin_max_attempts defaults to 3 → after 3 wrong PINs the family downgrades.
    for _ in range(3):
        r = client.post("/api/auth/unlock", json={"pin": "0000"},
                        headers={"X-CSRF-Token": csrf})
        assert r.status_code == 401
    # Now even the correct PIN is refused → must use password.
    r = client.post("/api/auth/unlock", json={"pin": PIN},
                    headers={"X-CSRF-Token": csrf})
    assert r.status_code == 401
    assert "password" in r.json()["detail"].lower()


def test_session_states(setup):
    client, salt = setup
    client.cookies.clear()
    assert client.get("/api/auth/session").json()["needs"] == "password"
    login = _login(client, salt).json()
    assert client.get("/api/auth/session").json()["needs"] == "none"
    client.cookies.delete("raspy_at")
    assert client.get("/api/auth/session").json()["needs"] == "pin"


def test_lockout_after_failures(setup):
    client, salt = setup
    client.cookies.clear()
    # max_attempts defaults to 5 → the 5th failure locks; subsequent → 429.
    last = None
    for _ in range(6):
        last = _login(client, salt, password="nope")
    assert last.status_code == 429
    assert "Retry-After" in last.headers


def test_logout_revokes(setup):
    client, salt = setup
    csrf = _login(client, salt).json()["csrf_token"]
    assert client.post("/api/auth/logout", headers={"X-CSRF-Token": csrf}).status_code == 204
    # Access cookie cleared; refresh revoked → can't refresh.
    assert client.post("/api/auth/refresh").status_code == 401


def test_child_setup_requires_temp_pin_and_blocks_unallowed_apps(setup):
    client, salt = setup
    admin_csrf = _login(client, salt).json()["csrf_token"]
    child_auth_salt = "bZVY7pC1n5EnlbS0K9uS3Q"
    child_master_salt = "GUedB4CKNLIhKylxjXI5qw"
    temp_key = kdf.derive_auth_key("temporary password", child_auth_salt)
    r = client.post(
        "/api/auth/admin/accounts",
        json={
            "username": "kid",
            "auth_key": temp_key,
            "temp_pin": "246810",
            "auth_salt": child_auth_salt,
            "master_salt": child_master_salt,
            "allowed_apps": ["notes"],
        },
        headers={"X-CSRF-Token": admin_csrf},
    )
    assert r.status_code == 201, r.text

    child_salts = client.get("/api/auth/kdf/kid").json()
    assert child_salts["auth_salt"] == child_auth_salt
    client.cookies.clear()
    assert client.post(
        "/api/auth/login", json={"username": "kid", "auth_key": temp_key}
    ).status_code == 401
    assert client.post(
        "/api/auth/login",
        json={"username": "kid", "auth_key": temp_key, "pin": "000000"},
    ).status_code == 401

    login = client.post(
        "/api/auth/login",
        json={"username": "kid", "auth_key": temp_key, "pin": "246810"},
    )
    assert login.status_code == 200, login.text
    assert login.json()["must_reset"] is True
    assert client.get("/api/auth/session").json()["needs"] == "reset"

    new_key = kdf.derive_auth_key("new child password", child_salts["auth_salt"])
    r = client.post(
        "/api/auth/complete-setup",
        json={"auth_key": new_key, "pin": "135790"},
        headers={"X-CSRF-Token": login.json()["csrf_token"]},
    )
    assert r.status_code == 204, r.text

    relogin = client.post(
        "/api/auth/login",
        json={"username": "kid", "auth_key": new_key, "pin": "135790"},
    )
    assert relogin.status_code == 200, relogin.text
    assert relogin.json()["must_reset"] is False
    app_ids = {a["id"] for a in client.get("/api/manifest").json()["attachments"]}
    assert "notes" in app_ids
    assert "vault" not in app_ids
    assert client.get("/api/att/notes/notes").status_code == 200
    assert client.get("/api/att/vault/manifest").status_code == 403

from __future__ import annotations

import asyncio
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from raspy.config import AuthSettings, Settings
from raspy.core.app import create_app
from raspy.core.auth.service import AuthService, load_or_create_secret
from raspy.core.db import Database

# Shared test credentials. Argon2 is set deliberately weak so the suite is fast.
_TEST_USER = "tester"
_TEST_PASSWORD = "test-password"
_TEST_PIN = "1234"
_TEST_AUTH_KEY = "test-auth-key"
_TEST_AUTH_SALT = "PrXc0GEAlOveYCpyIegc0Q"  # 16 bytes b64url
_FAST_ARGON = dict(argon_time_cost=1, argon_memory_kib=8, argon_parallelism=1)


def _seed_account(settings: Settings) -> None:
    async def _run() -> None:
        secret = load_or_create_secret(settings.auth_secret_path, create=True)
        db = Database(settings.db_path)
        db.connect()
        svc = AuthService(db=db, settings=settings.auth, secret=secret)
        await svc.init()
        await svc.create_account(
            _TEST_USER, _TEST_AUTH_KEY, _TEST_PIN,
            auth_salt=_TEST_AUTH_SALT, master_salt="V6fIW2LrJGyf0rsAew-3Xw",
        )
        db.close()

    asyncio.run(_run())
    # Channel static key, so the Layer-1 service is available in tests too.
    from raspy.core.auth.cli import _ensure_channel_key

    _ensure_channel_key(settings.channel_key_path)


def auth_settings(tmp_path: Path) -> Settings:
    """Settings with a seeded account + fast Argon2, for tests that build their
    own app/client instead of using the `client` fixture."""
    settings = Settings(
        data_dir=tmp_path,
        auth=AuthSettings(cookie_secure=False, **_FAST_ARGON),
    )
    _seed_account(settings)
    return settings


def login(c: TestClient) -> TestClient:
    """Log a freshly-built TestClient in (cookies + CSRF header). Returns it."""
    resp = c.post("/api/auth/login", json={"username": _TEST_USER, "auth_key": _TEST_AUTH_KEY})
    assert resp.status_code == 200, resp.text
    c.headers.update({"X-CSRF-Token": resp.json()["csrf_token"]})
    return c


@pytest.fixture
def client(tmp_path: Path):
    """An authenticated TestClient. An account is seeded on disk and the client
    is logged in, so existing tests (which predate auth) keep working against
    protected routes. Tests that exercise auth itself can clear cookies."""
    settings = Settings(
        data_dir=tmp_path,
        auth=AuthSettings(cookie_secure=False, **_FAST_ARGON),
    )
    _seed_account(settings)
    app = create_app(settings)
    with TestClient(app) as c:
        resp = c.post("/api/auth/login",
                      json={"username": _TEST_USER, "auth_key": _TEST_AUTH_KEY})
        assert resp.status_code == 200, resp.text
        # Carry the CSRF token on all mutating requests by default.
        c.headers.update({"X-CSRF-Token": resp.json()["csrf_token"]})
        yield c

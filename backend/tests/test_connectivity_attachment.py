"""Connectivity attachment: discovery, admin-only gating, status shape, and the
encrypted Cloudflare-token round-trip. No real tunnels are started."""

from __future__ import annotations

import pytest

from raspy.attachments.connectivity import Connectivity


def test_connectivity_discovered_and_admin_only(client):
    h = client.get("/api/healthz").json()
    loaded = {a["id"] for a in h["attachments"]["loaded"]}
    assert "connectivity" in loaded

    from raspy.core.manifest import _ADMIN_ONLY
    assert "connectivity" in _ADMIN_ONLY

    manifest = client.get("/api/manifest").json()
    ids = {a["id"] for a in manifest["attachments"]}
    # The seeded test account is the admin, so it DOES see the app.
    assert "connectivity" in ids
    node = next(a for a in manifest["attachments"] if a["id"] == "connectivity")
    assert node["ui"]["type"] == "connectivity"


def test_status_endpoint_shape_without_binaries(client, monkeypatch):
    """With neither cloudflared nor tailscale installed, status still returns a
    well-formed dashboard reporting installed=False and never crashes."""
    import raspy.attachments.connectivity as mod
    monkeypatch.setattr(mod.shutil, "which", lambda name: None)

    s = client.get("/api/att/connectivity/status").json()
    # Top-level dashboard groups always present.
    assert set(s) >= {"port", "local", "public", "tailscale", "cloudflare"}
    assert isinstance(s["local"], list)
    assert s["public"]["v4"] is None or isinstance(s["public"]["v4"], str)
    assert s["cloudflare"]["installed"] is False
    assert s["cloudflare"]["running"] is False
    assert s["cloudflare"]["configured"] is False
    assert s["tailscale"]["installed"] is False
    assert s["tailscale"]["connected"] is False
    # The login identity / ssh fields exist even when not installed.
    assert s["tailscale"]["login_name"] is None
    assert s["tailscale"]["ssh"] is False
    assert "install_url" in s["cloudflare"]


def test_local_addresses_have_links(client, monkeypatch):
    """Every discovered local address carries a ready-to-use http link on the
    spine's port."""
    import raspy.attachments.connectivity as mod
    monkeypatch.setattr(mod.shutil, "which", lambda name: None)
    # Force a deterministic local address so the test doesn't depend on the host.
    monkeypatch.setattr(
        mod.netinfo, "local_addresses",
        lambda: [{"ip": "192.168.1.5", "version": 4, "host": "192.168.1.5", "class": "lan"}],
    )
    monkeypatch.setattr(mod.netinfo, "public_ip", lambda timeout=4.0: {"v4": None, "v6": None})
    s = client.get("/api/att/connectivity/status").json()
    assert s["local"][0]["url"].startswith("http://192.168.1.5:")


def test_tailscale_actions_refuse_when_not_installed(client, monkeypatch):
    import raspy.attachments.connectivity as mod
    monkeypatch.setattr(mod.shutil, "which", lambda name: None)
    for path in ("tailscale/up", "tailscale/down", "tailscale/logout"):
        r = client.post(f"/api/att/connectivity/{path}")
        assert r.status_code == 503, path
    r = client.post("/api/att/connectivity/tailscale/ssh", json={"enable": True})
    assert r.status_code == 503


def test_cloudflare_up_requires_binary(client, monkeypatch):
    import raspy.attachments.connectivity as mod
    monkeypatch.setattr(mod.shutil, "which", lambda name: None)
    r = client.post("/api/att/connectivity/cloudflare/up")
    assert r.status_code == 503  # not installed


def test_netinfo_classifies_tailscale_and_lan():
    from raspy.attachments.connectivity import netinfo
    assert netinfo._classify("100.120.41.22") == "tailscale"  # CGNAT range
    assert netinfo._classify("192.168.1.10") == "lan"
    assert netinfo._classify("10.0.0.5") == "lan"
    assert netinfo._classify("fe80::1") == "link-local"
    # IPv6 host bracketing for URLs.
    assert netinfo._link_host("fd7a:115c::1") == "[fd7a:115c::1]"
    assert netinfo._link_host("192.168.1.1") == "192.168.1.1"


@pytest.mark.asyncio
async def test_token_is_encrypted_at_rest(tmp_path):
    """The stored Cloudflare token must not appear in plaintext on disk and must
    round-trip through the per-attachment Fernet key."""
    from raspy.core.contract import AttachmentContext
    from raspy.core.events import EventBus
    from raspy.core.db import Database, ScopedDB

    db = Database(tmp_path / "t.sqlite3")
    db.connect()
    ctx = AttachmentContext(
        db=ScopedDB(db, "connectivity"),
        data_dir=tmp_path,
        events=EventBus(),
        config={},
        attachment_id="connectivity",
    )
    att = Connectivity()
    att.ctx = ctx
    await att._ensure_tables()

    secret = "cf-tunnel-token-SECRET-123456"
    await att._save_cf_token(secret)

    # Encrypted file exists and does NOT contain the plaintext.
    enc = att._token_path().read_bytes()
    assert secret.encode() not in enc
    # Decrypts back to the original.
    assert att._cf_token() == secret
    db.close()

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
    for path in ("tailscale/up", "tailscale/down", "tailscale/logout",
                 "tailscale/update", "tailscale/netcheck"):
        r = client.post(f"/api/att/connectivity/{path}")
        assert r.status_code == 503, path
    r = client.post("/api/att/connectivity/tailscale/ssh", json={"enable": True})
    assert r.status_code == 503
    r = client.post("/api/att/connectivity/tailscale/exit-node", json={"node": "x"})
    assert r.status_code == 503
    r = client.post("/api/att/connectivity/tailscale/ping", json={"target": "x"})
    assert r.status_code == 503


def test_logout_signals_needs_root_then_succeeds_with_sudo(client, monkeypatch):
    """A privileged tailscale action that fails for lack of root returns 428
    `needs-root` (so the UI can prompt), and succeeds when a sudo password is
    supplied — without ever putting the password in argv."""
    import raspy.attachments.connectivity as mod

    monkeypatch.setattr(mod.shutil, "which", lambda name: f"/usr/bin/{name}")

    calls: list[tuple[list[str], bytes | None]] = []

    async def fake_run(cmd, timeout=30.0, stdin=None):
        calls.append((cmd, stdin))
        # Plain (no sudo) attempt → access denied; sudo attempt → success.
        if cmd[0].endswith("sudo"):
            return 0, "", ""
        return 1, "", "Access denied: logout access denied\nUse 'sudo tailscale logout'."

    monkeypatch.setattr(mod, "_run", fake_run)

    # No password → 428 needs-root.
    r = client.post("/api/att/connectivity/tailscale/logout")
    assert r.status_code == 428
    assert r.json()["detail"] == "needs-root"

    # With a password → runs via sudo -S and the password is fed on stdin only.
    r = client.post("/api/att/connectivity/tailscale/logout", json={"sudo_password": "hunter2"})
    assert r.status_code == 200, r.text
    assert r.json() == {"ok": True}

    sudo_call = next(c for c in calls if c[0][0].endswith("sudo"))
    cmd, stdin = sudo_call
    assert cmd[:4] == [cmd[0], "-S", "-k", "-p"]  # sudo -S -k -p '' …
    assert "hunter2" not in " ".join(cmd)  # never in argv
    assert stdin == b"hunter2\n"  # only on stdin


def test_wrong_sudo_password_returns_403(client, monkeypatch):
    import raspy.attachments.connectivity as mod

    monkeypatch.setattr(mod.shutil, "which", lambda name: f"/usr/bin/{name}")

    async def fake_run(cmd, timeout=30.0, stdin=None):
        if cmd[0].endswith("sudo"):
            return 1, "", "sudo: 1 incorrect password attempt"
        return 1, "", "Access denied: use 'sudo'"

    monkeypatch.setattr(mod, "_run", fake_run)

    r = client.post("/api/att/connectivity/tailscale/down", json={"sudo_password": "nope"})
    assert r.status_code == 403
    assert "password" in r.json()["detail"].lower()


def test_new_tailscale_actions_pass_expected_args(client, monkeypatch):
    """Exit-node, advertise, update and the read-only diagnostics build the right
    tailscale invocation and (for diagnostics) return captured text."""
    import raspy.attachments.connectivity as mod

    monkeypatch.setattr(mod.shutil, "which", lambda name: f"/usr/bin/{name}")
    seen: list[list[str]] = []

    async def fake_run(cmd, timeout=30.0, stdin=None):
        seen.append(cmd)
        if cmd[1] == "netcheck":
            return 0, "Report:\n\t* UDP: true\n", ""
        if cmd[1] == "ping":
            return 0, "pong via DERP\n", ""
        return 0, "", ""

    monkeypatch.setattr(mod, "_run", fake_run)

    # Use an exit node, then clear it.
    r = client.post("/api/att/connectivity/tailscale/exit-node", json={"node": "peer.ts.net"})
    assert r.status_code == 200, r.text
    assert seen[-1][1:] == ["set", "--exit-node=peer.ts.net"]
    client.post("/api/att/connectivity/tailscale/exit-node", json={"node": ""})
    assert seen[-1][1:] == ["set", "--exit-node="]

    # Advertise / stop advertising as an exit node.
    client.post("/api/att/connectivity/tailscale/advertise-exit-node", json={"enable": True})
    assert seen[-1][1:] == ["set", "--advertise-exit-node"]
    client.post("/api/att/connectivity/tailscale/advertise-exit-node", json={"enable": False})
    assert seen[-1][1:] == ["set", "--advertise-exit-node=false"]

    # Client self-update.
    client.post("/api/att/connectivity/tailscale/update")
    assert seen[-1][1:] == ["update", "--yes"]

    # Read-only diagnostics return their text.
    r = client.post("/api/att/connectivity/tailscale/netcheck")
    assert r.status_code == 200
    assert "UDP: true" in r.json()["output"]
    r = client.post("/api/att/connectivity/tailscale/ping", json={"target": "peer.ts.net"})
    assert r.status_code == 200
    assert seen[-1][1:] == ["ping", "-c", "3", "peer.ts.net"]
    assert "pong" in r.json()["output"]


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

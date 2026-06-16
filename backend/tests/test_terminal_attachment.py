"""Terminal attachment: discovery, admin-only gating, shell detection, and the
PTY WebSocket's auth/channel requirements. No real PTY is spawned here — the WS
tests assert it refuses to open without auth + an encrypted channel."""

from __future__ import annotations

import pytest

from raspy.attachments.terminal import Terminal, _detect_shells, _validate_shell, _clamp


def test_terminal_discovered_and_admin_only(client):
    h = client.get("/api/healthz").json()
    loaded = {a["id"] for a in h["attachments"]["loaded"]}
    assert "terminal" in loaded

    from raspy.core.manifest import _ADMIN_ONLY
    assert "terminal" in _ADMIN_ONLY

    # The seeded test account is the admin, so it sees the app with a terminal node.
    manifest = client.get("/api/manifest").json()
    node = next(a for a in manifest["attachments"] if a["id"] == "terminal")
    assert node["ui"]["type"] == "terminal"


def test_shells_endpoint(client):
    r = client.get("/api/att/terminal/shells").json()
    assert "supported" in r and isinstance(r["shells"], list)
    # Each shell entry is shaped for the picker.
    for s in r["shells"]:
        assert set(s) >= {"id", "name", "path"}


def test_detect_shells_only_real_shells():
    """No nologin / git-shell noise from /etc/shells leaks into the picker."""
    names = {s["name"] for s in _detect_shells()}
    assert "git-shell" not in names
    assert "nologin" not in names


def test_validate_shell_rejects_arbitrary_binaries():
    """An admin token must not be able to spawn an arbitrary binary as the shell —
    only a detected shell path is allowed; anything else falls back to a real one."""
    shells = _detect_shells()
    if not shells:
        pytest.skip("no shells on this host")
    chosen = _validate_shell("/usr/bin/totally-not-a-shell")
    assert chosen in {s["path"] for s in shells}
    # A genuine detected shell is preserved.
    assert _validate_shell(shells[0]["path"]) == shells[0]["path"]


def test_clamp_bounds():
    assert _clamp("abc", 24) == 24
    assert _clamp(0, 24) == 1
    assert _clamp(99999, 24) == 1000
    assert _clamp(120, 24) == 120


def test_sessions_listing_starts_empty(client):
    r = client.get("/api/att/terminal/sessions").json()
    assert r["sessions"] == []


def test_pty_ws_refuses_without_channel(client):
    """The PTY socket must close (1008) when no encrypted channel session is
    presented — a shell is never streamed in plaintext."""
    from starlette.websockets import WebSocketDisconnect

    with pytest.raises(WebSocketDisconnect) as exc:
        with client.websocket_connect("/api/att/terminal/pty") as ws:
            ws.receive_text()
    assert exc.value.code == 1008


def test_kill_unknown_session_404(client):
    r = client.delete("/api/att/terminal/sessions/deadbeef")
    assert r.status_code == 404


# --- a minimal channel client, mirroring the frontend crypto ------------------
def _channel_handshake(client):
    """Do a real channel handshake the way the frontend does, returning
    (sid, key) so the test can seal/open frames exactly like the browser."""
    import base64
    from cryptography.hazmat.primitives import hashes
    from cryptography.hazmat.primitives.asymmetric.x25519 import (
        X25519PrivateKey, X25519PublicKey,
    )
    from cryptography.hazmat.primitives.kdf.hkdf import HKDF

    def b64e(b):
        return base64.urlsafe_b64encode(b).rstrip(b"=").decode()

    def b64d(s):
        return base64.urlsafe_b64decode(s + "=" * (-len(s) % 4))

    from cryptography.hazmat.primitives.serialization import Encoding, PublicFormat

    eph = X25519PrivateKey.generate()
    eph_pub = eph.public_key().public_bytes(Encoding.Raw, PublicFormat.Raw)
    hs = client.post("/api/channel/handshake", json={"client_pub": b64e(eph_pub)}).json()
    server_pub = b64d(hs["server_pub"])
    shared = eph.exchange(X25519PublicKey.from_public_bytes(server_pub))
    key = HKDF(
        algorithm=hashes.SHA256(), length=32,
        salt=eph_pub + server_pub, info=b"raspy-channel-v1",
    ).derive(shared)
    return hs["session_id"], key


def test_pty_ws_sealed_open_roundtrip(client):
    """End-to-end: a sealed `open` frame (wrapped exactly like the frontend sends
    it) must reach the PTY and come back as a sealed `ready` — guarding against
    the wrapper not being unwrapped before decrypt."""
    import base64
    import json
    import os
    from cryptography.hazmat.primitives.ciphers.aead import ChaCha20Poly1305

    sid, key = _channel_handshake(client)
    aead = ChaCha20Poly1305(key)

    def seal(obj) -> str:
        nonce = os.urandom(12)
        ct = aead.encrypt(nonce, json.dumps(obj).encode(), None)
        payload = base64.urlsafe_b64encode(nonce + ct).rstrip(b"=").decode()
        return json.dumps({"type": "sealed", "payload": payload})

    def open_frame(raw) -> dict:
        frame = json.loads(raw)
        assert frame["type"] == "sealed"
        blob = base64.urlsafe_b64decode(frame["payload"] + "=" * (-len(frame["payload"]) % 4))
        return json.loads(aead.decrypt(blob[:12], blob[12:], None).decode())

    with client.websocket_connect(f"/api/att/terminal/pty?channel={sid}") as ws:
        ws.send_text(seal({"t": "open", "cols": 80, "rows": 24}))
        msg = open_frame(ws.receive_text())
        # The fix: this is "ready", NOT {"t":"error","msg":"decrypt failed"}.
        assert msg["t"] == "ready", msg
        assert "sid" in msg
        # Clean up the spawned PTY.
        ws.send_text(seal({"t": "input", "data": "exit\n"}))

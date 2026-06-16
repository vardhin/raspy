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

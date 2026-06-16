"""Terminal attachment — a real interactive shell on this machine, streamed over
an encrypted WebSocket.

This is a remote shell on the box (you can run `sudo`, edit files, anything the
service user can do), so it is locked down hard:

  * ADMIN-ONLY (in ``manifest._ADMIN_ONLY``) — children never see it and the
    HTTP routes 403 for non-admins (the core auth gate enforces this).
  * The PTY WebSocket **requires the encrypted channel** (core/channel): without
    a valid ``?channel=<sid>`` it refuses to open. So keystrokes — including any
    sudo password you type — never cross the tunnel in plaintext. Frames are
    sealed BOTH directions; this is the first client→server sealed path (the core
    ws hub only seals outbound).
  * It self-authenticates on the WS handshake (the HTTP auth-gate middleware does
    not run for WebSockets) exactly like core/ws.py: access token + admin role,
    reject frozen children.

Sessions are tmux-like: a PTY survives a browser disconnect and can be reattached
(its recent output is replayed from a ring buffer). An idle PTY is reaped after a
timeout, and all PTYs are killed on shutdown so nothing is orphaned.

POSIX only. On Windows the shells probe still works but opening a PTY reports
``unsupported`` (ConPTY is a separate effort), mirroring how connectivity refuses
cleanly when a provider isn't available.
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
import shutil
import signal
import sys
import time
from dataclasses import dataclass, field
from typing import Any

from fastapi import APIRouter, HTTPException, Request, WebSocket, WebSocketDisconnect

from raspy.core.contract import AttachmentContext, BaseAttachment
from raspy.core import ui

log = logging.getLogger("raspy.terminal")

_POSIX = not sys.platform.startswith("win")

# How much recent output to keep per session for replay on reattach.
_SCROLLBACK_BYTES = 64 * 1024
# Reap a detached (no client attached) session after this many seconds idle.
_IDLE_REAP_S = 30 * 60
# Cap concurrent sessions so a runaway client can't fork-bomb the box with PTYs.
_MAX_SESSIONS = 16


def _detect_shells() -> list[dict[str, str]]:
    """Discover available shells for the topbar picker. Reads /etc/shells when
    present and probes PATH; de-dupes by resolved path. The first entry is the
    sensible default ($SHELL if usable, else the platform default)."""
    found: dict[str, dict[str, str]] = {}  # path -> {id,name,path}

    def add(name: str, path: str | None) -> None:
        if not path:
            return
        rp = os.path.realpath(path)
        if not os.path.isfile(rp) or not os.access(rp, os.X_OK):
            return
        found.setdefault(rp, {"id": name, "name": name, "path": rp})

    if _POSIX:
        # Only genuine interactive shells — /etc/shells also lists things like
        # git-shell and nologin fallbacks that we don't want in the picker.
        known = {"bash", "zsh", "fish", "sh", "dash", "tcsh", "csh", "ksh", "mksh", "pwsh"}
        # /etc/shells is the canonical list of login shells on this host.
        try:
            with open("/etc/shells", encoding="utf-8") as fh:
                for line in fh:
                    line = line.strip()
                    if line and not line.startswith("#") and os.path.basename(line) in known:
                        add(os.path.basename(line), line)
        except OSError:
            pass
        for name in known:
            add(name, shutil.which(name))
    else:
        for name in ("powershell", "pwsh", "cmd"):
            add(name, shutil.which(name) or (name if name == "cmd" else None))

    shells = list(found.values())
    # Default first: $SHELL if we found it, else bash/sh, else whatever's first.
    env_shell = os.environ.get("SHELL")
    default_path = os.path.realpath(env_shell) if env_shell else None
    shells.sort(key=lambda s: (s["path"] != default_path, s["name"]))
    return shells


@dataclass
class _PtySession:
    """One running PTY + child process, with a scrollback buffer for reattach."""

    id: str
    shell: str
    pid: int
    fd: int  # master side of the PTY
    proc: asyncio.subprocess.Process
    cols: int = 80
    rows: int = 24
    created: float = field(default_factory=time.time)
    last_active: float = field(default_factory=time.time)
    # Recent output, trimmed to _SCROLLBACK_BYTES, replayed when a client attaches.
    scrollback: bytearray = field(default_factory=bytearray)
    # The currently-attached websocket, if any (one viewer at a time per session).
    attached: WebSocket | None = None
    # The asyncio task pumping PTY output → the attached socket.
    reader_task: asyncio.Task | None = None
    closed: bool = False

    def touch(self) -> None:
        self.last_active = time.time()

    def remember(self, data: bytes) -> None:
        self.scrollback.extend(data)
        if len(self.scrollback) > _SCROLLBACK_BYTES:
            del self.scrollback[: len(self.scrollback) - _SCROLLBACK_BYTES]


class Terminal(BaseAttachment):
    id = "terminal"
    title = "Terminal"
    icon = "terminal"
    version = "1.0.0"

    def __init__(self) -> None:
        self._sessions: dict[str, _PtySession] = {}
        self._reaper: asyncio.Task | None = None

    async def on_load(self, ctx: AttachmentContext) -> None:
        self._sessions = {}
        if _POSIX:
            self._reaper = asyncio.create_task(self._reap_loop())

    async def on_shutdown(self) -> None:
        if self._reaper:
            self._reaper.cancel()
            try:
                await self._reaper
            except asyncio.CancelledError:
                pass
            self._reaper = None
        for sess in list(self._sessions.values()):
            await self._close_session(sess)

    # ── PTY lifecycle ────────────────────────────────────────────────────────
    async def _spawn(self, shell_path: str, cols: int, rows: int) -> _PtySession:
        if not _POSIX:
            raise HTTPException(501, "terminal is not supported on this platform yet")
        if len(self._sessions) >= _MAX_SESSIONS:
            raise HTTPException(429, "too many open terminal sessions")
        import pty
        import termios

        master, slave = pty.openpty()
        _set_winsize(master, rows, cols)
        # Start the shell as a login, interactive shell attached to the slave fd.
        # start_new_session=True gives it its own session/process group so signals
        # and cleanup target the whole shell, not the spine.
        env = {**os.environ, "TERM": "xterm-256color"}
        proc = await asyncio.create_subprocess_exec(
            shell_path, "-i",
            stdin=slave, stdout=slave, stderr=slave,
            start_new_session=True,
            env=env,
        )
        os.close(slave)  # the child holds it now; we keep the master.
        os.set_blocking(master, False)
        sid = os.urandom(9).hex()
        sess = _PtySession(
            id=sid, shell=shell_path, pid=proc.pid, fd=master, proc=proc,
            cols=cols, rows=rows,
        )
        self._sessions[sid] = sess
        log.info("terminal session %s spawned (%s pid=%s)", sid, shell_path, proc.pid)
        del termios  # imported only to ensure availability on this platform
        return sess

    async def _close_session(self, sess: _PtySession) -> None:
        if sess.closed:
            return
        sess.closed = True
        self._sessions.pop(sess.id, None)
        if sess.reader_task:
            sess.reader_task.cancel()
        # Terminate the whole process group, then the PTY fd.
        try:
            os.killpg(os.getpgid(sess.pid), signal.SIGTERM)
        except (ProcessLookupError, PermissionError, OSError):
            pass
        try:
            os.close(sess.fd)
        except OSError:
            pass
        log.info("terminal session %s closed", sess.id)

    async def _reap_loop(self) -> None:
        while True:
            await asyncio.sleep(60)
            now = time.time()
            for sess in list(self._sessions.values()):
                # A session with a live attachment is never reaped for idleness.
                if sess.attached is not None:
                    continue
                if sess.proc.returncode is not None or now - sess.last_active > _IDLE_REAP_S:
                    await self._close_session(sess)

    # ── router ────────────────────────────────────────────────────────────────
    def router(self) -> APIRouter:
        r = APIRouter()

        def _require_admin(request: Request) -> None:
            from raspy.core.auth.deps import principal_from_request

            p = principal_from_request(request)
            if p is None or not p.is_admin:
                raise HTTPException(403, "admin only")

        @r.get("/shells")
        async def shells(request: Request) -> dict[str, Any]:
            _require_admin(request)
            return {"supported": _POSIX, "shells": _detect_shells()}

        @r.get("/sessions")
        async def sessions(request: Request) -> dict[str, Any]:
            _require_admin(request)
            return {"sessions": [
                {
                    "id": s.id, "shell": s.shell, "cols": s.cols, "rows": s.rows,
                    "created": s.created, "attached": s.attached is not None,
                    "alive": s.proc.returncode is None,
                }
                for s in self._sessions.values()
            ]}

        @r.delete("/sessions/{sid}")
        async def kill_session(request: Request, sid: str) -> dict[str, Any]:
            _require_admin(request)
            sess = self._sessions.get(sid)
            if sess is None:
                raise HTTPException(404, "no such session")
            await self._close_session(sess)
            return {"ok": True}

        @r.websocket("/pty")
        async def pty_ws(ws: WebSocket) -> None:
            await self._pty_ws(ws)

        return r

    # ── the PTY websocket ───────────────────────────────────────────────────
    async def _pty_ws(self, ws: WebSocket) -> None:
        """Authenticate (admin), require a channel session, then stream a PTY.

        Wire protocol (after the channel is opened — every frame is JSON):
          client→server: {"t":"open","shell":..,"cols":..,"rows":..}
                         {"t":"attach","sid":..}
                         {"t":"input","data":"<utf8>"}
                         {"t":"resize","cols":..,"rows":..}
          server→client: {"t":"ready","sid":..,"shell":..}
                         {"t":"output","data":"<utf8>"}
                         {"t":"exit","code":..}
                         {"t":"error","msg":..}
        """
        from raspy.core.auth.deps import ACCESS_COOKIE
        from raspy.core.auth.service import AuthError

        auth = getattr(ws.app.state, "auth", None)
        token = ws.cookies.get(ACCESS_COOKIE) or ws.query_params.get("access_token")
        if auth is None or not token:
            await ws.close(code=1008)
            return
        try:
            claims = auth.verify_access(token)
        except AuthError:
            await ws.close(code=1008)
            return
        # Admin only; a frozen child gets nothing.
        if claims.get("role") != "admin" or claims.get("mr"):
            await ws.close(code=1008)
            return

        # Require the encrypted channel — refuse to stream a shell in plaintext.
        channel = getattr(ws.app.state, "channel", None)
        sid = ws.query_params.get("channel")
        if not (channel and sid and channel.has_session(sid)):
            await ws.close(code=1008)  # client must handshake the channel first
            return

        if not _POSIX:
            await ws.accept()
            await _send(ws, channel, sid, {"t": "error", "msg": "terminal unsupported on this platform"})
            await ws.close()
            return

        await ws.accept()
        sess: _PtySession | None = None
        try:
            while True:
                raw = await ws.receive_text()
                try:
                    msg = json.loads(channel.open(sid, raw).decode())
                except Exception:
                    await _send(ws, channel, sid, {"t": "error", "msg": "decrypt failed"})
                    continue
                t = msg.get("t")

                if t == "open" and sess is None:
                    shell = _validate_shell(msg.get("shell"))
                    cols = _clamp(msg.get("cols"), 80)
                    rows = _clamp(msg.get("rows"), 24)
                    sess = await self._spawn(shell, cols, rows)
                    self._attach(ws, channel, sid, sess, replay=False)
                    await _send(ws, channel, sid, {"t": "ready", "sid": sess.id, "shell": sess.shell})

                elif t == "attach" and sess is None:
                    want = self._sessions.get(str(msg.get("sid")))
                    if want is None or want.proc.returncode is not None:
                        await _send(ws, channel, sid, {"t": "error", "msg": "session gone"})
                        continue
                    if want.attached is not None:
                        # Steal the attachment from a stale viewer (single viewer).
                        await _detach_other(want)
                    sess = want
                    self._attach(ws, channel, sid, sess, replay=True)
                    await _send(ws, channel, sid, {"t": "ready", "sid": sess.id, "shell": sess.shell})

                elif t == "input" and sess is not None:
                    data = str(msg.get("data", ""))
                    try:
                        os.write(sess.fd, data.encode())
                        sess.touch()
                    except OSError:
                        await _send(ws, channel, sid, {"t": "exit", "code": -1})

                elif t == "resize" and sess is not None:
                    sess.cols = _clamp(msg.get("cols"), sess.cols)
                    sess.rows = _clamp(msg.get("rows"), sess.rows)
                    _set_winsize(sess.fd, sess.rows, sess.cols)
                    sess.touch()
                # Unknown messages are ignored (forward-compatible).
        except WebSocketDisconnect:
            pass
        except Exception:  # noqa: BLE001
            log.exception("terminal ws error")
        finally:
            # Detach but DO NOT kill — the session persists for reattach. The
            # reaper collects it if no one comes back.
            if sess is not None and sess.attached is ws:
                if sess.reader_task:
                    sess.reader_task.cancel()
                    sess.reader_task = None
                sess.attached = None

    def _attach(self, ws: WebSocket, channel, sid: str, sess: _PtySession, *, replay: bool) -> None:
        """Bind this socket to the session and start pumping PTY output to it."""
        sess.attached = ws
        sess.reader_task = asyncio.create_task(self._pump(ws, channel, sid, sess, replay=replay))

    async def _pump(self, ws: WebSocket, channel, sid: str, sess: _PtySession, *, replay: bool = False) -> None:
        """Read the PTY master fd and forward sealed output frames. Ends when the
        child exits (read returns EOF / raises)."""
        loop = asyncio.get_running_loop()
        try:
            # Replay recent scrollback FIRST (ordered before any live output) so a
            # reattached client sees context without racing the live stream.
            if replay and sess.scrollback:
                await _send(ws, channel, sid, {"t": "output", "data": bytes(sess.scrollback).decode(errors="replace")})
            while True:
                data = await _read_fd(loop, sess.fd)
                if not data:  # EOF — shell exited
                    break
                sess.remember(data)
                sess.touch()
                await _send(ws, channel, sid, {"t": "output", "data": data.decode(errors="replace")})
        except asyncio.CancelledError:
            raise
        except Exception:  # noqa: BLE001
            pass
        finally:
            code = sess.proc.returncode
            with _suppress():
                await _send(ws, channel, sid, {"t": "exit", "code": code if code is not None else 0})
            await self._close_session(sess)

    def ui(self) -> Any:
        return ui._node("terminal", title="Terminal")


# ── module-level helpers ──────────────────────────────────────────────────────
def _set_winsize(fd: int, rows: int, cols: int) -> None:
    if not _POSIX:
        return
    import fcntl
    import struct
    import termios

    try:
        fcntl.ioctl(fd, termios.TIOCSWINSZ, struct.pack("HHHH", rows, cols, 0, 0))
    except OSError:
        pass


async def _read_fd(loop: asyncio.AbstractEventLoop, fd: int) -> bytes:
    """Await readability on the PTY master, then read a chunk. Uses the loop's
    reader so we never block the event loop on a blocking fd."""
    fut: asyncio.Future[bytes] = loop.create_future()

    def _on_readable() -> None:
        if fut.done():
            return
        loop.remove_reader(fd)
        try:
            fut.set_result(os.read(fd, 65536))
        except (BlockingIOError, InterruptedError):
            loop.add_reader(fd, _on_readable)  # spurious wake — keep waiting
        except OSError:
            fut.set_result(b"")  # fd closed / child gone → EOF

    loop.add_reader(fd, _on_readable)
    try:
        return await fut
    finally:
        with _suppress():
            loop.remove_reader(fd)


async def _send(ws: WebSocket, channel, sid: str, message: dict) -> None:
    """Seal a message for the channel and send it as one sealed frame."""
    payload = channel.seal(sid, json.dumps(message).encode())
    await ws.send_text(json.dumps({"type": "sealed", "payload": payload}))


async def _detach_other(sess: _PtySession) -> None:
    other = sess.attached
    sess.attached = None
    if sess.reader_task:
        sess.reader_task.cancel()
        sess.reader_task = None
    if other is not None:
        with _suppress():
            await other.close(code=1001)  # going away — replaced by a new viewer


def _validate_shell(path: Any) -> str:
    """Only allow spawning a shell we actually detected, so an attacker who got an
    admin token can't turn this into 'run any binary as argv[0]'."""
    allowed = {s["path"]: s["path"] for s in _detect_shells()}
    p = os.path.realpath(str(path)) if path else ""
    if p in allowed:
        return p
    # Fall back to the default (first detected) shell.
    shells = _detect_shells()
    if not shells:
        raise HTTPException(503, "no usable shell found on this machine")
    return shells[0]["path"]


def _clamp(v: Any, default: int) -> int:
    try:
        n = int(v)
    except (TypeError, ValueError):
        return default
    return max(1, min(1000, n))


class _suppress:
    """Tiny contextmanager that swallows exceptions (sync + async friendly)."""

    def __enter__(self) -> "_suppress":
        return self

    def __exit__(self, *exc: Any) -> bool:
        return True


attachment = Terminal()

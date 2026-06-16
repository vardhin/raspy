"""Connectivity attachment — a networking dashboard + remote-access control.

Shows every way to reach this Raspy box as a ready-to-use ``http://<addr>:<port>``
link — LAN/private IPs (v4+v6), the public IP, the Tailscale address + MagicDNS
name, and the Cloudflare tunnel hostname — and lets an admin bring the remote
links up:

  * Tailscale — already a machine-level VPN; Raspy DISCOVERS the assigned IP /
    MagicDNS name and shows the access link. If installed-but-logged-out it can
    trigger ``tailscale up`` and surface the login URL the daemon prints. The
    node key lives in tailscaled, never in Raspy.
  * Cloudflare Tunnel — Raspy supervises ``cloudflared tunnel run --token <T>``.
    The token is encrypted at rest (per-attachment Fernet key) and never returned
    to the client after being set.

ADMIN-ONLY (in ``manifest._ADMIN_ONLY``): it controls public exposure and a
stored secret. It never runs as root and never installs the provider binaries —
it detects them and links to docs if missing. See plan/56-connectivity.md.
"""

from __future__ import annotations

import asyncio
import logging
import os
import re
import shutil
import json as _json
from typing import Any

from cryptography.fernet import Fernet
from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel, Field

from raspy.config import get_settings
from raspy.core import ui
from raspy.core.contract import AttachmentContext, BaseAttachment

from . import netinfo

log = logging.getLogger("raspy.connectivity")


def _load_or_create_key(path) -> bytes:
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.is_file():
        return path.read_bytes()
    key = Fernet.generate_key()
    path.write_bytes(key)
    try:
        os.chmod(path, 0o600)
    except OSError:
        pass
    return key


class CloudflareToken(BaseModel):
    token: str = Field(min_length=10, max_length=4096)


class SudoBody(BaseModel):
    """Optional sudo password for a privileged action. Sent only over the
    encrypted channel (see core/channel) and used transiently — never stored,
    never logged, never placed in a command's argv."""

    sudo_password: str | None = Field(default=None, max_length=1024)


class SshToggle(SudoBody):
    enable: bool = True


class ExitNodeBody(SudoBody):
    """Route this node's traffic through ``node`` (DNSName or IP), or clear the
    exit node when ``node`` is empty/None."""

    node: str | None = Field(default=None, max_length=256)


class ExitNodeAdvertiseBody(SudoBody):
    enable: bool = True


class PingBody(BaseModel):
    """Read-only diagnostic: ping a tailnet peer. No sudo (it doesn't need root)."""

    target: str = Field(min_length=1, max_length=256)


async def _run(
    cmd: list[str], timeout: float = 30.0, stdin: bytes | None = None
) -> tuple[int, str, str]:
    """Run a command capturing output, off the event loop. Optional ``stdin`` is
    fed once and the pipe closed (used to hand `sudo -S` a password without ever
    putting it in argv, which is world-readable via /proc)."""
    proc = await asyncio.create_subprocess_exec(
        *cmd,
        stdin=asyncio.subprocess.PIPE if stdin is not None else None,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )
    try:
        out, err = await asyncio.wait_for(proc.communicate(input=stdin), timeout=timeout)
    except asyncio.TimeoutError:
        proc.kill()
        return 124, "", "timed out"
    return proc.returncode or 0, out.decode(errors="replace"), err.decode(errors="replace")


# Marker the UI keys off to know it should pop the sudo-password prompt and retry.
_NEEDS_ROOT = "needs-root"

# Substrings sudo / the tools print when escalation is required or the password
# was wrong — used to translate a raw failure into a "needs root" signal.
_ROOT_HINTS = ("access denied", "permission denied", "must be run as root",
               "operation not permitted", "use 'sudo")
_BADPW_HINTS = ("incorrect password", "sorry, try again", "authentication failure")


def _looks_like_needs_root(text: str) -> bool:
    t = text.lower()
    return any(h in t for h in _ROOT_HINTS)


async def _run_maybe_sudo(
    cmd: list[str], timeout: float, sudo_password: str | None
) -> tuple[int, str, str]:
    """Run ``cmd``; if a sudo password is supplied, run it through
    ``sudo -S -p '' -k`` and feed the password on stdin. ``-k`` invalidates any
    cached credential first so a stale timestamp can't mask a wrong password."""
    if sudo_password is None:
        return await _run(cmd, timeout=timeout)
    sudo = shutil.which("sudo")
    if not sudo:
        raise HTTPException(400, "sudo is not available on this machine")
    return await _run(
        [sudo, "-S", "-k", "-p", "", *cmd],
        timeout=timeout,
        stdin=(sudo_password + "\n").encode(),
    )


def _port() -> int:
    return get_settings().port


def _link(host: str) -> str:
    return f"http://{host}:{_port()}"


class Connectivity(BaseAttachment):
    id = "connectivity"
    title = "Connectivity"
    icon = "globe"
    version = "1.2.0"

    _cf_proc: asyncio.subprocess.Process | None = None
    _cf_hostname: str | None = None
    # When `tailscale up` is logged out it prints a login URL; we surface the most
    # recent one so the UI can show "click to log in".
    _ts_login_url: str | None = None

    async def on_load(self, ctx: AttachmentContext) -> None:
        self._cf_proc = None
        self._cf_hostname = None
        self._ts_login_url = None
        await self._ensure_tables()
        try:
            if await self._cf_autostart_wanted() and self._cf_token():
                await self._cf_start()
        except Exception:
            log.exception("cloudflare auto-resume failed")

    async def on_shutdown(self) -> None:
        await self._cf_stop()

    # ── storage ─────────────────────────────────────────────────────────────
    async def _ensure_tables(self) -> None:
        t = self.db.table("settings")
        await self.db.execute(
            f"CREATE TABLE IF NOT EXISTS {t} (key TEXT PRIMARY KEY, value TEXT NOT NULL)"
        )

    async def _set(self, key: str, value: str) -> None:
        t = self.db.table("settings")
        await self.db.execute(
            f"INSERT INTO {t} (key, value) VALUES (?, ?) "
            f"ON CONFLICT(key) DO UPDATE SET value=excluded.value",
            (key, value),
        )

    async def _get(self, key: str) -> str | None:
        t = self.db.table("settings")
        row = await self.db.fetch_one(f"SELECT value FROM {t} WHERE key = ?", (key,))
        return row["value"] if row else None

    def _fernet(self) -> Fernet:
        return Fernet(_load_or_create_key(self.account_data_dir / "connectivity.key"))

    def _token_path(self):
        return self.account_data_dir / "cloudflare_token.enc"

    async def _save_cf_token(self, token: str) -> None:
        enc = self._fernet().encrypt(token.encode())
        path = self._token_path()
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(enc)
        try:
            os.chmod(path, 0o600)
        except OSError:
            pass

    def _cf_token(self) -> str | None:
        path = self._token_path()
        if not path.is_file():
            return None
        try:
            return self._fernet().decrypt(path.read_bytes()).decode()
        except Exception:
            log.warning("could not decrypt cloudflare token")
            return None

    async def _cf_autostart_wanted(self) -> bool:
        return (await self._get("cf_autostart")) == "1"

    # ── cloudflared supervision ─────────────────────────────────────────────
    @staticmethod
    def _cloudflared_bin() -> str | None:
        return shutil.which("cloudflared")

    async def _cf_start(self) -> None:
        binary = self._cloudflared_bin()
        if not binary:
            raise HTTPException(503, "cloudflared is not installed on this machine")
        token = self._cf_token()
        if not token:
            raise HTTPException(400, "no Cloudflare token configured")
        await self._cf_stop()  # idempotent
        self._cf_proc = await asyncio.create_subprocess_exec(
            binary, "tunnel", "--no-autoupdate", "run", "--token", token,
            stdout=asyncio.subprocess.DEVNULL,
            stderr=asyncio.subprocess.DEVNULL,
        )
        await self._set("cf_autostart", "1")
        log.info("cloudflared started (pid %s)", self._cf_proc.pid)

    async def _cf_stop(self) -> None:
        proc = self._cf_proc
        self._cf_proc = None
        if proc is None or proc.returncode is not None:
            return
        proc.terminate()
        try:
            await asyncio.wait_for(proc.wait(), timeout=10)
        except asyncio.TimeoutError:
            proc.kill()

    def _cf_running(self) -> bool:
        return self._cf_proc is not None and self._cf_proc.returncode is None

    # ── tailscale ───────────────────────────────────────────────────────────
    @staticmethod
    def _tailscale_bin() -> str | None:
        return shutil.which("tailscale")

    async def _tailscale_status(self) -> dict[str, Any]:
        ts_bin = self._tailscale_bin()
        info: dict[str, Any] = {
            "installed": bool(ts_bin),
            "state": "not-installed",
            "connected": False,
            "ips": [],
            "magic_dns": None,
            "links": [],
            "login_url": self._ts_login_url,
            "login_name": None,     # the tailnet account email this node is logged in as
            "display_name": None,
            "hostname": None,
            "tailnet": None,
            "ssh": False,           # is this node advertising Tailscale SSH?
            "exit_node": None,      # DNSName of the exit node we're routing through, if any
            "advertising_exit_node": False,  # are WE offering to be an exit node?
            "exit_nodes": [],       # available exit-node peers: [{name, online}]
            "version": None,        # tailscale client version
            "update_available": False,  # a newer tailscale client exists
            "install_url": "https://tailscale.com/download",
        }
        if not ts_bin:
            return info
        code, out, _ = await _run([ts_bin, "status", "--json"])
        if code != 0:
            info["state"] = "error"
            return info
        try:
            data = _json.loads(out)
        except Exception:
            info["state"] = "error"
            return info
        backend = data.get("BackendState", "Unknown")
        self_node = data.get("Self") or {}
        ips = self_node.get("TailscaleIPs") or []
        dns = (self_node.get("DNSName") or "").rstrip(".")  # e.g. raspy.tailnet.ts.net
        info["state"] = backend.lower()  # "running" | "stopped" | "needslogin" | …
        info["connected"] = backend == "Running" and bool(ips)
        info["ips"] = ips
        info["magic_dns"] = dns or None
        info["hostname"] = self_node.get("HostName")
        # The login identity: User map keyed by Self.UserID carries the email.
        uid = self_node.get("UserID")
        user = (data.get("User") or {}).get(str(uid)) or {}
        info["login_name"] = user.get("LoginName")
        info["display_name"] = user.get("DisplayName")
        tn = data.get("CurrentTailnet") or {}
        info["tailnet"] = tn.get("Name") or data.get("MagicDNSSuffix")
        # If the daemon already surfaced a login URL (needs-login), prefer it.
        if data.get("AuthURL"):
            info["login_url"] = self._ts_login_url = data["AuthURL"]
        # SSH advertised? It shows up as an "ssh" capability on Self.
        caps = self_node.get("Capabilities") or []
        cap_map = self_node.get("CapMap") or {}
        info["ssh"] = any("ssh" in str(c).lower() for c in caps) or any(
            "ssh" in str(k).lower() for k in cap_map
        )
        # Are we offering ourselves as an exit node?
        info["advertising_exit_node"] = bool(self_node.get("ExitNodeOption"))
        # Client version + whether the daemon thinks a newer client exists.
        info["version"] = data.get("Version")
        cv = data.get("ClientVersion") or {}
        # RunningLatest=True means up to date; absent/False means an update exists.
        info["update_available"] = cv.get("RunningLatest") is False
        # Peers: which one is the active exit node, and which can serve as one.
        peers = (data.get("Peer") or {}).values()
        exit_nodes: list[dict[str, Any]] = []
        for p in peers:
            if not p.get("ExitNodeOption"):
                continue
            name = (p.get("DNSName") or "").rstrip(".") or p.get("HostName")
            exit_nodes.append({"name": name, "online": bool(p.get("Online"))})
            if p.get("ExitNode"):
                info["exit_node"] = name
        info["exit_nodes"] = exit_nodes
        # Build access links: MagicDNS name first (friendliest), then each IP.
        links: list[dict[str, str]] = []
        if dns:
            links.append({"label": "MagicDNS", "url": _link(dns)})
        for ip in ips:
            links.append({"label": "IP", "url": _link(netinfo._link_host(ip))})
        info["links"] = links
        return info

    async def _tailscale_up(self, sudo_password: str | None = None) -> dict[str, Any]:
        """Bring Tailscale up. If the daemon needs an interactive login it prints a
        URL on stderr; we capture and surface it rather than block. Does NOT take an
        auth key — the normal flow is a browser login. If `up` itself needs root and
        no password was given, signal needs-root so the UI can prompt and retry."""
        ts_bin = self._tailscale_bin()
        if not ts_bin:
            raise HTTPException(503, "tailscale is not installed on this machine")
        # --timeout keeps `up` from hanging waiting for auth; we just want the URL.
        code, out, err = await _run_maybe_sudo(
            [ts_bin, "up", "--timeout", "1s"], timeout=20, sudo_password=sudo_password
        )
        text = f"{out}\n{err}"
        m = re.search(r"https://login\.tailscale\.com/\S+", text)
        if m:
            self._ts_login_url = m.group(0)
            return {"ok": True, "needs_login": True, "login_url": self._ts_login_url}
        if code != 0:
            detail = (err or out or "tailscale up failed").strip()
            if sudo_password is None and _looks_like_needs_root(detail):
                # 428 (not 401) so the client's auth-refresh path is untouched —
                # this is "you must supply a precondition (the sudo password)".
                raise HTTPException(428, _NEEDS_ROOT)
            if sudo_password is not None and any(
                h in detail.lower() for h in _BADPW_HINTS
            ):
                raise HTTPException(403, "wrong sudo password")
            raise HTTPException(400, detail[:500])
        self._ts_login_url = None
        return {"ok": True, "needs_login": False}

    # ── full status (the dashboard) ─────────────────────────────────────────
    async def _status(self) -> dict[str, Any]:
        port = _port()
        # Local interfaces + public IP run off the loop (socket/HTTP work). Each
        # probe is independent and best-effort: one failing (no network, blocked
        # lookup, tailscale daemon hiccup) must not blank the whole dashboard.
        try:
            local = await asyncio.to_thread(netinfo.local_addresses)
        except Exception:
            log.exception("local address probe failed")
            local = []
        try:
            public = await asyncio.to_thread(netinfo.public_ip)
        except Exception:
            public = {"v4": None, "v6": None}
        try:
            tailscale = await self._tailscale_status()
        except Exception:
            log.exception("tailscale status probe failed")
            tailscale = {"installed": bool(self._tailscale_bin()), "state": "error",
                         "connected": False, "ips": [], "magic_dns": None, "links": [],
                         "login_url": None, "login_name": None, "display_name": None,
                         "hostname": None, "tailnet": None, "ssh": False,
                         "exit_node": None, "advertising_exit_node": False,
                         "exit_nodes": [], "version": None, "update_available": False,
                         "install_url": "https://tailscale.com/download"}

        # Attach a ready-to-use link to every local address.
        for a in local:
            a["url"] = _link(a["host"])

        cf_bin = self._cloudflared_bin()
        cloudflare = {
            "installed": bool(cf_bin),
            "configured": self._cf_token() is not None,
            "running": self._cf_running(),
            "hostname": self._cf_hostname,
            "url": _link(self._cf_hostname) if self._cf_hostname else None,
            "install_url": "https://developers.cloudflare.com/cloudflare-one/connections/connect-networks/downloads/",
        }

        return {
            "port": port,
            "local": local,
            "public": {"v4": public.get("v4"), "v6": public.get("v6")},
            "tailscale": tailscale,
            "cloudflare": cloudflare,
        }

    # ── router ──────────────────────────────────────────────────────────────
    def router(self) -> APIRouter:
        r = APIRouter()

        def _require_admin(request: Request) -> None:
            from raspy.core.auth.deps import principal_from_request

            p = principal_from_request(request)
            if p is None or not p.is_admin:
                raise HTTPException(403, "admin only")

        @r.get("/status")
        async def status(request: Request) -> dict[str, Any]:
            _require_admin(request)
            return await self._status()

        @r.post("/cloudflare/token")
        async def cf_token(request: Request, body: CloudflareToken) -> dict[str, Any]:
            _require_admin(request)
            await self._save_cf_token(body.token.strip())
            return {"ok": True, "configured": True}

        @r.post("/cloudflare/up")
        async def cf_up(request: Request) -> dict[str, Any]:
            _require_admin(request)
            await self._cf_start()
            await self.notify("Tunnel up", "Cloudflare tunnel started.", url="/a/connectivity")
            return {"ok": True, "running": True}

        @r.post("/cloudflare/down")
        async def cf_down(request: Request) -> dict[str, Any]:
            _require_admin(request)
            await self._cf_stop()
            await self._set("cf_autostart", "0")
            return {"ok": True, "running": False}

        @r.post("/tailscale/up")
        async def ts_up(request: Request, body: SudoBody | None = None) -> dict[str, Any]:
            _require_admin(request)
            return await self._tailscale_up((body or SudoBody()).sudo_password)

        @r.post("/tailscale/down")
        async def ts_down(request: Request, body: SudoBody | None = None) -> dict[str, Any]:
            _require_admin(request)
            return await self._ts_simple(
                ["down"], "tailscale down failed", (body or SudoBody()).sudo_password
            )

        @r.post("/tailscale/logout")
        async def ts_logout(request: Request, body: SudoBody | None = None) -> dict[str, Any]:
            """Fully log out (forgets the node key / account), not just 'down'."""
            _require_admin(request)
            self._ts_login_url = None
            return await self._ts_simple(
                ["logout"], "tailscale logout failed", (body or SudoBody()).sudo_password
            )

        @r.post("/tailscale/ssh")
        async def ts_ssh(request: Request, body: SshToggle) -> dict[str, Any]:
            """Enable or disable Tailscale SSH on this node (tailscale set --ssh)."""
            _require_admin(request)
            flag = "--ssh" if body.enable else "--ssh=false"
            return await self._ts_simple(
                ["set", flag], "tailscale set --ssh failed", body.sudo_password
            )

        @r.post("/tailscale/exit-node")
        async def ts_exit_node(request: Request, body: ExitNodeBody) -> dict[str, Any]:
            """Route this node's traffic through an exit node, or clear it. An empty
            ``node`` clears (``set --exit-node=``)."""
            _require_admin(request)
            node = (body.node or "").strip()
            return await self._ts_simple(
                ["set", f"--exit-node={node}"],
                "tailscale set --exit-node failed",
                body.sudo_password,
            )

        @r.post("/tailscale/advertise-exit-node")
        async def ts_advertise_exit(request: Request, body: ExitNodeAdvertiseBody) -> dict[str, Any]:
            """Offer (or stop offering) this node as an exit node for the tailnet."""
            _require_admin(request)
            flag = "--advertise-exit-node" if body.enable else "--advertise-exit-node=false"
            return await self._ts_simple(
                ["set", flag], "tailscale set --advertise-exit-node failed", body.sudo_password
            )

        @r.post("/tailscale/update")
        async def ts_update(request: Request, body: SudoBody | None = None) -> dict[str, Any]:
            """Update the tailscale client to the latest version (tailscale update --yes)."""
            _require_admin(request)
            return await self._ts_simple(
                ["update", "--yes"], "tailscale update failed",
                (body or SudoBody()).sudo_password,
            )

        @r.post("/tailscale/netcheck")
        async def ts_netcheck(request: Request) -> dict[str, Any]:
            """Read-only network diagnostic (no root needed); returns the report text."""
            _require_admin(request)
            return await self._ts_diagnostic(["netcheck"], "tailscale netcheck failed")

        @r.post("/tailscale/ping")
        async def ts_ping(request: Request, body: PingBody) -> dict[str, Any]:
            """Read-only: ping a tailnet peer (3 packets); returns the output text."""
            _require_admin(request)
            return await self._ts_diagnostic(
                ["ping", "-c", "3", body.target.strip()], "tailscale ping failed"
            )

        return r

    async def _ts_simple(
        self, args: list[str], errmsg: str, sudo_password: str | None = None
    ) -> dict[str, Any]:
        """Run a tailscale subcommand that has no special output handling.
        Refuses cleanly when not installed; surfaces the real error otherwise.

        When the command fails because it needs root and no password was given,
        return HTTP 428 with ``detail: needs-root`` so the UI can prompt for the
        sudo password and retry — rather than silently escalating (plan/56)."""
        ts_bin = self._tailscale_bin()
        if not ts_bin:
            raise HTTPException(503, "tailscale is not installed on this machine")
        code, out, err = await _run_maybe_sudo(
            [ts_bin, *args], timeout=30, sudo_password=sudo_password
        )
        if code != 0:
            detail = (err or out or errmsg).strip()
            if sudo_password is None and _looks_like_needs_root(detail):
                # 428 (not 401) so the client's auth-refresh path is untouched —
                # this is "you must supply a precondition (the sudo password)".
                raise HTTPException(428, _NEEDS_ROOT)
            if sudo_password is not None and any(
                h in detail.lower() for h in _BADPW_HINTS
            ):
                raise HTTPException(403, "wrong sudo password")
            raise HTTPException(400, detail[:500])
        return {"ok": True}

    async def _ts_diagnostic(self, args: list[str], errmsg: str) -> dict[str, Any]:
        """Run a read-only tailscale diagnostic (netcheck/ping) and return its text
        output for the UI to display. These don't need root, so there's no sudo
        path; a non-zero exit still surfaces the captured output."""
        ts_bin = self._tailscale_bin()
        if not ts_bin:
            raise HTTPException(503, "tailscale is not installed on this machine")
        code, out, err = await _run([ts_bin, *args], timeout=30)
        text = (out + err).strip()
        if code != 0 and not text:
            raise HTTPException(400, errmsg)
        return {"ok": code == 0, "output": text[:8000]}

    def ui(self) -> Any:
        return ui._node("connectivity", title="Connectivity")


attachment = Connectivity()

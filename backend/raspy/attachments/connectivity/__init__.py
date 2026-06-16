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


class SshToggle(BaseModel):
    enable: bool = True


async def _run(cmd: list[str], timeout: float = 30.0) -> tuple[int, str, str]:
    """Run a command capturing output, off the event loop."""
    proc = await asyncio.create_subprocess_exec(
        *cmd,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )
    try:
        out, err = await asyncio.wait_for(proc.communicate(), timeout=timeout)
    except asyncio.TimeoutError:
        proc.kill()
        return 124, "", "timed out"
    return proc.returncode or 0, out.decode(errors="replace"), err.decode(errors="replace")


def _port() -> int:
    return get_settings().port


def _link(host: str) -> str:
    return f"http://{host}:{_port()}"


class Connectivity(BaseAttachment):
    id = "connectivity"
    title = "Connectivity"
    icon = "globe"
    version = "1.1.0"

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
        # Build access links: MagicDNS name first (friendliest), then each IP.
        links: list[dict[str, str]] = []
        if dns:
            links.append({"label": "MagicDNS", "url": _link(dns)})
        for ip in ips:
            links.append({"label": "IP", "url": _link(netinfo._link_host(ip))})
        info["links"] = links
        return info

    async def _tailscale_up(self) -> dict[str, Any]:
        """Bring Tailscale up. If the daemon needs an interactive login it prints a
        URL on stderr; we capture and surface it rather than block. Does NOT take an
        auth key — the normal flow is a browser login."""
        ts_bin = self._tailscale_bin()
        if not ts_bin:
            raise HTTPException(503, "tailscale is not installed on this machine")
        # --timeout keeps `up` from hanging waiting for auth; we just want the URL.
        code, out, err = await _run(
            [ts_bin, "up", "--timeout", "1s"], timeout=20
        )
        text = f"{out}\n{err}"
        m = re.search(r"https://login\.tailscale\.com/\S+", text)
        if m:
            self._ts_login_url = m.group(0)
            return {"ok": True, "needs_login": True, "login_url": self._ts_login_url}
        if code != 0:
            # Common: needs root. Surface the real reason for the UI to show.
            raise HTTPException(400, (err or out or "tailscale up failed").strip()[:500])
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
        async def ts_up(request: Request) -> dict[str, Any]:
            _require_admin(request)
            return await self._tailscale_up()

        @r.post("/tailscale/down")
        async def ts_down(request: Request) -> dict[str, Any]:
            _require_admin(request)
            return await self._ts_simple(["down"], "tailscale down failed")

        @r.post("/tailscale/logout")
        async def ts_logout(request: Request) -> dict[str, Any]:
            """Fully log out (forgets the node key / account), not just 'down'."""
            _require_admin(request)
            self._ts_login_url = None
            return await self._ts_simple(["logout"], "tailscale logout failed")

        @r.post("/tailscale/ssh")
        async def ts_ssh(request: Request, body: SshToggle) -> dict[str, Any]:
            """Enable or disable Tailscale SSH on this node (tailscale set --ssh)."""
            _require_admin(request)
            flag = "--ssh" if body.enable else "--ssh=false"
            return await self._ts_simple(["set", flag], "tailscale set --ssh failed")

        return r

    async def _ts_simple(self, args: list[str], errmsg: str) -> dict[str, Any]:
        """Run a tailscale subcommand that has no special output handling.
        Refuses cleanly when not installed; surfaces the real error otherwise."""
        ts_bin = self._tailscale_bin()
        if not ts_bin:
            raise HTTPException(503, "tailscale is not installed on this machine")
        code, out, err = await _run([ts_bin, *args], timeout=30)
        if code != 0:
            raise HTTPException(400, (err or out or errmsg).strip()[:500])
        return {"ok": True}

    def ui(self) -> Any:
        return ui._node("connectivity", title="Connectivity")


attachment = Connectivity()

"""Self-update: check GitHub Releases, and on one-click confirmation download +
verify + swap the platform binary and restart via the OS service manager.

Design (see plan/55-distribution.md):

  * CHECK is cheap and safe: read latest.json (published by release.yml) from the
    repo's latest release, compare its version to raspy.__version__. A periodic
    background task does this and, when newer, raises a notification through the
    existing bus — the user sees a banner. No download happens automatically.
  * APPLY is explicit (a POST the UI fires on "Update now"): download the matching
    raspy-<os>-<arch> asset, verify it against SHA256SUMS, atomically swap it in
    place of the running binary, then ask the service manager to restart us. The
    app NEVER silently restarts.

Only meaningful for the frozen single-file binary (sys.frozen). A source checkout
reports updatable=False — there's no single artifact to swap.
"""

from __future__ import annotations

import asyncio
import hashlib
import json
import logging
import os
import platform
import shutil
import subprocess
import sys
import tempfile
import urllib.request
from dataclasses import dataclass
from pathlib import Path

from .. import __version__
from ..config import Settings

log = logging.getLogger("raspy.updater")

_UA = {"User-Agent": f"raspy-updater/{__version__}"}


def _asset_name() -> str | None:
    """raspy-<os>-<arch>[.exe] for the running platform, matching release.yml."""
    sysname = sys.platform
    machine = platform.machine().lower()
    if machine in ("x86_64", "amd64"):
        arch = "x64"
    elif machine in ("aarch64", "arm64"):
        arch = "arm64"
    else:
        return None
    if sysname.startswith("linux"):
        return f"raspy-linux-{arch}"
    if sysname == "darwin":
        return f"raspy-macos-{arch}"
    if sysname.startswith("win"):
        # windows arm64 falls back to the x64 build (see install.ps1).
        return "raspy-windows-x64.exe"
    return None


def _parse_version(v: str) -> tuple[int, ...]:
    """Lenient semver tuple: '1.2.3' -> (1,2,3). Non-numeric pieces -> 0 so a
    comparison never raises; a malformed remote version just won't out-rank us."""
    out = []
    for part in v.strip().lstrip("v").split("."):
        num = "".join(ch for ch in part if ch.isdigit())
        out.append(int(num) if num else 0)
    return tuple(out) or (0,)


def is_newer(remote: str, local: str = __version__) -> bool:
    return _parse_version(remote) > _parse_version(local)


def is_frozen() -> bool:
    return bool(getattr(sys, "frozen", False))


def _self_path() -> Path:
    """Absolute path to the currently running binary (frozen) or interpreter."""
    return Path(sys.executable).resolve()


@dataclass
class UpdateInfo:
    current: str
    latest: str | None
    available: bool
    updatable: bool          # frozen binary on a known platform
    asset: str | None
    reason: str | None = None

    def as_dict(self) -> dict:
        return {
            "current": self.current,
            "latest": self.latest,
            "available": self.available,
            "updatable": self.updatable,
            "asset": self.asset,
            "reason": self.reason,
        }


def _fetch(url: str, timeout: float = 20.0) -> bytes:
    req = urllib.request.Request(url, headers=_UA)
    with urllib.request.urlopen(req, timeout=timeout) as resp:  # noqa: S310 (trusted GitHub URL)
        return resp.read()


class Updater:
    """Owns update checks + applies. One instance lives on app.state."""

    def __init__(self, settings: Settings, events=None, notifications=None) -> None:
        self._settings = settings
        self._events = events
        self._notifications = notifications
        self._repo = settings.update_repo
        self._task: asyncio.Task | None = None
        # Remember the last version we already notified about so the periodic
        # check doesn't nag every interval for the same release.
        self._notified_version: str | None = None
        self._applying = False

    # ── release metadata ────────────────────────────────────────────────────
    def _latest_json_url(self) -> str:
        return f"https://github.com/{self._repo}/releases/latest/download/latest.json"

    def _asset_url(self, name: str) -> str:
        return f"https://github.com/{self._repo}/releases/latest/download/{name}"

    def _sums_url(self) -> str:
        return f"https://github.com/{self._repo}/releases/latest/download/SHA256SUMS"

    async def check(self) -> UpdateInfo:
        """Look up the latest release version. Network + parse run in a thread so
        the event loop is never blocked."""
        asset = _asset_name()
        updatable = is_frozen() and asset is not None
        try:
            raw = await asyncio.to_thread(_fetch, self._latest_json_url())
            meta = json.loads(raw.decode())
            latest = str(meta.get("version") or "").strip() or None
        except Exception as exc:  # network down, no release yet, etc.
            log.info("update check failed: %s", exc)
            return UpdateInfo(
                current=__version__, latest=None, available=False,
                updatable=updatable, asset=asset, reason=f"check failed: {exc}",
            )
        available = bool(latest and is_newer(latest))
        reason = None
        if not updatable:
            reason = "not a frozen binary" if not is_frozen() else "unknown platform"
        return UpdateInfo(
            current=__version__, latest=latest, available=available,
            updatable=updatable, asset=asset, reason=reason,
        )

    # ── apply ───────────────────────────────────────────────────────────────
    async def apply(self) -> dict:
        """Download + verify + swap the new binary, then restart. Returns a dict
        describing the action; on a successful restart the process exits and the
        caller never sees a normal return."""
        if self._applying:
            return {"ok": False, "error": "an update is already in progress"}
        info = await self.check()
        if not info.updatable:
            return {"ok": False, "error": info.reason or "not updatable"}
        if not info.available:
            return {"ok": False, "error": "already up to date", "current": info.current}
        assert info.asset
        self._applying = True
        try:
            new_path = await asyncio.to_thread(self._download_verified, info.asset)
            await asyncio.to_thread(self._swap, new_path)
        except Exception as exc:
            self._applying = False
            log.exception("update apply failed")
            return {"ok": False, "error": str(exc)}
        # Swap succeeded. Schedule the restart slightly later so this HTTP
        # response can flush to the browser before we go down.
        log.warning("update applied: %s -> %s; restarting", info.current, info.latest)
        asyncio.get_running_loop().call_later(0.5, self._restart)
        return {"ok": True, "from": info.current, "to": info.latest, "restarting": True}

    def _download_verified(self, asset: str) -> Path:
        tmpdir = Path(tempfile.mkdtemp(prefix="raspy-update-"))
        target = tmpdir / asset
        log.info("downloading update asset %s", asset)
        data = _fetch(self._asset_url(asset), timeout=120.0)
        target.write_bytes(data)

        # Verify against SHA256SUMS (published alongside the binaries).
        try:
            sums = _fetch(self._sums_url(), timeout=20.0).decode()
        except Exception as exc:
            raise RuntimeError(f"could not fetch SHA256SUMS: {exc}") from exc
        want = None
        for line in sums.splitlines():
            parts = line.split()
            if len(parts) == 2 and parts[1] == asset:
                want = parts[0].lower()
                break
        if not want:
            raise RuntimeError(f"no checksum entry for {asset}")
        got = hashlib.sha256(target.read_bytes()).hexdigest()
        if got != want:
            raise RuntimeError(f"checksum mismatch (got {got} want {want})")
        log.info("update asset verified")
        os.chmod(target, 0o755)
        return target

    def _swap(self, new_path: Path) -> None:
        """Replace the running binary with new_path. Cross-platform:

          POSIX: os.replace is atomic on the same filesystem, and replacing the
          file backing a running process is fine — the open inode stays valid
          until we exec the new one.

          Windows: a running .exe is locked and can't be overwritten. The standard
          dance is to RENAME the live exe aside, then move the new one into place;
          the renamed-aside file is deleted on next start.
        """
        dst = _self_path()
        # Move onto the destination's filesystem first so the final swap is atomic.
        staged = dst.with_name(dst.name + ".new")
        shutil.move(str(new_path), str(staged))
        os.chmod(staged, 0o755)

        if sys.platform.startswith("win"):
            old = dst.with_name(dst.name + ".old")
            try:
                if old.exists():
                    old.unlink()
            except OSError:
                pass
            os.replace(dst, old)        # move the locked live exe aside
            os.replace(staged, dst)     # put the new one in place
        else:
            os.replace(staged, dst)     # atomic same-fs replace

    def _restart(self) -> None:
        """Ask the OS service manager to restart us; fall back to in-place exec."""
        strat = self._settings.update_restart_strategy
        svc = self._settings.update_service_name
        try:
            if strat in ("auto", "service") and svc:
                if sys.platform.startswith("linux") and shutil.which("systemctl"):
                    # Works for both system and --user units; try user first.
                    for scope in (["--user"], []):
                        if subprocess.call(["systemctl", *scope, "restart", svc]) == 0:
                            return
                elif sys.platform == "darwin" and shutil.which("launchctl"):
                    subprocess.call(["launchctl", "kickstart", "-k", f"gui/{os.getuid()}/com.raspy.spine"])
                    return
                elif sys.platform.startswith("win"):
                    # The service manager restarts us after we exit (Restart=always
                    # equivalent is sc failure config); simplest is to just exit.
                    subprocess.Popen(["sc", "stop", svc])
                    os._exit(0)
        except Exception:
            log.exception("service restart failed; falling back to exec")
        # Fallback: re-exec the (now updated) binary in place.
        log.warning("re-exec %s", _self_path())
        try:
            os.execv(str(_self_path()), [str(_self_path()), "serve"])
        except Exception:
            log.exception("re-exec failed; exiting so the manager can restart us")
            os._exit(0)

    # ── periodic background check + notify ──────────────────────────────────
    def start(self) -> None:
        interval = self._settings.update_check_interval_s
        if interval <= 0:
            log.info("periodic update checks disabled")
            return
        self._task = asyncio.create_task(self._loop(interval))

    async def stop(self) -> None:
        if self._task:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
            self._task = None

    async def _loop(self, interval: int) -> None:
        # Small initial delay so startup isn't slowed by a network call.
        await asyncio.sleep(30)
        while True:
            try:
                info = await self.check()
                if info.available and info.latest and info.latest != self._notified_version:
                    await self._announce(info)
                    self._notified_version = info.latest
            except asyncio.CancelledError:
                raise
            except Exception:
                log.exception("periodic update check errored")
            await asyncio.sleep(interval)

    async def _announce(self, info: UpdateInfo) -> None:
        """Surface an available update through the existing channels."""
        # Live event for the in-app banner (no auth scoping — it's not secret).
        if self._events is not None:
            self._events.publish(
                "update.available",
                {"current": info.current, "latest": info.latest, "updatable": info.updatable},
            )
        # Persisted bell + optional Web Push, if a notifier is wired and this is
        # actually applicable (frozen binary).
        if self._notifications is not None and info.updatable:
            try:
                await self._notifications.notify(
                    title="Update available",
                    body=f"Raspy {info.latest} is ready (you're on {info.current}).",
                    source="updater",
                    url="/?update=1",
                    data={"latest": info.latest, "current": info.current},
                )
            except Exception:
                log.exception("update notification failed")

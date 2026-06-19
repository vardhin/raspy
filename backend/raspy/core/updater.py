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
    current_tag: str | None = None   # recorded installed tag (truth over __version__)

    def as_dict(self) -> dict:
        return {
            "current": self.current,
            "current_tag": self.current_tag,
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
        # An admin can toggle/retune the periodic check at runtime from the
        # Updates app; the override survives restarts in a small JSON file (the
        # layered config.toml is read-only at runtime). Absent => use settings.

    # ── installed-tag + binary cache ────────────────────────────────────────
    def _installed_tag_path(self) -> Path:
        return self._settings.data_dir / "installed_tag"

    def installed_tag(self) -> str | None:
        """The release tag we last swapped in (e.g. ``v0.5.2``). This is the
        truth about what's running — independent of the binary's baked-in
        ``__version__``, which is wrong whenever a release forgot to bump it.
        ``None`` if we've never self-updated (original install)."""
        try:
            t = self._installed_tag_path().read_text().strip()
            return t or None
        except FileNotFoundError:
            return None
        except Exception:
            return None

    def _record_installed_tag(self, tag: str) -> None:
        try:
            self._installed_tag_path().write_text(tag.strip())
        except Exception:
            log.exception("could not record installed tag %s", tag)

    def _cache_dir(self) -> Path:
        return self._settings.data_dir / "update_cache"

    def _cached_path(self, tag: str, asset: str) -> Path:
        """Where a verified binary for ``tag`` lives so a re-install is instant."""
        return self._cache_dir() / tag.lstrip("v") / asset

    def cached_tags(self) -> set[str]:
        """Tags whose binary for THIS platform is cached + verified on disk."""
        asset = _asset_name()
        if asset is None:
            return set()
        out: set[str] = set()
        root = self._cache_dir()
        if not root.is_dir():
            return out
        for sub in root.iterdir():
            if sub.is_dir() and (sub / asset).is_file():
                out.add(f"v{sub.name}")
        return out

    def delete_cached(self, tag: str) -> dict:
        tag = tag if tag.startswith("v") else f"v{tag}"
        d = self._cache_dir() / tag.lstrip("v")
        if not d.is_dir():
            return {"ok": False, "error": "not cached"}
        try:
            shutil.rmtree(d)
        except Exception as exc:
            return {"ok": False, "error": str(exc)}
        return {"ok": True, "tag": tag}

    def _emit_progress(self, stage: str, **extra) -> None:
        """Broadcast one update step so the UI can show exactly where we are.
        Stages: downloading, verifying, caching, swapping, restarting, error,
        done (cached)."""
        if self._events is not None:
            self._events.publish("update.progress", {"stage": stage, **extra})

    def _autocheck_path(self) -> Path:
        return self._settings.data_dir / "update_autocheck.json"

    def _autocheck_override(self) -> dict | None:
        try:
            return json.loads(self._autocheck_path().read_text())
        except FileNotFoundError:
            return None
        except Exception as exc:
            log.info("autocheck override unreadable: %s", exc)
            return None

    def autocheck(self) -> dict:
        """Current periodic-check config: the override if set, else the settings
        default. ``interval_s <= 0`` (or ``enabled=False``) means disabled."""
        ov = self._autocheck_override()
        if ov is not None:
            interval = int(ov.get("interval_s", self._settings.update_check_interval_s))
            enabled = bool(ov.get("enabled", interval > 0)) and interval > 0
        else:
            interval = int(self._settings.update_check_interval_s)
            enabled = interval > 0
        return {"enabled": enabled, "interval_s": interval}

    def set_autocheck(self, *, enabled: bool, interval_s: int) -> dict:
        interval_s = max(0, int(interval_s))
        self._autocheck_path().write_text(
            json.dumps({"enabled": bool(enabled), "interval_s": interval_s})
        )
        # Restart the loop so the new cadence (or disable) takes effect now.
        self.restart_loop()
        return self.autocheck()

    # ── release metadata ────────────────────────────────────────────────────
    def _latest_json_url(self) -> str:
        return f"https://github.com/{self._repo}/releases/latest/download/latest.json"

    def _asset_url(self, name: str, tag: str | None = None) -> str:
        """Asset download URL. ``tag=None`` uses the ``latest`` pointer; a tag
        targets that specific release (so an admin can install any version)."""
        ref = f"download/{tag}" if tag else "latest/download"
        return f"https://github.com/{self._repo}/releases/{ref}/{name}"

    def _sums_url(self, tag: str | None = None) -> str:
        ref = f"download/{tag}" if tag else "latest/download"
        return f"https://github.com/{self._repo}/releases/{ref}/SHA256SUMS"

    def _releases_api_url(self) -> str:
        return f"https://api.github.com/repos/{self._repo}/releases?per_page=30"

    async def list_releases(self) -> dict:
        """All published releases (newest first) with notes + whether this
        platform's asset is present, plus which one is currently installed.

        Powers the admin Updates app's version picker. Network + parse run in a
        thread so the event loop is never blocked.
        """
        asset = _asset_name()
        updatable = is_frozen() and asset is not None
        cur_tag = self.installed_tag()                 # what we actually swapped in
        cached = self.cached_tags()                    # tags ready for instant switch
        try:
            raw = await asyncio.to_thread(_fetch, self._releases_api_url())
            data = json.loads(raw.decode())
        except Exception as exc:
            log.info("release list failed: %s", exc)
            return {
                "current": __version__,
                "current_tag": cur_tag,
                "updatable": updatable,
                "asset": asset,
                "cached": sorted(cached),
                "releases": [],
                "reason": f"list failed: {exc}",
            }
        releases = []
        for rel in data:
            if rel.get("draft"):
                continue
            tag = str(rel.get("tag_name") or "")
            version = tag.lstrip("v")
            names = {a.get("name") for a in rel.get("assets") or []}
            is_cached = tag in cached
            # "current" is the tag we recorded at swap time when we have one (the
            # binary's baked-in __version__ can lie); else fall back to __version__.
            is_current = (tag == cur_tag) if cur_tag else (version == __version__)
            releases.append(
                {
                    "tag": tag,
                    "version": version,
                    "name": rel.get("name") or tag,
                    "notes": rel.get("body") or "",
                    "published_at": rel.get("published_at"),
                    "prerelease": bool(rel.get("prerelease")),
                    # Can we actually install this on the running platform?
                    "installable": bool(updatable and asset and asset in names),
                    # Cached binaries install instantly (no download).
                    "cached": is_cached,
                    "is_current": is_current,
                    "is_newer": bool(version and is_newer(version)),
                }
            )
        return {
            "current": __version__,
            "current_tag": cur_tag,
            "updatable": updatable,
            "asset": asset,
            "cached": sorted(cached),
            "releases": releases,
            "reason": None if updatable else (
                "not a frozen binary" if not is_frozen() else "unknown platform"
            ),
        }

    async def check(self) -> UpdateInfo:
        """Look up the latest release version. Network + parse run in a thread so
        the event loop is never blocked."""
        asset = _asset_name()
        updatable = is_frozen() and asset is not None
        cur_tag = self.installed_tag()
        # The local version to compare against: the recorded installed tag's
        # version when we have one (truth), else the binary's baked-in __version__.
        local = cur_tag.lstrip("v") if cur_tag else __version__
        try:
            raw = await asyncio.to_thread(_fetch, self._latest_json_url())
            meta = json.loads(raw.decode())
            latest = str(meta.get("version") or "").strip() or None
        except Exception as exc:  # network down, no release yet, etc.
            log.info("update check failed: %s", exc)
            return UpdateInfo(
                current=__version__, current_tag=cur_tag, latest=None,
                available=False, updatable=updatable, asset=asset,
                reason=f"check failed: {exc}",
            )
        available = bool(latest and is_newer(latest, local))
        reason = None
        if not updatable:
            reason = "not a frozen binary" if not is_frozen() else "unknown platform"
        return UpdateInfo(
            current=__version__, current_tag=cur_tag, latest=latest,
            available=available, updatable=updatable, asset=asset, reason=reason,
        )

    # ── apply ───────────────────────────────────────────────────────────────
    async def apply(self, target: str | None = None) -> dict:
        """Download + verify + swap a binary, then restart. ``target`` is a release
        tag (e.g. ``v0.4.0``) to install a *specific* version — up or down, so the
        admin can roll back; ``None`` installs the latest available update. Returns
        a dict describing the action; on a successful restart the process exits and
        the caller never sees a normal return."""
        if self._applying:
            return {"ok": False, "error": "an update is already in progress"}
        asset = _asset_name()
        if not (is_frozen() and asset):
            reason = "not a frozen binary" if not is_frozen() else "unknown platform"
            return {"ok": False, "error": reason}

        if target is None:
            # Latest-update path: keep the existing "are we behind?" guard.
            info = await self.check()
            if not info.available:
                return {"ok": False, "error": "already up to date", "current": info.current}
            to = info.latest
        else:
            # Specific-version path: install exactly this tag (allows downgrade).
            target = target if target.startswith("v") else f"v{target}"
            to = target.lstrip("v")
            # Compare against the recorded installed tag (truth) when we have one,
            # not the binary's baked-in __version__ (which can be wrong). This lets
            # you re-flash a tag whose version string collides with __version__.
            cur_tag = self.installed_tag()
            if cur_tag == target or (cur_tag is None and to == __version__):
                return {"ok": False, "error": "already on this version", "current": to}

        # We must know the concrete tag to cache/record by; resolve "latest".
        tag = target
        if tag is None:
            tag = f"v{to}" if to else None
        tag_label = tag or (f"v{to}" if to else "latest")

        self._applying = True
        try:
            cached = self._cached_path(tag_label, asset) if tag else None
            if cached is not None and cached.is_file():
                # Instant path: a verified binary for this tag is already on disk.
                self._emit_progress("cached_hit", tag=tag_label, to=to)
                bin_path = cached
            else:
                bin_path = await asyncio.to_thread(
                    self._fetch_verify_cache, asset, target, tag_label, to
                )
            self._emit_progress("swapping", tag=tag_label, to=to)
            await asyncio.to_thread(self._swap, bin_path)
            if tag:
                self._record_installed_tag(tag_label)
        except Exception as exc:
            self._applying = False
            log.exception("update apply failed")
            self._emit_progress("error", tag=tag_label, error=str(exc))
            return {"ok": False, "error": str(exc)}
        # Swap succeeded. Schedule the restart slightly later so this HTTP
        # response can flush to the browser before we go down.
        log.warning("update applied: %s -> %s; restarting", __version__, to)
        self._emit_progress("restarting", tag=tag_label, to=to)
        asyncio.get_running_loop().call_later(0.5, self._restart)
        return {"ok": True, "from": __version__, "to": to, "tag": tag_label, "restarting": True}

    def _fetch_verify_cache(
        self, asset: str, tag: str | None, tag_label: str, to: str | None
    ) -> Path:
        """Download → checksum-verify → store in the per-tag cache. Runs in a
        worker thread; emits progress at each step. Returns the cached binary
        path (kept on disk so a future re-install of this tag is instant)."""
        tmpdir = Path(tempfile.mkdtemp(prefix="raspy-update-"))
        tmp = tmpdir / asset
        try:
            self._emit_progress("downloading", tag=tag_label, to=to)
            log.info("downloading update asset %s (%s)", asset, tag or "latest")
            data = _fetch(self._asset_url(asset, tag), timeout=300.0)
            tmp.write_bytes(data)
            self._emit_progress(
                "downloaded", tag=tag_label, to=to, bytes=len(data)
            )

            self._emit_progress("verifying", tag=tag_label, to=to)
            try:
                sums = _fetch(self._sums_url(tag), timeout=20.0).decode()
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
            got = hashlib.sha256(tmp.read_bytes()).hexdigest()
            if got != want:
                raise RuntimeError(f"checksum mismatch (got {got} want {want})")
            log.info("update asset verified")

            # Store the verified binary in the cache so switching back is instant.
            self._emit_progress("caching", tag=tag_label, to=to)
            dest = self._cached_path(tag_label, asset)
            dest.parent.mkdir(parents=True, exist_ok=True)
            shutil.move(str(tmp), str(dest))
            os.chmod(dest, 0o755)
            self._emit_progress("verified", tag=tag_label, to=to)
            return dest
        finally:
            shutil.rmtree(tmpdir, ignore_errors=True)

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
        cfg = self.autocheck()
        if not cfg["enabled"]:
            log.info("periodic update checks disabled")
            return
        self._task = asyncio.create_task(self._loop(cfg["interval_s"]))

    def restart_loop(self) -> None:
        """Cancel the running loop and start one with the current autocheck
        config — called when an admin changes the toggle/interval at runtime."""
        if self._task and not self._task.done():
            self._task.cancel()
        self._task = None
        cfg = self.autocheck()
        if cfg["enabled"]:
            self._task = asyncio.create_task(self._loop(cfg["interval_s"]))
        else:
            log.info("periodic update checks disabled")

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

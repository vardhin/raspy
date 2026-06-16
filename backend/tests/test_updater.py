"""Self-updater: version comparison, platform asset naming, and the safe
behaviour on a non-frozen checkout (no swap, reports not-updatable)."""

from __future__ import annotations

import pytest

from raspy.core import updater
from raspy.config import Settings


def test_version_compare():
    assert updater.is_newer("0.2.0", "0.1.0")
    assert updater.is_newer("1.0.0", "0.9.9")
    assert updater.is_newer("0.1.10", "0.1.2")  # numeric, not lexical
    assert not updater.is_newer("0.1.0", "0.1.0")
    assert not updater.is_newer("0.1.0", "0.2.0")
    # Tolerates a leading v and malformed parts without raising.
    assert updater.is_newer("v1.2.0", "1.1.0")
    assert not updater.is_newer("garbage", "0.1.0")


def test_asset_name_for_known_platforms(monkeypatch):
    monkeypatch.setattr(updater.sys, "platform", "linux")
    monkeypatch.setattr(updater.platform, "machine", lambda: "aarch64")
    assert updater._asset_name() == "raspy-linux-arm64"

    monkeypatch.setattr(updater.sys, "platform", "darwin")
    monkeypatch.setattr(updater.platform, "machine", lambda: "x86_64")
    assert updater._asset_name() == "raspy-macos-x64"

    monkeypatch.setattr(updater.sys, "platform", "win32")
    monkeypatch.setattr(updater.platform, "machine", lambda: "amd64")
    assert updater._asset_name() == "raspy-windows-x64.exe"


@pytest.mark.asyncio
async def test_check_reports_not_updatable_on_source_checkout(monkeypatch):
    """A non-frozen checkout must never claim it can self-update, even if a newer
    release exists. We stub the network so the test is offline + deterministic."""
    up = Updater_for_test(monkeypatch, latest="9.9.9")
    info = await up.check()
    assert info.latest == "9.9.9"
    # available compares versions; but updatable is False because not frozen.
    assert info.updatable is False
    assert info.reason


@pytest.mark.asyncio
async def test_apply_refuses_when_not_frozen(monkeypatch):
    up = Updater_for_test(monkeypatch, latest="9.9.9")
    res = await up.apply()
    assert res["ok"] is False
    assert "updatable" in res["error"] or "frozen" in res["error"]


def Updater_for_test(monkeypatch, *, latest: str):
    """Build an Updater whose network calls are stubbed to a fixed latest.json."""
    settings = Settings()
    up = updater.Updater(settings=settings, events=None, notifications=None)

    import json

    def fake_fetch(url, timeout=20.0):
        if url.endswith("latest.json"):
            return json.dumps({"version": latest, "assets": {}}).encode()
        raise AssertionError(f"unexpected fetch {url}")

    monkeypatch.setattr(updater, "_fetch", fake_fetch)
    # Force not-frozen regardless of how tests are run.
    monkeypatch.setattr(updater, "is_frozen", lambda: False)
    return up

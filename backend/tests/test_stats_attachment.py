"""Stats attachment wiring: discovery, snapshot endpoint, and live ticks."""

from __future__ import annotations

import asyncio

import pytest

from raspy.attachments.stats import Stats, metrics
from raspy.core.events import EventBus


def test_stats_is_discovered_and_has_ui(client):
    h = client.get("/api/healthz").json()
    loaded = {a["id"] for a in h["attachments"]["loaded"]}
    assert "stats" in loaded

    manifest = client.get("/api/manifest").json()
    stats = next(a for a in manifest["attachments"] if a["id"] == "stats")
    assert stats["ui"]["type"] == "system_stats"
    assert stats["ui"]["source"] == "snapshot"


def test_snapshot_endpoint_shape(client):
    snap = client.get("/api/att/stats/snapshot").json()
    # Always-present keys regardless of platform.
    for key in ("time", "cpu_count", "storage", "memory", "uptime"):
        assert key in snap
    assert isinstance(snap["storage"], list)


@pytest.mark.asyncio
async def test_publish_loop_emits_tick(monkeypatch):
    """The background task should publish a stats.tick on its interval."""
    bus = EventBus()
    queue = bus.subscribe()

    att = Stats()

    # Make the snapshot trivial + deterministic and the interval tiny.
    monkeypatch.setattr(metrics, "snapshot", lambda: {"time": 1.0, "temp_c": 42.0})

    class Ctx:
        events = bus
        config: dict = {"interval": 0.01}

    await att.on_load(Ctx())  # type: ignore[arg-type]
    try:
        event = await asyncio.wait_for(queue.get(), timeout=2.0)
        assert event.topic == "stats.tick"
        assert event.payload["temp_c"] == 42.0
    finally:
        await att.on_shutdown()


@pytest.mark.asyncio
async def test_interval_is_clamped(monkeypatch):
    att = Stats()

    class Ctx:
        events = EventBus()
        config: dict = {"interval": 0.001}  # below the floor

    monkeypatch.setattr(metrics, "snapshot", lambda: {})
    await att.on_load(Ctx())  # type: ignore[arg-type]
    try:
        assert att._interval >= 1.0  # clamped to _MIN_INTERVAL
    finally:
        await att.on_shutdown()

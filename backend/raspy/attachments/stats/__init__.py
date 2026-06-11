"""System Stats attachment — live Raspberry Pi health & telemetry.

Surfaces the Pi's real vitals: SoC temperature, core voltage, throttle/under-
voltage state, CPU load, RAM, storage and uptime (see ``metrics.py``). A
background task samples on an interval and publishes ``stats.tick`` events over
the core WebSocket hub (plan/20 §6), so the dashboard updates live without
polling. ``GET /api/att/stats/snapshot`` gives a one-shot reading for first paint.

Capabilities (plan/20 §7): reads system telemetry (``/proc``, ``/sys``,
``vcgencmd``); no writes. Sample interval is config-tunable via
``[attachments.stats] interval = <seconds>``.
"""

from __future__ import annotations

import asyncio
import logging
from typing import Any

from fastapi import APIRouter

from raspy.core import ui
from raspy.core.contract import AttachmentContext, BaseAttachment
from raspy.core.events import EventBus

from . import metrics

log = logging.getLogger("raspy.stats")

_DEFAULT_INTERVAL = 3.0
_MIN_INTERVAL = 1.0


class Stats(BaseAttachment):
    id = "stats"
    title = "System"
    icon = "activity"
    version = "1.0.0"

    _task: asyncio.Task[None] | None = None
    _interval: float = _DEFAULT_INTERVAL
    _events: EventBus

    async def on_load(self, ctx: AttachmentContext) -> None:
        try:
            self._interval = max(_MIN_INTERVAL, float(ctx.config.get("interval", _DEFAULT_INTERVAL)))
        except (TypeError, ValueError):
            self._interval = _DEFAULT_INTERVAL
        # Hold the event bus directly so the publish loop doesn't depend on the
        # `self.ctx` property indirection.
        self._events = ctx.events
        # Prime the CPU delta so the first published tick already has a %.
        metrics.cpu_percent()
        self._task = asyncio.create_task(self._publish_loop(), name="stats.publish")

    async def on_shutdown(self) -> None:
        if self._task is not None:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
            self._task = None

    async def _publish_loop(self) -> None:
        """Sample + publish on the configured interval until cancelled."""
        while True:
            try:
                await asyncio.sleep(self._interval)
                # Metric reads touch the filesystem / spawn vcgencmd; keep them off
                # the event loop.
                snap = await asyncio.to_thread(metrics.snapshot)
                self._events.publish("stats.tick", snap)
            except asyncio.CancelledError:
                raise
            except Exception:  # noqa: BLE001 - a bad sample must not kill the loop
                log.exception("stats sample failed")

    def router(self) -> APIRouter:
        r = APIRouter()

        @r.get("/snapshot")
        async def snapshot() -> dict[str, Any]:
            return await asyncio.to_thread(metrics.snapshot)

        return r

    def ui(self) -> dict[str, Any]:
        return ui.system_stats(source="snapshot", title="System")


attachment = Stats()

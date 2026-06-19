"""Pomodoro attachment — a focus timer that goes fullscreen and notifies on finish.

Server-authoritative: the *session* (phase, when it ends, whether it's paused, and
the optional linked todo) lives in the DB, so the timer survives a page reload or a
device switch and any client can read/drive it. A durable background scheduler fires
a notification the moment a running phase's end time arrives — even if no client is
open. The frontend ships a dedicated fullscreen component (Tier-2), like calendar /
notes, because a beautiful animated timer is beyond the declarative vocabulary.
"""

from __future__ import annotations

import asyncio
import logging
import time
from typing import Any

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from raspy.core.contract import AttachmentContext, BaseAttachment
from raspy.core import ui


log = logging.getLogger("raspy.pomodoro")

_SCHED_IDLE_S = 30.0  # how long the finish-watcher sleeps when nothing is running

# Phase ladder: a "work" phase, then a "break". Durations are per-account settings.
_PHASE_WORK = "work"
_PHASE_BREAK = "break"

_DEFAULT_WORK_MIN = 25
_DEFAULT_BREAK_MIN = 5
_MIN_MIN = 1
_MAX_MIN = 180


class Settings(BaseModel):
    work_minutes: int = Field(default=_DEFAULT_WORK_MIN, ge=_MIN_MIN, le=_MAX_MIN)
    break_minutes: int = Field(default=_DEFAULT_BREAK_MIN, ge=_MIN_MIN, le=_MAX_MIN)


class StartBody(BaseModel):
    phase: str = Field(default=_PHASE_WORK)
    # Optional linked todo, so the timer can show what you're focusing on.
    todo_id: int | None = None
    todo_title: str | None = Field(default=None, max_length=500)


class Pomodoro(BaseAttachment):
    id = "pomodoro"
    title = "Pomodoro"
    icon = "clock4"
    version = "1.0.0"

    _scheduler: asyncio.Task[None] | None = None
    _wake: asyncio.Event

    # --- lifecycle ----------------------------------------------------------

    async def on_load(self, ctx: AttachmentContext) -> None:
        self._ready: set[str] = set()
        self._wake = asyncio.Event()
        self._scheduler = asyncio.create_task(self._finish_loop())

    async def on_shutdown(self) -> None:
        if self._scheduler is not None:
            self._scheduler.cancel()
            try:
                await self._scheduler
            except asyncio.CancelledError:
                pass
            self._scheduler = None

    async def _ensure(self) -> str:
        """Create this account's single-row session table on first touch.

        One row per account (id = 1). ``running`` is 1 while a phase is counting
        down, ``ends_at`` is its finish time, ``remaining`` holds the seconds left
        when paused, ``notified`` guards the one-shot finish notification.
        """
        t = self.db.table("session")
        if t not in self._ready:
            await self.db.execute(
                f"""
                CREATE TABLE IF NOT EXISTS {t} (
                    id          INTEGER PRIMARY KEY CHECK (id = 1),
                    phase       TEXT    NOT NULL DEFAULT 'work',
                    running     INTEGER NOT NULL DEFAULT 0,
                    ends_at     REAL,
                    remaining   REAL,
                    duration    REAL    NOT NULL DEFAULT 0,
                    notified    INTEGER NOT NULL DEFAULT 0,
                    todo_id     INTEGER,
                    todo_title  TEXT,
                    work_min    INTEGER NOT NULL DEFAULT 25,
                    break_min   INTEGER NOT NULL DEFAULT 5,
                    updated     REAL    NOT NULL DEFAULT 0
                )
                """
            )
            row = await self.db.fetch_one(f"SELECT id FROM {t} WHERE id = 1")
            if row is None:
                await self.db.execute(
                    f"INSERT INTO {t} (id, updated) VALUES (1, ?)", (time.time(),)
                )
            self._ready.add(t)
        return t

    async def _state(self) -> dict[str, Any]:
        t = await self._ensure()
        row = await self.db.fetch_one(f"SELECT * FROM {t} WHERE id = 1")
        return _to_api(row or {})

    # --- API ----------------------------------------------------------------

    def router(self) -> APIRouter:
        r = APIRouter()

        @r.get("/state")
        async def get_state() -> dict[str, Any]:
            return await self._state()

        @r.get("/settings")
        async def get_settings() -> dict[str, Any]:
            t = await self._ensure()
            row = await self.db.fetch_one(
                f"SELECT work_min, break_min FROM {t} WHERE id = 1"
            )
            return {
                "work_minutes": int((row or {}).get("work_min", _DEFAULT_WORK_MIN)),
                "break_minutes": int((row or {}).get("break_min", _DEFAULT_BREAK_MIN)),
            }

        @r.put("/settings")
        async def put_settings(body: Settings) -> dict[str, Any]:
            t = await self._ensure()
            await self.db.execute(
                f"UPDATE {t} SET work_min = ?, break_min = ?, updated = ? WHERE id = 1",
                (body.work_minutes, body.break_minutes, time.time()),
            )
            self.events.publish("pomodoro.updated", await self._state())
            return {
                "work_minutes": body.work_minutes,
                "break_minutes": body.break_minutes,
            }

        @r.post("/start")
        async def start(body: StartBody) -> dict[str, Any]:
            t = await self._ensure()
            if body.phase not in (_PHASE_WORK, _PHASE_BREAK):
                raise HTTPException(400, "phase must be 'work' or 'break'")
            settings = await self.db.fetch_one(
                f"SELECT work_min, break_min FROM {t} WHERE id = 1"
            )
            mins = (
                int(settings["work_min"])
                if body.phase == _PHASE_WORK
                else int(settings["break_min"])
            )
            now = time.time()
            duration = mins * 60
            await self.db.execute(
                f"UPDATE {t} SET phase = ?, running = 1, ends_at = ?, remaining = NULL, "
                f"duration = ?, notified = 0, todo_id = ?, todo_title = ?, updated = ? "
                f"WHERE id = 1",
                (
                    body.phase,
                    now + duration,
                    duration,
                    body.todo_id,
                    (body.todo_title or "").strip() or None,
                    now,
                ),
            )
            state = await self._state()
            self.events.publish("pomodoro.updated", state)
            self._wake.set()  # the finish watcher should pick up the new end time
            return state

        @r.post("/pause")
        async def pause() -> dict[str, Any]:
            t = await self._ensure()
            row = await self.db.fetch_one(f"SELECT * FROM {t} WHERE id = 1")
            if row and row["running"] and row["ends_at"] is not None:
                remaining = max(0.0, float(row["ends_at"]) - time.time())
                await self.db.execute(
                    f"UPDATE {t} SET running = 0, remaining = ?, ends_at = NULL, "
                    f"updated = ? WHERE id = 1",
                    (remaining, time.time()),
                )
            state = await self._state()
            self.events.publish("pomodoro.updated", state)
            return state

        @r.post("/resume")
        async def resume() -> dict[str, Any]:
            t = await self._ensure()
            row = await self.db.fetch_one(f"SELECT * FROM {t} WHERE id = 1")
            if row and not row["running"] and row["remaining"] is not None:
                ends_at = time.time() + float(row["remaining"])
                await self.db.execute(
                    f"UPDATE {t} SET running = 1, ends_at = ?, remaining = NULL, "
                    f"updated = ? WHERE id = 1",
                    (ends_at, time.time()),
                )
            state = await self._state()
            self.events.publish("pomodoro.updated", state)
            self._wake.set()
            return state

        @r.post("/reset")
        async def reset() -> dict[str, Any]:
            t = await self._ensure()
            await self.db.execute(
                f"UPDATE {t} SET running = 0, ends_at = NULL, remaining = NULL, "
                f"duration = 0, notified = 0, todo_id = NULL, todo_title = NULL, "
                f"updated = ? WHERE id = 1",
                (time.time(),),
            )
            state = await self._state()
            self.events.publish("pomodoro.updated", state)
            return state

        return r

    # --- finish scheduler ----------------------------------------------------

    async def _finish_loop(self) -> None:
        """Notify when a running phase ends; sleep until the next end time.

        Durable: reads the DB each pass, so a timer started before a restart still
        finishes. Wakes early when a session starts/resumes (via ``_wake``).
        Iterates every account in its own isolated scope.
        """
        while True:
            sleep = _SCHED_IDLE_S
            try:
                for acct in await self.ctx.list_accounts():
                    is_admin = (acct.get("role") or "admin") == "admin"
                    with self.ctx.account_scope(acct["username"], is_admin=is_admin):
                        try:
                            acct_sleep = await self._finish_pass()
                        except Exception:  # noqa: BLE001 - one account must not stall the rest
                            log.exception("pomodoro finish pass failed for an account")
                            acct_sleep = _SCHED_IDLE_S
                    sleep = min(sleep, acct_sleep)
            except asyncio.CancelledError:
                raise
            except Exception:  # noqa: BLE001 - never let the loop die
                log.exception("pomodoro finish loop iteration failed")
                sleep = _SCHED_IDLE_S
            try:
                await asyncio.wait_for(self._wake.wait(), timeout=sleep)
            except asyncio.TimeoutError:
                pass
            self._wake.clear()

    async def _finish_pass(self) -> float:
        t = await self._ensure()
        now = time.time()
        row = await self.db.fetch_one(
            f"SELECT * FROM {t} WHERE id = 1 AND running = 1 AND notified = 0 "
            f"AND ends_at IS NOT NULL"
        )
        if row is None:
            return _SCHED_IDLE_S
        ends_at = float(row["ends_at"])
        if ends_at <= now:
            await self._fire_finish(row)
            return _SCHED_IDLE_S
        return max(1.0, min(_SCHED_IDLE_S, ends_at - now))

    async def _fire_finish(self, row: dict[str, Any]) -> None:
        t = self.db.table("session")
        phase = row["phase"]
        if phase == _PHASE_WORK:
            title = "Focus session complete"
            body = "Nice work — time for a break."
            if row.get("todo_title"):
                body = f"Finished focusing on “{row['todo_title']}”. Take a break."
        else:
            title = "Break over"
            body = "Back to it — start your next focus session."
        await self.notify(title, body, icon="clock4", url="/a/pomodoro")
        # Mark the phase done so it stops counting and won't re-notify. The client
        # decides whether to auto-start the next phase.
        await self.db.execute(
            f"UPDATE {t} SET running = 0, notified = 1, ends_at = NULL, "
            f"remaining = 0, updated = ? WHERE id = 1",
            (time.time(),),
        )
        self.events.publish("pomodoro.finished", await self._state())

    # --- UI -----------------------------------------------------------------

    def ui(self) -> dict[str, Any]:
        return ui.view(title="Pomodoro", children=[ui.pomodoro()])


def _to_api(row: dict[str, Any]) -> dict[str, Any]:
    running = bool(row.get("running"))
    ends_at = row.get("ends_at")
    remaining_col = row.get("remaining")
    # Seconds left right now: from ends_at when running, from the stored remaining
    # when paused. The client also runs its own ticking clock from this snapshot.
    if running and ends_at is not None:
        remaining = max(0.0, float(ends_at) - time.time())
    elif remaining_col is not None:
        remaining = max(0.0, float(remaining_col))
    else:
        remaining = 0.0
    return {
        "phase": row.get("phase", _PHASE_WORK),
        "running": running,
        "ends_at": ends_at,
        "remaining": remaining,
        "duration": float(row.get("duration") or 0),
        "notified": bool(row.get("notified")),
        "todo_id": row.get("todo_id"),
        "todo_title": row.get("todo_title"),
        "work_minutes": int(row.get("work_min", _DEFAULT_WORK_MIN)),
        "break_minutes": int(row.get("break_min", _DEFAULT_BREAK_MIN)),
    }


attachment = Pomodoro()

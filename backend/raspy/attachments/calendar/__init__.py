"""Calendar — a hybrid memory journal + planner on a continuous day timeline.

Every calendar day in the viewed range gets a card. Days with one or more *entries*
show them (photo carousel + title + description + date). Days with no entry show a
deterministic **placeholder**: the same image + quote the ``vibe`` app cached for
that date (so the calendar's empty state is the daily vibe, shared, offline-ish).

Entries can be created for past, present, or future dates. A future entry may carry
a ``remind_at`` timestamp; a durable background scheduler fires a notification at
that time via the core notification service — surviving restarts (it reads the DB on
boot, unlike the core's in-memory ``notify_later``).

Photos are stored as content-addressed blobs in the attachment data dir (SHA-256 of
the bytes), streamed back with their real mime type. They are NOT end-to-end
encrypted (these are journal photos the server legitimately serves) — that's the
deliberate difference from the zero-knowledge ``vault``.
"""

from __future__ import annotations

import asyncio
import datetime as dt
import hashlib
import logging
import time
from pathlib import Path
from typing import Any

from fastapi import APIRouter, HTTPException, Query, Response, UploadFile
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field

from raspy.core import ui
from raspy.core.contract import AttachmentContext, BaseAttachment

from .._dailyvibe import DailyVibeStore

log = logging.getLogger("raspy.calendar")

_MAX_IMAGE = 25 * 1024 * 1024  # 25 MiB per photo
_ALLOWED_IMAGE = {"image/jpeg", "image/png", "image/webp", "image/gif", "image/avif"}
_MAX_RANGE_DAYS = 400  # guard the range endpoint
_SCHED_IDLE_S = 60.0  # how long the reminder loop sleeps when nothing is due


def _valid_date(s: str) -> str:
    try:
        dt.date.fromisoformat(s)
    except (ValueError, TypeError) as exc:
        raise HTTPException(400, "invalid date (expected YYYY-MM-DD)") from exc
    return s


def _hash_bytes(b: bytes) -> str:
    return hashlib.sha256(b).hexdigest()


class EntryCreate(BaseModel):
    date: str = Field(min_length=10, max_length=10)
    title: str = Field(default="", max_length=200)
    description: str = Field(default="", max_length=10_000)
    remind_at: float | None = Field(default=None)  # unix ts; future => schedules


class EntryUpdate(BaseModel):
    date: str | None = Field(default=None, min_length=10, max_length=10)
    title: str | None = Field(default=None, max_length=200)
    description: str | None = Field(default=None, max_length=10_000)
    remind_at: float | None = Field(default=None)
    clear_remind: bool = Field(default=False)


class Calendar(BaseAttachment):
    id = "calendar"
    title = "Calendar"
    icon = "calendar"
    version = "1.0.0"

    _blob_dir: Path
    _vibe: DailyVibeStore
    _scheduler: asyncio.Task[None] | None = None
    _wake: asyncio.Event

    async def on_load(self, ctx: AttachmentContext) -> None:
        self._blob_dir = ctx.data_dir / "photos"
        self._blob_dir.mkdir(parents=True, exist_ok=True)
        # Share the vibe app's cache so an empty day shows that day's vibe.
        # data_dir is data/att/calendar; the sibling vibe cache is data/att/vibe/cache.
        vibe_cache = ctx.data_dir.parent / "vibe" / "cache"
        self._vibe = DailyVibeStore(vibe_cache)
        self._wake = asyncio.Event()

        e = self.db.table("entries")
        img = self.db.table("images")
        await self.db.execute(
            f"""
            CREATE TABLE IF NOT EXISTS {e} (
                id          INTEGER PRIMARY KEY AUTOINCREMENT,
                date        TEXT NOT NULL,
                title       TEXT NOT NULL DEFAULT '',
                description TEXT NOT NULL DEFAULT '',
                remind_at   REAL,
                notified    INTEGER NOT NULL DEFAULT 0,
                created     REAL NOT NULL,
                updated     REAL NOT NULL
            )
            """
        )
        await self.db.execute(f"CREATE INDEX IF NOT EXISTS {e}_date ON {e} (date)")
        await self.db.execute(
            f"CREATE INDEX IF NOT EXISTS {e}_due ON {e} (notified, remind_at)"
        )
        await self.db.execute(
            f"""
            CREATE TABLE IF NOT EXISTS {img} (
                id       INTEGER PRIMARY KEY AUTOINCREMENT,
                entry_id INTEGER NOT NULL,
                hash     TEXT NOT NULL,
                mime     TEXT NOT NULL,
                ord      INTEGER NOT NULL DEFAULT 0,
                created  REAL NOT NULL
            )
            """
        )
        await self.db.execute(
            f"CREATE INDEX IF NOT EXISTS {img}_entry ON {img} (entry_id, ord)"
        )
        self._scheduler = asyncio.create_task(self._reminder_loop())

    async def on_shutdown(self) -> None:
        if self._scheduler is not None:
            self._scheduler.cancel()
            try:
                await self._scheduler
            except asyncio.CancelledError:
                pass
            self._scheduler = None

    # --- blob helpers --------------------------------------------------------

    def _blob_path(self, h: str) -> Path:
        sub = self._blob_dir / h[:2]
        sub.mkdir(parents=True, exist_ok=True)
        return sub / h

    async def _images_for(self, entry_id: int) -> list[dict[str, Any]]:
        img = self.db.table("images")
        rows = await self.db.fetch_all(
            f"SELECT id, hash, mime, ord FROM {img} WHERE entry_id = ? ORDER BY ord, id",
            (entry_id,),
        )
        for row in rows:
            row["url"] = f"image/{row['hash']}"
        return rows

    async def _entry_api(self, row: dict[str, Any]) -> dict[str, Any]:
        return {
            "id": row["id"],
            "date": row["date"],
            "title": row["title"],
            "description": row["description"],
            "remind_at": row["remind_at"],
            "notified": bool(row["notified"]),
            "created": row["created"],
            "updated": row["updated"],
            "images": await self._images_for(row["id"]),
        }

    # --- reminder scheduler --------------------------------------------------

    async def _reminder_loop(self) -> None:
        """Fire notifications for due entries; sleep until the next is due.

        Durable: reads the DB each pass, so reminders set before a restart still
        fire. Wakes early when a new reminder is created/changed (via ``_wake``).
        """
        e = self.db.table("entries")
        while True:
            try:
                now = time.time()
                due = await self.db.fetch_all(
                    f"SELECT * FROM {e} WHERE notified = 0 AND remind_at IS NOT NULL "
                    f"AND remind_at <= ? ORDER BY remind_at LIMIT 50",
                    (now,),
                )
                for row in due:
                    await self._fire_reminder(row)

                nxt = await self.db.fetch_one(
                    f"SELECT MIN(remind_at) AS t FROM {e} "
                    f"WHERE notified = 0 AND remind_at IS NOT NULL"
                )
                next_due = (nxt or {}).get("t")
                if next_due is None:
                    sleep = _SCHED_IDLE_S
                else:
                    sleep = max(1.0, min(_SCHED_IDLE_S, next_due - time.time()))
            except asyncio.CancelledError:
                raise
            except Exception:  # noqa: BLE001 - never let the loop die
                log.exception("calendar reminder loop iteration failed")
                sleep = _SCHED_IDLE_S
            try:
                await asyncio.wait_for(self._wake.wait(), timeout=sleep)
            except asyncio.TimeoutError:
                pass
            self._wake.clear()

    async def _fire_reminder(self, row: dict[str, Any]) -> None:
        e = self.db.table("entries")
        title = row["title"] or "Calendar reminder"
        body = (row["description"] or "")[:200] or f"Your entry for {row['date']}."
        await self.notify(
            title,
            body,
            url=f"/a/calendar?date={row['date']}",
            data={"entry_id": row["id"], "date": row["date"]},
        )
        await self.db.execute(
            f"UPDATE {e} SET notified = 1 WHERE id = ?", (row["id"],)
        )

    # --- API -----------------------------------------------------------------

    def router(self) -> APIRouter:
        r = APIRouter()
        e = self.db.table("entries")
        img = self.db.table("images")

        async def _row(entry_id: int) -> dict[str, Any]:
            row = await self.db.fetch_one(f"SELECT * FROM {e} WHERE id = ?", (entry_id,))
            if row is None:
                raise HTTPException(404, "entry not found")
            return row

        @r.get("/range")
        async def range_(
            from_: str = Query(alias="from"),
            to: str = Query(...),
        ) -> list[dict[str, Any]]:
            """One object per day in [from, to]. Days with entries carry them;
            empty days carry a placeholder (the shared daily vibe). The client
            calls ``/range?from=YYYY-MM-DD&to=YYYY-MM-DD``."""
            d0 = dt.date.fromisoformat(_valid_date(from_))
            d1 = dt.date.fromisoformat(_valid_date(to))
            if d1 < d0:
                d0, d1 = d1, d0
            span = (d1 - d0).days + 1
            if span > _MAX_RANGE_DAYS:
                raise HTTPException(400, f"range too large (max {_MAX_RANGE_DAYS} days)")

            rows = await self.db.fetch_all(
                f"SELECT * FROM {e} WHERE date >= ? AND date <= ? "
                f"ORDER BY date, created",
                (d0.isoformat(), d1.isoformat()),
            )
            by_date: dict[str, list[dict[str, Any]]] = {}
            for row in rows:
                by_date.setdefault(row["date"], []).append(await self._entry_api(row))

            out: list[dict[str, Any]] = []
            for i in range(span):
                day = d0 + dt.timedelta(days=i)
                ds = day.isoformat()
                entries = by_date.get(ds, [])
                item: dict[str, Any] = {
                    "date": ds,
                    "weekday": day.weekday(),  # 0 = Monday … 6 = Sunday
                    "entries": entries,
                }
                if not entries:
                    item["placeholder"] = await self._placeholder(ds)
                out.append(item)
            return out

        @r.get("/placeholder/{date}")
        async def placeholder(date: str) -> dict[str, Any]:
            return await self._placeholder(_valid_date(date))

        @r.get("/entries/{entry_id}")
        async def get_entry(entry_id: int) -> dict[str, Any]:
            return await self._entry_api(await _row(entry_id))

        @r.post("/entries", status_code=201)
        async def create_entry(body: EntryCreate) -> dict[str, Any]:
            _valid_date(body.date)
            now = time.time()
            new_id = await self.db.execute_insert(
                f"INSERT INTO {e} (date, title, description, remind_at, notified, "
                f"created, updated) VALUES (?, ?, ?, ?, 0, ?, ?)",
                (body.date, body.title.strip(), body.description, body.remind_at, now, now),
            )
            self._wake.set()  # a new reminder may be sooner than the current sleep
            self.events.publish("calendar.changed", {"date": body.date})
            return await self._entry_api(await _row(new_id))

        @r.patch("/entries/{entry_id}")
        async def update_entry(entry_id: int, body: EntryUpdate) -> dict[str, Any]:
            await _row(entry_id)
            sets: list[str] = []
            params: list[Any] = []
            if body.date is not None:
                sets.append("date = ?")
                params.append(_valid_date(body.date))
            if body.title is not None:
                sets.append("title = ?")
                params.append(body.title.strip())
            if body.description is not None:
                sets.append("description = ?")
                params.append(body.description)
            if body.clear_remind:
                sets.append("remind_at = NULL")
                sets.append("notified = 0")
            elif body.remind_at is not None:
                sets.append("remind_at = ?")
                params.append(body.remind_at)
                sets.append("notified = 0")  # re-arm if rescheduled
            if sets:
                sets.append("updated = ?")
                params.append(time.time())
                params.append(entry_id)
                await self.db.execute(
                    f"UPDATE {e} SET {', '.join(sets)} WHERE id = ?", params
                )
                self._wake.set()
            row = await _row(entry_id)
            self.events.publish("calendar.changed", {"date": row["date"]})
            return await self._entry_api(row)

        @r.delete("/entries/{entry_id}", status_code=204)
        async def delete_entry(entry_id: int) -> None:
            row = await _row(entry_id)
            imgs = await self.db.fetch_all(
                f"SELECT hash FROM {img} WHERE entry_id = ?", (entry_id,)
            )
            await self.db.execute(f"DELETE FROM {img} WHERE entry_id = ?", (entry_id,))
            await self.db.execute(f"DELETE FROM {e} WHERE id = ?", (entry_id,))
            # GC blobs no longer referenced by any image row.
            for row_img in imgs:
                await self._gc_blob(row_img["hash"])
            self.events.publish("calendar.changed", {"date": row["date"]})

        # --- images ---------------------------------------------------------

        @r.post("/entries/{entry_id}/images", status_code=201)
        async def add_image(entry_id: int, file: UploadFile) -> dict[str, Any]:
            await _row(entry_id)
            mime = (file.content_type or "").split(";")[0].strip().lower()
            if mime not in _ALLOWED_IMAGE:
                raise HTTPException(415, f"unsupported image type: {mime or 'unknown'}")
            data = await file.read()
            if not data:
                raise HTTPException(400, "empty file")
            if len(data) > _MAX_IMAGE:
                raise HTTPException(413, "image too large")
            h = _hash_bytes(data)
            path = self._blob_path(h)
            if not path.is_file():
                tmp = path.with_suffix(".tmp")
                tmp.write_bytes(data)
                tmp.replace(path)
            nxt = await self.db.fetch_one(
                f"SELECT COALESCE(MAX(ord), -1) + 1 AS n FROM {img} WHERE entry_id = ?",
                (entry_id,),
            )
            ord_ = int((nxt or {}).get("n", 0))
            img_id = await self.db.execute_insert(
                f"INSERT INTO {img} (entry_id, hash, mime, ord, created) "
                f"VALUES (?, ?, ?, ?, ?)",
                (entry_id, h, mime, ord_, time.time()),
            )
            row = await _row(entry_id)
            self.events.publish("calendar.changed", {"date": row["date"]})
            return {"id": img_id, "hash": h, "mime": mime, "ord": ord_, "url": f"image/{h}"}

        @r.delete("/images/{image_id}", status_code=204)
        async def delete_image(image_id: int) -> None:
            row = await self.db.fetch_one(
                f"SELECT entry_id, hash FROM {img} WHERE id = ?", (image_id,)
            )
            if row is None:
                raise HTTPException(404, "image not found")
            await self.db.execute(f"DELETE FROM {img} WHERE id = ?", (image_id,))
            await self._gc_blob(row["hash"])
            entry = await self.db.fetch_one(
                f"SELECT date FROM {e} WHERE id = ?", (row["entry_id"],)
            )
            if entry:
                self.events.publish("calendar.changed", {"date": entry["date"]})

        @r.patch("/entries/{entry_id}/images/order", status_code=204)
        async def reorder_images(entry_id: int, body: dict[str, list[int]]) -> None:
            """Body: {"order": [imageId, imageId, …]} in the desired display order."""
            await _row(entry_id)
            order = body.get("order", [])
            for i, image_id in enumerate(order):
                await self.db.execute(
                    f"UPDATE {img} SET ord = ? WHERE id = ? AND entry_id = ?",
                    (i, image_id, entry_id),
                )
            row = await _row(entry_id)
            self.events.publish("calendar.changed", {"date": row["date"]})

        @r.get("/image/{blob_hash}")
        async def get_image(blob_hash: str) -> Response:
            if not all(c in "0123456789abcdef" for c in blob_hash) or len(blob_hash) != 64:
                raise HTTPException(400, "invalid hash")
            path = self._blob_path(blob_hash)
            if not path.is_file():
                raise HTTPException(404, "image not found")
            row = await self.db.fetch_one(
                f"SELECT mime FROM {img} WHERE hash = ? LIMIT 1", (blob_hash,)
            )
            mime = (row or {}).get("mime", "application/octet-stream")
            return FileResponse(path, media_type=mime)

        return r

    async def _placeholder(self, date: str) -> dict[str, Any]:
        vibe = await asyncio.to_thread(self._vibe.ensure, date)
        return {
            "image_url": f"/api/att/vibe/image/{date}",
            "quote": vibe.quote,
            "author": vibe.author,
            "accent": vibe.accent,
        }

    async def _gc_blob(self, h: str) -> None:
        img = self.db.table("images")
        still = await self.db.fetch_one(
            f"SELECT 1 AS x FROM {img} WHERE hash = ? LIMIT 1", (h,)
        )
        if still is None:
            self._blob_path(h).unlink(missing_ok=True)

    def ui(self) -> dict[str, Any]:
        return ui.view(title="Calendar", children=[ui.calendar()])


attachment = Calendar()

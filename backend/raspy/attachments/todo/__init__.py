"""Todo attachment — persistent task list with live updates.

Demonstrates the full contract: namespaced storage, CRUD API, declarative UI, and
WebSocket events so a change on one device shows up live on another.
See plan/60-roadmap.md Milestone 1.
"""

from __future__ import annotations

import asyncio
import datetime as dt
import logging
import time
from typing import Any

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field, field_validator

from raspy.core.contract import AttachmentContext, BaseAttachment
from raspy.core import ui


log = logging.getLogger("raspy.todo")

# Priority is a small fixed ladder: 0 none, 1 low, 2 medium, 3 high. The list
# sorts incomplete items by priority (high first), so it doubles as an ordering.
PRIORITY_MIN = 0
PRIORITY_MAX = 3

_SCHED_IDLE_S = 60.0  # how long the due-date loop sleeps when nothing is due


def _coerce_priority(v: Any) -> Any:
    # The declarative select sends its value as a string (and an empty string
    # after the create-form auto-clears it); normalise both to a clamped int.
    if v is None or v == "":
        return 0
    try:
        n = int(v)
    except (TypeError, ValueError):
        return 0
    return max(PRIORITY_MIN, min(PRIORITY_MAX, n))


def _coerce_due(v: Any) -> Any:
    # The declarative date input sends "" when cleared; treat that as "no due".
    if v == "":
        return None
    return v


def _due_at(date: str | None) -> float | None:
    """Local-midnight unix ts for a YYYY-MM-DD date (when its reminder fires)."""
    if not date:
        return None
    try:
        d = dt.date.fromisoformat(date)
    except (ValueError, TypeError) as exc:
        raise HTTPException(400, "invalid due date (expected YYYY-MM-DD)") from exc
    return dt.datetime(d.year, d.month, d.day).timestamp()


class TodoCreate(BaseModel):
    title: str = Field(min_length=1, max_length=500)
    priority: int = 0
    # A YYYY-MM-DD due date; when that day arrives a notification fires once.
    due: str | None = Field(default=None, min_length=10, max_length=10)

    _norm_priority = field_validator("priority", mode="before")(_coerce_priority)
    _norm_due = field_validator("due", mode="before")(_coerce_due)


class TodoUpdate(BaseModel):
    title: str | None = Field(default=None, min_length=1, max_length=500)
    done: bool | None = None
    priority: int | None = Field(default=None, ge=PRIORITY_MIN, le=PRIORITY_MAX)
    due: str | None = Field(default=None, min_length=10, max_length=10)
    clear_due: bool = False

    _norm_due = field_validator("due", mode="before")(_coerce_due)


class TodoReorder(BaseModel):
    # The desired top-to-bottom order of item ids after a drag. Bounded so a
    # malformed client can't ask us to rewrite an unbounded number of rows.
    order: list[int] = Field(max_length=10_000)


class Todo(BaseAttachment):
    id = "todo"
    title = "Todo"
    icon = "check-square"
    version = "1.0.0"

    # --- lifecycle ----------------------------------------------------------

    _scheduler: asyncio.Task[None] | None = None
    _wake: asyncio.Event

    async def on_load(self, ctx: AttachmentContext) -> None:
        # Per-account tables are created lazily in _ensure() — the table name
        # depends on the requesting account (isolation), unknown at load time.
        self._ready: set[str] = set()
        self._wake = asyncio.Event()
        # Durable due-date scheduler: fires a notification when a todo's day
        # arrives. Reads the DB each pass so reminders survive a restart.
        self._scheduler = asyncio.create_task(self._due_loop())

    async def on_shutdown(self) -> None:
        if self._scheduler is not None:
            self._scheduler.cancel()
            try:
                await self._scheduler
            except asyncio.CancelledError:
                pass
            self._scheduler = None

    async def _ensure(self) -> str:
        """Create this account's items table on first touch; return its name."""
        t = self.db.table("items")
        if t not in self._ready:
            await self.db.execute(
                f"""
                CREATE TABLE IF NOT EXISTS {t} (
                    id        INTEGER PRIMARY KEY AUTOINCREMENT,
                    title     TEXT    NOT NULL,
                    done      INTEGER NOT NULL DEFAULT 0,
                    priority  INTEGER NOT NULL DEFAULT 0,
                    due       TEXT,
                    due_at    REAL,
                    notified  INTEGER NOT NULL DEFAULT 0,
                    position  INTEGER NOT NULL DEFAULT 0,
                    created   REAL    NOT NULL,
                    updated   REAL    NOT NULL
                )
                """
            )
            # Migrate tables created before these columns existed (CREATE IF NOT
            # EXISTS above is a no-op for them, so add any missing column).
            cols = {c["name"] for c in await self.db.fetch_all(f"PRAGMA table_info({t})")}
            for name, decl in (
                ("priority", "INTEGER NOT NULL DEFAULT 0"),
                ("due", "TEXT"),
                ("due_at", "REAL"),
                ("notified", "INTEGER NOT NULL DEFAULT 0"),
            ):
                if name not in cols:
                    await self.db.execute(f"ALTER TABLE {t} ADD COLUMN {name} {decl}")
            await self.db.execute(
                f"CREATE INDEX IF NOT EXISTS {t}_due "
                f"ON {t} (notified, done, due_at)"
            )
            self._ready.add(t)
        return t

    # --- API ----------------------------------------------------------------

    def router(self) -> APIRouter:
        r = APIRouter()

        async def _row(item_id: int) -> dict[str, Any]:
            t = await self._ensure()
            row = await self.db.fetch_one(f"SELECT * FROM {t} WHERE id = ?", (item_id,))
            if row is None:
                raise HTTPException(404, "todo not found")
            return _to_api(row)

        @r.get("/items")
        async def list_items() -> list[dict[str, Any]]:
            t = await self._ensure()
            rows = await self.db.fetch_all(
                f"SELECT * FROM {t} "
                f"ORDER BY done ASC, priority DESC, position ASC, id ASC"
            )
            return [_to_api(row) for row in rows]

        @r.post("/items", status_code=201)
        async def create_item(body: TodoCreate) -> dict[str, Any]:
            t = await self._ensure()
            now = time.time()
            max_pos = await self.db.fetch_one(
                f"SELECT COALESCE(MAX(position), 0) AS m FROM {t}"
            )
            pos = int((max_pos or {}).get("m", 0)) + 1
            due_at = _due_at(body.due)
            # If the due day is already here, mark it notified so we don't fire a
            # late reminder for a date the user set in the past.
            notified = 1 if (due_at is not None and due_at <= now) else 0
            new_id = await self.db.execute_insert(
                f"INSERT INTO {t} "
                f"(title, done, priority, due, due_at, notified, position, "
                f" created, updated) "
                f"VALUES (?, 0, ?, ?, ?, ?, ?, ?, ?)",
                (body.title.strip(), body.priority, body.due, due_at, notified,
                 pos, now, now),
            )
            item = await _row(new_id)
            self.events.publish("todo.created", item)
            # Demo of the core notification service: any attachment can do this.
            await self.notify(
                "New todo added", item["title"], icon="check-square", url="/a/todo"
            )
            self._wake.set()  # a new due date may be sooner than the current sleep
            return item

        # Declared before "/items/{item_id}" so the literal "order" path isn't
        # captured as an item id (FastAPI matches routes in declaration order).
        @r.patch("/items/order", status_code=204)
        async def reorder_items(body: TodoReorder) -> None:
            """Set explicit manual order from a drag-reorder. ``body.order`` is the
            list of item ids in their new top-to-bottom order; we rewrite each
            row's ``position`` to its index so the list's ``position ASC`` sort
            reflects it. The list still sorts by ``done`` then ``priority`` first,
            so dragging orders *within* a priority band (the visual grouping)."""
            t = await self._ensure()
            now = time.time()
            for i, item_id in enumerate(body.order):
                await self.db.execute(
                    f"UPDATE {t} SET position = ?, updated = ? WHERE id = ?",
                    (i, now, item_id),
                )
            self.events.publish("todo.reordered", {"order": body.order})

        @r.patch("/items/{item_id}")
        async def update_item(item_id: int, body: TodoUpdate) -> dict[str, Any]:
            t = await self._ensure()
            await _row(item_id)  # 404 if missing
            sets: list[str] = []
            params: list[Any] = []
            if body.title is not None:
                sets.append("title = ?")
                params.append(body.title.strip())
            if body.done is not None:
                sets.append("done = ?")
                params.append(1 if body.done else 0)
            if body.priority is not None:
                sets.append("priority = ?")
                params.append(body.priority)
            if body.clear_due:
                sets += ["due = NULL", "due_at = NULL", "notified = 0"]
            elif body.due is not None:
                due_at = _due_at(body.due)
                now = time.time()
                sets += ["due = ?", "due_at = ?", "notified = ?"]
                params += [body.due, due_at, 1 if due_at <= now else 0]
            if sets:
                sets.append("updated = ?")
                params.append(time.time())
                params.append(item_id)
                await self.db.execute(
                    f"UPDATE {t} SET {', '.join(sets)} WHERE id = ?", params
                )
            item = await _row(item_id)
            self.events.publish("todo.updated", item)
            self._wake.set()  # due date may have moved earlier
            return item

        @r.post("/items/{item_id}/toggle")
        async def toggle_item(item_id: int) -> dict[str, Any]:
            t = await self._ensure()
            row = await _row(item_id)
            await self.db.execute(
                f"UPDATE {t} SET done = ?, updated = ? WHERE id = ?",
                (0 if row["done"] else 1, time.time(), item_id),
            )
            item = await _row(item_id)
            self.events.publish("todo.updated", item)
            return item

        @r.post("/items/{item_id}/cycle-priority")
        async def cycle_priority(item_id: int) -> dict[str, Any]:
            t = await self._ensure()
            row = await _row(item_id)
            nxt = (int(row["priority"]) + 1) % (PRIORITY_MAX + 1)
            await self.db.execute(
                f"UPDATE {t} SET priority = ?, updated = ? WHERE id = ?",
                (nxt, time.time(), item_id),
            )
            item = await _row(item_id)
            self.events.publish("todo.updated", item)
            return item

        @r.delete("/items/{item_id}", status_code=204)
        async def delete_item(item_id: int) -> None:
            t = await self._ensure()
            await _row(item_id)
            await self.db.execute(f"DELETE FROM {t} WHERE id = ?", (item_id,))
            self.events.publish("todo.deleted", {"id": item_id})

        @r.post("/clear-done", status_code=204)
        async def clear_done() -> None:
            t = await self._ensure()
            await self.db.execute(f"DELETE FROM {t} WHERE done = 1")
            self.events.publish("todo.cleared", None)

        return r

    # --- due-date scheduler --------------------------------------------------

    async def _due_loop(self) -> None:
        """Fire a notification when an undone todo's due day arrives.

        Durable: reads the DB each pass, so due dates set before a restart still
        fire. Wakes early when a due date is created/changed (via ``_wake``).
        Iterates every account in its own isolated scope.
        """
        while True:
            sleep = _SCHED_IDLE_S
            try:
                for acct in await self.ctx.list_accounts():
                    is_admin = (acct.get("role") or "admin") == "admin"
                    with self.ctx.account_scope(acct["username"], is_admin=is_admin):
                        try:
                            acct_sleep = await self._due_pass()
                        except Exception:  # noqa: BLE001 - one account must not stall the rest
                            log.exception("todo due pass failed for an account")
                            acct_sleep = _SCHED_IDLE_S
                    sleep = min(sleep, acct_sleep)
            except asyncio.CancelledError:
                raise
            except Exception:  # noqa: BLE001 - never let the loop die
                log.exception("todo due loop iteration failed")
                sleep = _SCHED_IDLE_S
            try:
                await asyncio.wait_for(self._wake.wait(), timeout=sleep)
            except asyncio.TimeoutError:
                pass
            self._wake.clear()

    async def _due_pass(self) -> float:
        """Fire due reminders for the current account; return seconds until its
        next due reminder (or the idle cap)."""
        t = await self._ensure()
        now = time.time()
        due = await self.db.fetch_all(
            f"SELECT * FROM {t} WHERE notified = 0 AND done = 0 "
            f"AND due_at IS NOT NULL AND due_at <= ? ORDER BY due_at LIMIT 50",
            (now,),
        )
        for row in due:
            await self._fire_due(row)
        nxt = await self.db.fetch_one(
            f"SELECT MIN(due_at) AS t FROM {t} "
            f"WHERE notified = 0 AND done = 0 AND due_at IS NOT NULL"
        )
        next_due = (nxt or {}).get("t")
        if next_due is None:
            return _SCHED_IDLE_S
        return max(1.0, min(_SCHED_IDLE_S, next_due - time.time()))

    async def _fire_due(self, row: dict[str, Any]) -> None:
        t = self.db.table("items")
        await self.notify(
            "Todo due today",
            row["title"],
            icon="check-square",
            url="/a/todo",
            data={"todo_id": row["id"], "due": row["due"]},
        )
        await self.db.execute(
            f"UPDATE {t} SET notified = 1 WHERE id = ?", (row["id"],)
        )
        self.events.publish("todo.updated", _to_api(dict(row, notified=1)))

    # --- UI -----------------------------------------------------------------

    def ui(self) -> dict[str, Any]:
        return ui.view(
            title="Todo",
            children=[
                ui.surface(
                    level=2,
                    children=[
                        ui.row(
                            align="end",
                            children=[
                                ui.input(
                                    "title",
                                    label="New item",
                                    placeholder="What needs doing?",
                                ),
                                ui.select(
                                    "priority",
                                    label="Priority",
                                    options=[
                                        {"value": "0", "label": "None"},
                                        {"value": "1", "label": "Low"},
                                        {"value": "2", "label": "Medium"},
                                        {"value": "3", "label": "High"},
                                    ],
                                ),
                                ui.input("due", label="Due date", kind="date"),
                                ui.button(
                                    "Add",
                                    action=ui.post(
                                        "items",
                                        body={
                                            "title": "$title",
                                            "priority": "$priority",
                                            "due": "$due",
                                        },
                                    ),
                                ),
                            ],
                        )
                    ],
                ),
                ui.list_(
                    source="items",
                    key="id",
                    empty="Nothing yet — add your first task.",
                    # Drag a row by its handle to set a manual order. Items sort by
                    # priority first, so a drag reorders within a priority band.
                    reorder=ui.patch("items/order"),
                    item=ui.surface(
                        interactive=True,
                        # Tapping anywhere on the row toggles done — the checkbox
                        # is a tiny target, so the whole row is the hit area.
                        # Clicks on inner controls (priority/delete) don't bubble.
                        action=ui.post("items/{id}/toggle"),
                        children=[
                            ui.row(
                                justify="between",
                                align="center",
                                children=[
                                    ui.row(
                                        align="center",
                                        children=[
                                            ui.checkbox(
                                                bind="done",
                                                action=ui.post("items/{id}/toggle"),
                                            ),
                                            ui.text("", bind="title", role="body"),
                                        ],
                                    ),
                                    ui.row(
                                        align="center",
                                        children=[
                                            ui.badge(
                                                "",
                                                bind="due_label",
                                                variant_bind="due_variant",
                                                hide_when_empty=True,
                                            ),
                                            ui.button(
                                                "None",
                                                bind="priority_chip",
                                                variant_bind="priority_btn_variant",
                                                size="sm",
                                                action=ui.post(
                                                    "items/{id}/cycle-priority"
                                                ),
                                            ),
                                            ui.button(
                                                "Delete",
                                                variant="danger",
                                                action=ui.delete("items/{id}"),
                                            ),
                                        ],
                                    ),
                                ],
                            )
                        ],
                    ),
                ),
                ui.button(
                    "Clear completed",
                    variant="ghost",
                    action=ui.post("clear-done"),
                ),
            ],
        )


def _to_api(row: dict[str, Any]) -> dict[str, Any]:
    priority = int(row["priority"]) if row.get("priority") is not None else 0
    return {
        "id": row["id"],
        "title": row["title"],
        "done": bool(row["done"]),
        "priority": priority,
        "priority_label": _PRIORITY_LABELS[priority],
        "priority_variant": _PRIORITY_VARIANTS[priority],
        # The cycle "chip" is a Button, whose variant set excludes `info`; map
        # "none" to ghost so it reads as an empty/settable slot.
        "priority_chip": _PRIORITY_CHIP_LABELS[priority],
        "priority_btn_variant": _PRIORITY_BTN_VARIANTS[priority],
        "due": row.get("due"),
        "due_label": _due_label(row.get("due"), row.get("due_at")),
        "due_variant": _due_variant(row.get("due_at"), bool(row["done"])),
        "notified": bool(row.get("notified")),
        "position": row["position"],
        "created": row["created"],
        "updated": row["updated"],
    }


def _due_label(due: str | None, due_at: float | None) -> str:
    """Short human label for a due date: Today / Tomorrow / Mon DD."""
    if not due:
        return ""
    try:
        d = dt.date.fromisoformat(due)
    except (ValueError, TypeError):
        return ""
    today = dt.date.today()
    delta = (d - today).days
    if delta == 0:
        return "Due today"
    if delta == 1:
        return "Due tomorrow"
    if delta == -1:
        return "Due yesterday"
    if delta < -1:
        return f"Overdue · {d.strftime('%b %d')}"
    return f"Due {d.strftime('%b %d')}"


def _due_variant(due_at: float | None, done: bool) -> str:
    if due_at is None:
        return "neutral"
    if done:
        return "neutral"
    # Past local-midnight (today or earlier) reads urgent; future is informational.
    return "danger" if due_at <= time.time() else "info"


# Display label + themed Badge variant per priority level. Empty label for
# "none" so those rows show no badge at all.
_PRIORITY_LABELS = {0: "", 1: "Low", 2: "Medium", 3: "High"}
_PRIORITY_VARIANTS = {0: "neutral", 1: "info", 2: "warn", 3: "danger"}
# The clickable cycle chip always shows a label (so there's something to click)
# and uses only Button-valid variants.
_PRIORITY_CHIP_LABELS = {0: "None", 1: "Low", 2: "Medium", 3: "High"}
_PRIORITY_BTN_VARIANTS = {0: "ghost", 1: "neutral", 2: "warn", 3: "danger"}


attachment = Todo()

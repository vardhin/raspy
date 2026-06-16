"""Notifications — a core service every attachment can use.

This is core plumbing (it sits next to events/ws), not an attachment. Any
attachment gets ``ctx.notify(title, body, ...)`` and the spine handles the rest:

1. **Record** the notification in SQLite (history, read/unread).
2. **Foreground push** — publish a ``notification.new`` event on the EventBus, so
   any *connected* client (browser tab, Capacitor/Flutter webview) shows it live
   via the existing WebSocket. See ``core/ws.py``.
3. **Background push** — deliver to registered subscriptions even when no tab is
   open, via the Web Push protocol (browser) and, in future, FCM (native APK).

Subscriptions carry a ``kind`` (``webpush`` | ``fcm``) so the same
``/subscribe`` endpoint serves both a browser service worker *and* a future
Flutter app registering an FCM token — only the send path branches on ``kind``.

Web Push needs a VAPID keypair. Generate one (see ``scripts``/README) and put it
in config; without it the foreground path still works and background push is
simply skipped with a warning.
"""

from __future__ import annotations

import asyncio
import json
import logging
import time
from typing import Any

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel, Field

from .auth.scope import account_slug, current_account, current_account_legacy
from .db import Database

log = logging.getLogger("raspy.notifications")

# The owner key stored on every notification / subscription, so each account only
# sees its own. The original admin keeps the legacy unsuffixed scope (sentinel
# below) to match its pre-isolation storage; children get their ``account_slug``.
# A row written before isolation (or by a background task with no account context)
# also lands on the legacy owner, so the admin still sees historical notifications.
_LEGACY_OWNER = "_admin"


def owner_key(username: str | None, *, is_admin: bool) -> str:
    """The account key a notification is stored/filtered under. Admin (and any
    contextless/background write) → the legacy sentinel; a child → its slug. The
    WS endpoint uses this with the connected account to filter the live feed, so
    it must match :func:`_current_owner` exactly."""
    if username is None or is_admin:
        return _LEGACY_OWNER
    return account_slug(username)


def _current_owner() -> str:
    """The account key for whoever is in scope right now. Mirrors how ScopedDB /
    data dirs resolve the current account (see core/auth/scope.py): admin/legacy
    → the sentinel, a child → its slug. Read at call time from the ContextVars the
    auth gate and the background pollers set."""
    return owner_key(
        current_account.get(), is_admin=current_account_legacy.get()
    )

# Core tables are prefixed ``core_`` to stay clear of attachment ``att_*`` tables.
_T_NOTES = "core_notifications"
_T_SUBS = "core_push_subscriptions"
_T_OUTBOX = "core_push_outbox"

# Outbox retry policy. Backoff is exponential in attempts, capped, so a push
# service hiccup is retried a handful of times over a few minutes rather than
# hammered or dropped.
_MAX_ATTEMPTS = 6
_BACKOFF_BASE_S = 5.0  # 5s, 10s, 20s, 40s, 80s, 160s
_BACKOFF_CAP_S = 300.0
_DRAIN_IDLE_S = 30.0  # how long the worker sleeps when the outbox is empty


# --- API models --------------------------------------------------------------


class PushSubscribe(BaseModel):
    """A client registering to receive background push.

    Browser (Web Push): ``kind="webpush"`` with ``endpoint`` + ``keys``.
    Native (future FCM): ``kind="fcm"`` with ``token`` in ``keys.token``.
    """

    kind: str = Field(default="webpush")
    endpoint: str = Field(min_length=1, max_length=2048)
    keys: dict[str, str] = Field(default_factory=dict)


class TestNotify(BaseModel):
    title: str = Field(default="Test notification", max_length=200)
    body: str = Field(default="Hello from your Pi 👋", max_length=1000)


# --- service -----------------------------------------------------------------


class NotificationService:
    """Owns notification history + push subscriptions for the whole spine."""

    def __init__(self, db: Database, events: Any, settings: Any) -> None:
        self._db = db
        self._events = events
        self._settings = settings
        self._worker: asyncio.Task[None] | None = None
        # Set when a new outbox row is enqueued, so the drain worker wakes
        # immediately instead of waiting out its idle sleep.
        self._wake = asyncio.Event()
        # Pending delayed notifications, so they can be cancelled on shutdown.
        self._scheduled: set[asyncio.Task[None]] = set()

    @property
    def vapid_public_key(self) -> str | None:
        return getattr(self._settings, "vapid_public_key", None) or None

    async def init(self) -> None:
        await self._db.execute(
            f"""
            CREATE TABLE IF NOT EXISTS {_T_NOTES} (
                id        INTEGER PRIMARY KEY AUTOINCREMENT,
                account   TEXT    NOT NULL DEFAULT '{_LEGACY_OWNER}',
                source    TEXT    NOT NULL DEFAULT 'core',
                title     TEXT    NOT NULL,
                body      TEXT    NOT NULL DEFAULT '',
                icon      TEXT,
                url       TEXT,
                data      TEXT,
                read      INTEGER NOT NULL DEFAULT 0,
                created   REAL    NOT NULL
            )
            """
        )
        await self._db.execute(
            f"""
            CREATE TABLE IF NOT EXISTS {_T_SUBS} (
                id        INTEGER PRIMARY KEY AUTOINCREMENT,
                account   TEXT    NOT NULL DEFAULT '{_LEGACY_OWNER}',
                kind      TEXT    NOT NULL DEFAULT 'webpush',
                endpoint  TEXT    NOT NULL UNIQUE,
                keys      TEXT    NOT NULL DEFAULT '{{}}',
                created   REAL    NOT NULL
            )
            """
        )
        # Durable delivery queue: one row per (notification × subscription).
        # Survives restarts — the drain worker picks up leftover 'pending' rows.
        await self._db.execute(
            f"""
            CREATE TABLE IF NOT EXISTS {_T_OUTBOX} (
                id           INTEGER PRIMARY KEY AUTOINCREMENT,
                endpoint     TEXT    NOT NULL,
                kind         TEXT    NOT NULL DEFAULT 'webpush',
                payload      TEXT    NOT NULL,
                status       TEXT    NOT NULL DEFAULT 'pending',
                attempts     INTEGER NOT NULL DEFAULT 0,
                next_attempt REAL    NOT NULL DEFAULT 0,
                last_error   TEXT,
                created      REAL    NOT NULL
            )
            """
        )
        await self._db.execute(
            f"CREATE INDEX IF NOT EXISTS {_T_OUTBOX}_due "
            f"ON {_T_OUTBOX} (status, next_attempt)"
        )
        await self._migrate_account_columns()

    async def _migrate_account_columns(self) -> None:
        """Add the ``account`` owner column to notification/subscription tables
        created before per-account isolation existed. SQLite has no ``ADD COLUMN
        IF NOT EXISTS``, so introspect and add what's missing. Existing rows keep
        the default (legacy/admin owner), so the admin still sees its history."""
        for table in (_T_NOTES, _T_SUBS):
            rows = await self._db.fetch_all(f"PRAGMA table_info({table})")
            if not any(r["name"] == "account" for r in rows):
                await self._db.execute(
                    f"ALTER TABLE {table} ADD COLUMN account "
                    f"TEXT NOT NULL DEFAULT '{_LEGACY_OWNER}'"
                )

    # --- worker lifecycle ----------------------------------------------------

    def start(self) -> None:
        """Start the background drain worker. Call once, after init()."""
        if self._worker is None or self._worker.done():
            self._worker = asyncio.create_task(self._drain_loop())

    async def stop(self) -> None:
        """Stop the drain worker. In-flight sends finish; pending rows persist."""
        for task in list(self._scheduled):
            task.cancel()
        if self._scheduled:
            await asyncio.gather(*self._scheduled, return_exceptions=True)
        self._scheduled.clear()
        if self._worker is not None:
            self._worker.cancel()
            try:
                await self._worker
            except asyncio.CancelledError:
                pass
            self._worker = None

    # --- the one method attachments call ------------------------------------

    async def notify(
        self,
        title: str,
        body: str = "",
        *,
        source: str = "core",
        icon: str | None = None,
        url: str | None = None,
        data: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """Record + deliver a notification through every available channel.

        Scoped to the account in context: it's stored under that owner, only
        delivered live to that account's connected clients, and only pushed to
        that account's subscriptions. So a child's notification never reaches the
        admin (or another child), and vice-versa."""
        now = time.time()
        owner = _current_owner()
        note_id = await self._db.execute_insert(
            f"INSERT INTO {_T_NOTES} (account, source, title, body, icon, url, data, read, created) "
            f"VALUES (?, ?, ?, ?, ?, ?, ?, 0, ?)",
            (owner, source, title, body, icon, url, json.dumps(data) if data else None, now),
        )
        note = {
            "id": note_id,
            "source": source,
            "title": title,
            "body": body,
            "icon": icon,
            "url": url,
            "data": data,
            "read": False,
            "created": now,
        }
        # 1. Foreground: live to this account's connected clients over the WS.
        #    The "account" field is the delivery filter the WS endpoint applies;
        #    it is not part of the persisted/public note shape.
        #    - "notification.new" drives the global handler (OS popup + bell).
        #    - "notifications.changed" matches the notifications app's id prefix
        #      so an open /a/notifications view re-pulls its history live.
        self._events.publish("notification.new", {**note, "account": owner})
        self._events.publish("notifications.changed", {"id": note_id, "account": owner})
        # 2. Background: enqueue one durable outbox row per subscription owned by
        #    this account. The drain worker delivers them with retries — so a
        #    notification raised while the push service (or Pi) is momentarily
        #    down is not lost.
        await self._enqueue_push(note, owner)
        return note

    def notify_later(self, delay: float, title: str, body: str = "", **kwargs: Any) -> None:
        """Fire a notification after ``delay`` seconds. Used by the test button so
        you can background the app and watch the real (background) notification
        arrive. The task is tracked and cancelled on shutdown."""

        async def _run() -> None:
            try:
                await asyncio.sleep(delay)
                await self.notify(title, body, **kwargs)
            except asyncio.CancelledError:
                pass

        task = asyncio.create_task(_run())
        self._scheduled.add(task)
        task.add_done_callback(self._scheduled.discard)

    # --- history -------------------------------------------------------------

    async def list(self, limit: int = 50) -> list[dict[str, Any]]:
        owner = _current_owner()
        rows = await self._db.fetch_all(
            f"SELECT * FROM {_T_NOTES} WHERE account = ? ORDER BY created DESC LIMIT ?",
            (owner, limit),
        )
        return [_note_to_api(r) for r in rows]

    async def unread_count(self) -> int:
        owner = _current_owner()
        row = await self._db.fetch_one(
            f"SELECT COUNT(*) AS n FROM {_T_NOTES} WHERE account = ? AND read = 0",
            (owner,),
        )
        return int((row or {}).get("n", 0))

    async def mark_read(self, note_id: int) -> None:
        # Scope by owner so an account can't read/clear another's notifications by
        # guessing ids — the global notifications router is shared across accounts.
        await self._db.execute(
            f"UPDATE {_T_NOTES} SET read = 1 WHERE id = ? AND account = ?",
            (note_id, _current_owner()),
        )

    async def mark_all_read(self) -> None:
        await self._db.execute(
            f"UPDATE {_T_NOTES} SET read = 1 WHERE read = 0 AND account = ?",
            (_current_owner(),),
        )

    async def delete(self, note_id: int) -> None:
        await self._db.execute(
            f"DELETE FROM {_T_NOTES} WHERE id = ? AND account = ?",
            (note_id, _current_owner()),
        )

    async def clear(self) -> None:
        await self._db.execute(
            f"DELETE FROM {_T_NOTES} WHERE account = ?", (_current_owner(),)
        )

    # --- subscriptions -------------------------------------------------------

    async def add_subscription(self, sub: PushSubscribe) -> None:
        # Stamp the owner so background push only reaches this account's devices.
        # On re-subscribe (same endpoint) the owner is reasserted too, in case the
        # same browser/device was handed to a different account.
        owner = _current_owner()
        await self._db.execute(
            f"INSERT INTO {_T_SUBS} (account, kind, endpoint, keys, created) VALUES (?, ?, ?, ?, ?) "
            f"ON CONFLICT(endpoint) DO UPDATE SET "
            f"account = excluded.account, kind = excluded.kind, keys = excluded.keys",
            (owner, sub.kind, sub.endpoint, json.dumps(sub.keys), time.time()),
        )

    async def remove_subscription(self, endpoint: str) -> None:
        await self._db.execute(
            f"DELETE FROM {_T_SUBS} WHERE endpoint = ?", (endpoint,)
        )

    # --- push delivery (durable outbox) -------------------------------------

    async def _enqueue_push(self, note: dict[str, Any], owner: str) -> None:
        """Write one outbox row per subscription owned by ``owner``, then poke the
        worker. Only this account's devices get the background push."""
        subs = await self._db.fetch_all(
            f"SELECT * FROM {_T_SUBS} WHERE account = ?", (owner,)
        )
        if not subs:
            return
        payload = json.dumps(
            {
                "title": note["title"],
                "body": note["body"],
                "icon": note.get("icon"),
                "url": note.get("url"),
                "data": {"id": note["id"], **(note.get("data") or {})},
            }
        )
        now = time.time()
        for sub in subs:
            await self._db.execute(
                f"INSERT INTO {_T_OUTBOX} "
                f"(endpoint, kind, payload, status, attempts, next_attempt, created) "
                f"VALUES (?, ?, ?, 'pending', 0, ?, ?)",
                (sub["endpoint"], sub.get("kind", "webpush"), payload, now, now),
            )
        self._wake.set()

    async def _drain_loop(self) -> None:
        """Forever: deliver due outbox rows, sleeping until the next is due."""
        while True:
            try:
                slept_for = await self._drain_once()
            except asyncio.CancelledError:
                raise
            except Exception:  # noqa: BLE001 - never let the worker die
                log.exception("outbox drain iteration failed")
                slept_for = _DRAIN_IDLE_S
            # Wait until something is enqueued or the next row comes due.
            try:
                await asyncio.wait_for(self._wake.wait(), timeout=slept_for)
            except asyncio.TimeoutError:
                pass
            self._wake.clear()

    async def _drain_once(self) -> float:
        """Send every currently-due row. Returns seconds to sleep before next."""
        now = time.time()
        due = await self._db.fetch_all(
            f"SELECT * FROM {_T_OUTBOX} WHERE status = 'pending' AND next_attempt <= ? "
            f"ORDER BY next_attempt ASC LIMIT 50",
            (now,),
        )
        for row in due:
            await self._deliver_row(row)

        # When does the next pending row come due? That's how long we can sleep.
        nxt = await self._db.fetch_one(
            f"SELECT MIN(next_attempt) AS t FROM {_T_OUTBOX} WHERE status = 'pending'"
        )
        next_due = (nxt or {}).get("t")
        if next_due is None:
            return _DRAIN_IDLE_S
        return max(0.5, min(_DRAIN_IDLE_S, next_due - time.time()))

    async def _deliver_row(self, row: dict[str, Any]) -> None:
        sub = {"endpoint": row["endpoint"], "kind": row["kind"]}
        # The outbox stores endpoint+payload; keys live on the subscription row.
        sub_row = await self._db.fetch_one(
            f"SELECT * FROM {_T_SUBS} WHERE endpoint = ?", (row["endpoint"],)
        )
        if sub_row is None:
            # Subscription gone (unsubscribed) — this delivery is moot.
            await self._mark_outbox(row["id"], "dead", row["attempts"], "no subscription")
            return
        sub["keys"] = sub_row["keys"]
        payload = row["payload"]
        kind = row["kind"]

        try:
            if kind == "webpush":
                await self._send_webpush(sub, payload)
            elif kind == "fcm":
                await self._send_fcm(sub, payload)
            else:
                raise RuntimeError(f"unknown kind {kind!r}")
            await self._mark_outbox(row["id"], "sent", row["attempts"] + 1, None)
        except _GoneError:
            # Subscription expired at the push service — prune it and kill the row.
            await self.remove_subscription(row["endpoint"])
            await self._mark_outbox(row["id"], "dead", row["attempts"] + 1, "gone (410/404)")
        except Exception as exc:  # noqa: BLE001
            attempts = row["attempts"] + 1
            if attempts >= _MAX_ATTEMPTS:
                await self._mark_outbox(row["id"], "dead", attempts, repr(exc))
                log.warning(
                    "push to %s permanently failed after %d attempts: %r",
                    row["endpoint"], attempts, exc,
                )
            else:
                delay = min(_BACKOFF_CAP_S, _BACKOFF_BASE_S * (2 ** (attempts - 1)))
                await self._db.execute(
                    f"UPDATE {_T_OUTBOX} SET attempts = ?, next_attempt = ?, "
                    f"last_error = ? WHERE id = ?",
                    (attempts, time.time() + delay, repr(exc), row["id"]),
                )

    async def _mark_outbox(
        self, row_id: int, status: str, attempts: int, error: str | None
    ) -> None:
        await self._db.execute(
            f"UPDATE {_T_OUTBOX} SET status = ?, attempts = ?, last_error = ? WHERE id = ?",
            (status, attempts, error, row_id),
        )

    async def outbox_stats(self) -> dict[str, int]:
        """Counts by status — handy for /healthz or debugging."""
        rows = await self._db.fetch_all(
            f"SELECT status, COUNT(*) AS n FROM {_T_OUTBOX} GROUP BY status"
        )
        return {r["status"]: r["n"] for r in rows}

    async def _send_webpush(self, sub: dict[str, Any], payload: str) -> None:
        priv = getattr(self._settings, "vapid_private_key", None)
        subject = getattr(self._settings, "vapid_subject", None) or "mailto:admin@localhost"
        if not priv:
            log.warning("web push skipped: no VAPID private key configured")
            return

        # pywebpush is sync; run it off the event loop.
        def _send() -> None:
            from pywebpush import WebPushException, webpush

            subscription_info = {
                "endpoint": sub["endpoint"],
                "keys": json.loads(sub["keys"]),
            }
            try:
                webpush(
                    subscription_info=subscription_info,
                    data=payload,
                    vapid_private_key=priv,
                    vapid_claims={"sub": subject},
                )
            except WebPushException as exc:  # noqa: PERF203
                status = getattr(exc.response, "status_code", None)
                if status in (404, 410):
                    raise _GoneError from exc
                raise

        await asyncio.to_thread(_send)

    async def _send_fcm(self, sub: dict[str, Any], payload: str) -> None:
        """Placeholder for native (Flutter APK) FCM delivery.

        When the APK lands, register its FCM token via /subscribe with
        kind="fcm" (token in keys.token), and implement the FCM HTTP v1 send
        here. The store, history, and foreground paths already work unchanged.
        """
        log.info("fcm delivery not yet implemented; token stored only")


class _GoneError(Exception):
    """Raised internally when a push subscription is no longer valid (404/410)."""


def _note_to_api(row: dict[str, Any]) -> dict[str, Any]:
    return {
        "id": row["id"],
        "source": row["source"],
        "title": row["title"],
        "body": row["body"],
        "icon": row["icon"],
        "url": row["url"],
        "data": json.loads(row["data"]) if row.get("data") else None,
        "read": bool(row["read"]),
        "created": row["created"],
    }


# --- router ------------------------------------------------------------------

router = APIRouter()


def _service(request: Request) -> NotificationService:
    svc = getattr(request.app.state, "notifications", None)
    if svc is None:
        raise HTTPException(503, "notification service unavailable")
    return svc


@router.get("/notifications")
async def list_notifications(request: Request, limit: int = 50) -> dict[str, Any]:
    svc = _service(request)
    items = await svc.list(limit=limit)
    return {"items": items, "unread": await svc.unread_count()}


@router.post("/notifications/{note_id}/read", status_code=204)
async def read_notification(request: Request, note_id: int) -> None:
    await _service(request).mark_read(note_id)


@router.post("/notifications/read-all", status_code=204)
async def read_all(request: Request) -> None:
    await _service(request).mark_all_read()


@router.delete("/notifications", status_code=204)
async def clear_notifications(request: Request) -> None:
    await _service(request).clear()


@router.get("/notifications/vapid-key")
async def vapid_key(request: Request) -> dict[str, str | None]:
    return {"key": _service(request).vapid_public_key}


@router.get("/notifications/outbox")
async def outbox(request: Request) -> dict[str, int]:
    """Delivery queue health: counts by status (pending/sent/dead)."""
    return await _service(request).outbox_stats()


@router.post("/notifications/subscribe", status_code=201)
async def subscribe(request: Request, sub: PushSubscribe) -> dict[str, bool]:
    await _service(request).add_subscription(sub)
    return {"ok": True}


@router.post("/notifications/unsubscribe", status_code=204)
async def unsubscribe(request: Request, body: dict[str, str]) -> None:
    endpoint = body.get("endpoint")
    if not endpoint:
        raise HTTPException(422, "endpoint required")
    await _service(request).remove_subscription(endpoint)


@router.post("/notifications/test", status_code=201)
async def test_notify(request: Request, body: TestNotify) -> dict[str, Any]:
    return await _service(request).notify(body.title, body.body, source="test")

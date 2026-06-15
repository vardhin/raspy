"""SQLite access, namespaced per attachment. See plan/10-spine.md §5.

One database file, WAL mode, single-writer-friendly (one user on a Pi). Each
attachment gets a :class:`ScopedDB` whose ``table()`` helper prefixes table names
with the attachment id, so attachments can't collide or read each other's tables
by accident.

sqlite3 is synchronous; we run queries in a thread via ``asyncio.to_thread`` so
they don't block the event loop. A single shared connection with
``check_same_thread=False`` plus a lock keeps it simple and correct for this scale.
"""

from __future__ import annotations

import asyncio
import re
import sqlite3
import threading
from pathlib import Path
from typing import Any, Iterable

_IDENT_RE = re.compile(r"^[a-z][a-z0-9_]*$")


def _validate_ident(name: str, kind: str) -> str:
    if not _IDENT_RE.match(name):
        raise ValueError(f"invalid {kind}: {name!r} (must match {_IDENT_RE.pattern})")
    return name


class Database:
    """Owns the single SQLite connection for the whole spine."""

    def __init__(self, path: Path) -> None:
        self._path = path
        self._lock = threading.Lock()
        self._conn: sqlite3.Connection | None = None

    def connect(self) -> None:
        self._path.parent.mkdir(parents=True, exist_ok=True)
        conn = sqlite3.connect(
            self._path, check_same_thread=False, isolation_level=None
        )
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute("PRAGMA foreign_keys=ON")
        conn.execute("PRAGMA busy_timeout=5000")
        self._conn = conn

    def close(self) -> None:
        if self._conn is not None:
            self._conn.close()
            self._conn = None

    @property
    def raw(self) -> sqlite3.Connection:
        if self._conn is None:
            raise RuntimeError("database not connected")
        return self._conn

    # --- sync primitives (run under lock) -----------------------------------

    def _execute(self, sql: str, params: Iterable[Any] = ()) -> sqlite3.Cursor:
        with self._lock:
            return self.raw.execute(sql, tuple(params))

    def _executemany(self, sql: str, seq: Iterable[Iterable[Any]]) -> sqlite3.Cursor:
        with self._lock:
            return self.raw.executemany(sql, [tuple(p) for p in seq])

    # --- async wrappers ------------------------------------------------------

    async def execute(self, sql: str, params: Iterable[Any] = ()) -> None:
        await asyncio.to_thread(self._execute, sql, params)

    async def fetch_all(
        self, sql: str, params: Iterable[Any] = ()
    ) -> list[dict[str, Any]]:
        def run() -> list[dict[str, Any]]:
            cur = self._execute(sql, params)
            return [dict(r) for r in cur.fetchall()]

        return await asyncio.to_thread(run)

    async def fetch_one(
        self, sql: str, params: Iterable[Any] = ()
    ) -> dict[str, Any] | None:
        def run() -> dict[str, Any] | None:
            cur = self._execute(sql, params)
            row = cur.fetchone()
            return dict(row) if row is not None else None

        return await asyncio.to_thread(run)

    async def execute_insert(self, sql: str, params: Iterable[Any] = ()) -> int:
        """Execute an INSERT and return the new rowid."""

        def run() -> int:
            cur = self._execute(sql, params)
            return int(cur.lastrowid or 0)

        return await asyncio.to_thread(run)

    async def execute_insert_changed(
        self, sql: str, params: Iterable[Any] = ()
    ) -> tuple[int, int]:
        """Execute an INSERT and return ``(rowid, rows_affected)``.

        For ``INSERT OR IGNORE``, ``lastrowid`` is unreliable — SQLite leaves it
        pointing at the previous successful insert when a row is ignored. Callers
        that need to distinguish a genuine insert from a no-op (e.g. dedup) must
        check ``rows_affected``, which is 0 when the row was ignored.
        """

        def run() -> tuple[int, int]:
            cur = self._execute(sql, params)
            return int(cur.lastrowid or 0), int(cur.rowcount or 0)

        return await asyncio.to_thread(run)


class ScopedDB:
    """A database handle scoped to one attachment *and* the current account.

    ``table("items")`` -> ``"att_todo_items"`` for the original admin (legacy,
    unsuffixed — preserves data that predates per-account isolation), or
    ``"att_todo_u1a2b3c4_items"`` for a child account, where the middle token is
    ``account_slug(username)``. Pass the result into your SQL.

    The account is read from the ``current_account`` ContextVar **at call time**
    (set by the auth gate per request), NOT captured at construction — so a single
    attachment instance serves every account, each landing in its own tables.
    Attachments must therefore call ``table()`` *inside* a request handler, not
    once at load time.

    The scope is a naming convention enforced here; it keeps attachment tables
    namespaced, per-account isolated, and greppable.
    """

    def __init__(self, db: Database, attachment_id: str) -> None:
        self._db = db
        self._att = _validate_ident(attachment_id, "attachment id")

    def _prefix(self) -> str:
        # Imported lazily to avoid a core<->auth import cycle at module load.
        from .auth.scope import account_slug, current_account, current_account_legacy

        username = current_account.get()
        # Legacy/global scope: the original admin, or any context with no account
        # set (background tasks, pre-isolation tests) — keep the historical
        # unsuffixed prefix so existing data stays reachable.
        if username is None or current_account_legacy.get():
            return f"att_{self._att}_"
        return f"att_{self._att}_{account_slug(username)}_"

    def table(self, name: str) -> str:
        return self._prefix() + _validate_ident(name, "table name")

    # Thin pass-throughs so attachments never touch the global Database directly.
    async def execute(self, sql: str, params: Iterable[Any] = ()) -> None:
        await self._db.execute(sql, params)

    async def fetch_all(
        self, sql: str, params: Iterable[Any] = ()
    ) -> list[dict[str, Any]]:
        return await self._db.fetch_all(sql, params)

    async def fetch_one(
        self, sql: str, params: Iterable[Any] = ()
    ) -> dict[str, Any] | None:
        return await self._db.fetch_one(sql, params)

    async def execute_insert(self, sql: str, params: Iterable[Any] = ()) -> int:
        return await self._db.execute_insert(sql, params)

    async def execute_insert_changed(
        self, sql: str, params: Iterable[Any] = ()
    ) -> tuple[int, int]:
        return await self._db.execute_insert_changed(sql, params)

"""Dropbox — drop encrypted files onto *another* account; the unified inbox.

This is the vault's cross-account sibling. The vault stores blobs you can only
read yourself (symmetric, master-key); the dropbox *delivers* blobs to someone
else, end-to-end encrypted to their public key (see the ``identity`` attachment).

Flow for a single dropped file (all crypto in the client):
  1. the sender encrypts the file with a fresh random data key (secretstream),
     producing an opaque ciphertext blob content-addressed by SHA-256 — identical
     to the vault scheme;
  2. the sender builds a small metadata header ``{name, type, size, data_key,
     stream_header}`` and **seals it to the recipient's X25519 public key**
     (libsodium ``crypto_box_seal``) → ``sealed_meta``;
  3. the sender POSTs ``to`` + the ciphertext + ``sealed_meta`` here.

The server then opens an :meth:`account_scope` for the recipient and writes the
blob into the recipient's *isolated* storage tree plus one ``items`` row. So the
file physically lands in the recipient's own dropbox; only the recipient's secret
key (unlocked by their vault master key) can open ``sealed_meta`` to get the data
key and decrypt the blob. The Pi stores only ciphertext + a sealed header it can't
read.

The same delivery path is reused by the ``chat`` app for media messages
(``source='chat'``), so received chat media also shows up here, filterable by the
sending account — one drop box for everything you receive, per your design.

Per-account isolated: tables + blob dirs resolve to the *recipient* account during
delivery (via ``account_scope``) and to the *requesting* account when listing or
downloading your own inbox.

Authenticity note: sealed boxes are anonymous; the ``from`` recorded on each item
is asserted by the server from the sender's authenticated session, not proven by
the crypto. Fine for this single-operator, mutually-trusting Pi.
"""

from __future__ import annotations

import hashlib
import json
import re
import time
from pathlib import Path
from typing import Any

from fastapi import APIRouter, Depends, Form, HTTPException, Query, UploadFile
from fastapi.responses import StreamingResponse

from raspy.core.auth.deps import require_auth, Principal
from raspy.core.contract import AttachmentContext, BaseAttachment

_HASH_RE = re.compile(r"^[0-9a-f]{64}$")
_CHUNK = 256 * 1024
_MAX_BLOB = 2 * 1024 * 1024 * 1024  # 2 GiB hard cap per blob
_MAX_META = 64 * 1024  # sealed metadata header is tiny; cap defensively
_SOURCES = {"drop", "chat"}


def _validate_hash(h: str) -> str:
    if not _HASH_RE.match(h):
        raise HTTPException(400, "invalid blob hash")
    return h


class Dropbox(BaseAttachment):
    id = "dropbox"
    title = "Dropbox"
    icon = "inbox"
    version = "1.0.0"

    async def on_load(self, ctx: AttachmentContext) -> None:
        # Per-account tables are created lazily in _ensure() — their names depend on
        # which account's scope is active, unknown at load time.
        self._ready: set[str] = set()

    # --- per-account storage (resolved against the ACTIVE scope) -------------

    async def _ensure(self) -> str:
        """Create the active account's items table on first touch; return its
        name. Works for both the requester's own scope and a recipient scope
        entered via account_scope()."""
        t = self.db.table("items")
        if t not in self._ready:
            await self.db.execute(
                f"""
                CREATE TABLE IF NOT EXISTS {t} (
                    id          INTEGER PRIMARY KEY AUTOINCREMENT,
                    sender      TEXT NOT NULL,
                    source      TEXT NOT NULL DEFAULT 'drop',
                    blob_hash   TEXT NOT NULL,
                    size        INTEGER NOT NULL,
                    -- metadata header (name/type/data-key/stream-header) sealed to
                    -- the recipient's public key; opaque to the Pi.
                    sealed_meta TEXT NOT NULL,
                    created     REAL NOT NULL
                )
                """
            )
            await self.db.execute(
                f"CREATE INDEX IF NOT EXISTS {t}_sender ON {t} (sender, created)"
            )
            self._ready.add(t)
        return t

    def _blob_dir(self) -> Path:
        d = self.account_data_dir / "blobs"
        d.mkdir(parents=True, exist_ok=True)
        return d

    def _blob_path(self, h: str) -> Path:
        sub = self._blob_dir() / h[:2]
        sub.mkdir(parents=True, exist_ok=True)
        return sub / h

    async def _resolve_recipient(self, username: str) -> tuple[str, bool]:
        """Return ``(username, is_admin)`` for a valid recipient, else 404/400."""
        accounts = await self.ctx.list_accounts()
        for a in accounts:
            if a["username"] == username:
                return username, (a.get("role", "admin") == "admin")
        raise HTTPException(404, "unknown recipient account")

    def _row_api(self, row: dict[str, Any]) -> dict[str, Any]:
        return {
            "id": row["id"],
            "from": row["sender"],
            "source": row["source"],
            "hash": row["blob_hash"],
            "size": row["size"],
            "sealed_meta": row["sealed_meta"],
            "created": row["created"],
        }

    # --- delivery (shared with chat) -----------------------------------------

    async def deliver(
        self,
        *,
        recipient: str,
        sender: str,
        ciphertext: bytes,
        sealed_meta: str,
        source: str,
    ) -> dict[str, Any]:
        """Write a sealed blob + item row into the recipient's isolated store.

        Reusable by the chat attachment for media messages. Runs inside the
        recipient's account_scope so storage resolves to *their* tree. Returns the
        created item (recipient-scoped view).
        """
        if source not in _SOURCES:
            raise HTTPException(400, "invalid source")
        if not sealed_meta or len(sealed_meta) > _MAX_META:
            raise HTTPException(400, "invalid sealed metadata")
        if not ciphertext:
            raise HTTPException(400, "empty blob")
        if len(ciphertext) > _MAX_BLOB:
            raise HTTPException(413, "blob too large")

        h = hashlib.sha256(ciphertext).hexdigest()
        _, is_admin = await self._resolve_recipient(recipient)
        with self.ctx.account_scope(recipient, is_admin=is_admin):
            t = await self._ensure()
            path = self._blob_path(h)
            if not path.is_file():
                tmp = path.with_suffix(".tmp")
                tmp.write_bytes(ciphertext)
                tmp.replace(path)
            now = time.time()
            new_id = await self.db.execute_insert(
                f"INSERT INTO {t} (sender, source, blob_hash, size, sealed_meta, created) "
                f"VALUES (?, ?, ?, ?, ?, ?)",
                (sender, source, h, len(ciphertext), sealed_meta, now),
            )
            created = {
                "id": new_id,
                "sender": sender,
                "source": source,
                "blob_hash": h,
                "size": len(ciphertext),
                "sealed_meta": sealed_meta,
                "created": now,
            }
        # Notify the recipient (their WS subscription filters by topic). Published
        # outside the scope — the event bus is global.
        self.events.publish(
            "dropbox.received",
            {"to": recipient, "from": sender, "source": source, "hash": h},
        )
        return created

    def router(self) -> APIRouter:
        r = APIRouter()

        @r.post("/send", status_code=201)
        async def send(  # noqa: B008
            file: UploadFile = ...,
            to: str = Form(...),
            sealed_meta: str = Form(...),
            source: str = Form("drop"),
            principal: Principal = Depends(require_auth),
        ) -> dict[str, Any]:
            """Drop an encrypted file onto another account. ``file`` is opaque
            ciphertext; ``sealed_meta`` is the metadata header sealed to the
            recipient's public key; ``to`` is the recipient username."""
            data = await file.read()
            created = await self.deliver(
                recipient=to,
                sender=principal.username,
                ciphertext=data,
                sealed_meta=sealed_meta,
                source=source,
            )
            return self._row_api(created)

        @r.get("/items")
        async def list_items(
            sender: str | None = Query(None, alias="from"),
            limit: int = Query(default=50, ge=1, le=500),
            offset: int = Query(default=0, ge=0),
        ) -> list[dict[str, Any]]:
            """My inbox: everything dropped to me, newest first, paginated.

            Optional ``from`` filters to one sending account (the See-page pill
            bar). ``limit``/``offset`` page through by timestamp (mail-app style);
            the ordering is deterministic (created, then id) so page boundaries are
            stable. Filename search happens client-side — names live inside the
            sealed metadata the Pi can't read."""
            t = await self._ensure()
            where = ""
            params: list[Any] = []
            if sender:
                where = "WHERE sender = ?"
                params.append(sender)
            params.extend([limit, offset])
            rows = await self.db.fetch_all(
                f"SELECT * FROM {t} {where} ORDER BY created DESC, id DESC "
                f"LIMIT ? OFFSET ?",
                params,
            )
            return [self._row_api(row) for row in rows]

        @r.get("/senders")
        async def senders() -> list[dict[str, Any]]:
            """Distinct accounts that have dropped something to me, with counts —
            powers the 'see all media from account X' filter."""
            t = await self._ensure()
            return await self.db.fetch_all(
                f"SELECT sender AS \"from\", COUNT(*) AS count, MAX(created) AS last "
                f"FROM {t} GROUP BY sender ORDER BY last DESC"
            )

        @r.get("/blob/{blob_hash}")
        async def get_blob(blob_hash: str) -> StreamingResponse:
            """Stream one of MY received ciphertext blobs back for decryption."""
            t = await self._ensure()
            h = _validate_hash(blob_hash)
            # Only serve blobs that belong to an item in my own inbox.
            row = await self.db.fetch_one(
                f"SELECT size FROM {t} WHERE blob_hash = ? LIMIT 1", (h,)
            )
            if row is None:
                raise HTTPException(404, "blob not found")
            path = self._blob_path(h)
            if not path.is_file():
                raise HTTPException(404, "blob not found")

            def _iter():
                with path.open("rb") as fh:
                    while True:
                        chunk = fh.read(_CHUNK)
                        if not chunk:
                            break
                        yield chunk

            return StreamingResponse(
                _iter(),
                media_type="application/octet-stream",
                headers={"Content-Length": str(row["size"])},
            )

        @r.delete("/item/{item_id}", status_code=204)
        async def delete_item(item_id: int) -> None:
            """Remove an item from my inbox (and GC its blob if unreferenced)."""
            t = await self._ensure()
            row = await self.db.fetch_one(
                f"SELECT blob_hash FROM {t} WHERE id = ?", (item_id,)
            )
            if row is None:
                raise HTTPException(404, "item not found")
            await self.db.execute(f"DELETE FROM {t} WHERE id = ?", (item_id,))
            still = await self.db.fetch_one(
                f"SELECT 1 AS x FROM {t} WHERE blob_hash = ? LIMIT 1",
                (row["blob_hash"],),
            )
            if still is None:
                self._blob_path(row["blob_hash"]).unlink(missing_ok=True)
            self.events.publish("dropbox.changed", {"what": "item", "id": item_id})

        return r

    def ui(self) -> dict[str, Any]:
        from raspy.core import ui

        return ui.view(title="Dropbox", children=[ui.dropbox()])


attachment = Dropbox()

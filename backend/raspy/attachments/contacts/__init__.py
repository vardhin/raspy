"""Contacts — a personal address book + a "keep in touch" reminder list.

Each contact carries plaintext fields (name, description, phone, email, address)
and any number of **end-to-end-encrypted** photos. The encryption is identical to
the ``calendar`` / ``vault`` scheme: photos are content-addressed blobs (SHA-256 of
the *ciphertext*) and the per-image data key is sealed under the vault master key
(``key_wrapped``) — the Pi only ever stores opaque ciphertext plus a wrapped key it
cannot open. The text fields stay plaintext so the list/accordion can render names
without the vault being unlocked.

Two views live in one app (the frontend ships the topbar):
  * "Keep in touch" — an accordion of names, so you remember to call people.
  * "All contacts" — the full directory with photos + every field.

Per-account isolated: tables + blob dirs resolve to the requesting account.
"""

from __future__ import annotations

import hashlib
import time
from pathlib import Path
from typing import Any

from fastapi import APIRouter, HTTPException, Query, Response, UploadFile
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field

from raspy.core import ui
from raspy.core.contract import AttachmentContext, BaseAttachment

_MAX_IMAGE = 25 * 1024 * 1024  # 25 MiB per photo


def _hash_bytes(b: bytes) -> str:
    return hashlib.sha256(b).hexdigest()


class ContactCreate(BaseModel):
    name: str = Field(min_length=1, max_length=200)
    description: str = Field(default="", max_length=10_000)
    phone: str = Field(default="", max_length=200)
    email: str = Field(default="", max_length=320)
    address: str = Field(default="", max_length=2_000)
    keep_in_touch: bool = Field(default=False)


class ContactUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=200)
    description: str | None = Field(default=None, max_length=10_000)
    phone: str | None = Field(default=None, max_length=200)
    email: str | None = Field(default=None, max_length=320)
    address: str | None = Field(default=None, max_length=2_000)
    keep_in_touch: bool | None = Field(default=None)


class Contacts(BaseAttachment):
    id = "contacts"
    title = "Contacts"
    icon = "contact"
    version = "1.0.0"

    async def on_load(self, ctx: AttachmentContext) -> None:
        # Per-account tables are created lazily in _ensure() — their names depend on
        # who is asking (per-account isolation), unknown at load time.
        self._ready: set[str] = set()

    # --- per-account storage (resolved at request time) ---------------------

    async def _ensure(self) -> tuple[str, str]:
        """Create this account's contacts tables on first touch; return
        ``(contacts_table, images_table)``."""
        c = self.db.table("contacts")
        img = self.db.table("images")
        if c in self._ready:
            return c, img
        await self.db.execute(
            f"""
            CREATE TABLE IF NOT EXISTS {c} (
                id          INTEGER PRIMARY KEY AUTOINCREMENT,
                name        TEXT NOT NULL,
                description TEXT NOT NULL DEFAULT '',
                phone       TEXT NOT NULL DEFAULT '',
                email       TEXT NOT NULL DEFAULT '',
                address     TEXT NOT NULL DEFAULT '',
                keep_in_touch INTEGER NOT NULL DEFAULT 0,
                created     REAL NOT NULL,
                updated     REAL NOT NULL
            )
            """
        )
        await self.db.execute(f"CREATE INDEX IF NOT EXISTS {c}_name ON {c} (name)")
        # Migration: add keep_in_touch to tables created before this column existed.
        cols = await self.db.fetch_all(f"PRAGMA table_info({c})")
        if not any(col["name"] == "keep_in_touch" for col in cols):
            await self.db.execute(
                f"ALTER TABLE {c} ADD COLUMN keep_in_touch INTEGER NOT NULL DEFAULT 0"
            )
        await self.db.execute(
            f"""
            CREATE TABLE IF NOT EXISTS {img} (
                id            INTEGER PRIMARY KEY AUTOINCREMENT,
                contact_id    INTEGER NOT NULL,
                hash          TEXT NOT NULL,
                mime          TEXT NOT NULL,
                ord           INTEGER NOT NULL DEFAULT 0,
                created       REAL NOT NULL,
                -- E2E encryption material: the blob is ciphertext; key_wrapped is the
                -- per-image data key sealed under the master key, header is the
                -- secretstream header (not secret).
                key_wrapped   TEXT,
                nonce_wrapped TEXT,
                header        TEXT,
                -- Exactly one image per contact has cover=1; it's the one shown in
                -- minimized/avatar/card views. Falls back to lowest ord when unset.
                cover         INTEGER NOT NULL DEFAULT 0
            )
            """
        )
        await self.db.execute(
            f"CREATE INDEX IF NOT EXISTS {img}_contact ON {img} (contact_id, ord)"
        )
        # Migration: add cover to image tables created before this column existed.
        icols = await self.db.fetch_all(f"PRAGMA table_info({img})")
        if not any(col["name"] == "cover" for col in icols):
            await self.db.execute(
                f"ALTER TABLE {img} ADD COLUMN cover INTEGER NOT NULL DEFAULT 0"
            )
        self._ready.add(c)
        return c, img

    def _blob_dir(self) -> Path:
        d = self.account_data_dir / "photos"
        d.mkdir(parents=True, exist_ok=True)
        return d

    def _blob_path(self, h: str) -> Path:
        # Shard by first 2 hex chars to avoid one huge directory.
        sub = self._blob_dir() / h[:2]
        sub.mkdir(parents=True, exist_ok=True)
        return sub / h

    # --- shaping -------------------------------------------------------------

    async def _images_for(self, contact_id: int) -> list[dict[str, Any]]:
        img = self.db.table("images")
        rows = await self.db.fetch_all(
            f"SELECT id, hash, mime, ord, key_wrapped, nonce_wrapped, header, cover "
            f"FROM {img} WHERE contact_id = ? ORDER BY ord, id",
            (contact_id,),
        )
        for row in rows:
            row["url"] = f"image/{row['hash']}"
            # `enc` tells the client whether to decrypt (always true for new rows).
            row["enc"] = bool(row.get("key_wrapped"))
            row["cover"] = bool(row.get("cover"))
        return rows

    async def _ensure_cover(self, contact_id: int) -> None:
        """Guarantee a contact with images has exactly one cover: if none is flagged
        (e.g. the cover was deleted, or these are the first photos), promote the
        lowest-ord image. No-op for contacts with no photos."""
        img = self.db.table("images")
        has = await self.db.fetch_one(
            f"SELECT 1 AS x FROM {img} WHERE contact_id = ? AND cover = 1 LIMIT 1",
            (contact_id,),
        )
        if has is not None:
            return
        first = await self.db.fetch_one(
            f"SELECT id FROM {img} WHERE contact_id = ? ORDER BY ord, id LIMIT 1",
            (contact_id,),
        )
        if first is not None:
            await self.db.execute(
                f"UPDATE {img} SET cover = 1 WHERE id = ?", (first["id"],)
            )

    async def _contact_api(self, row: dict[str, Any], *, with_images: bool = True) -> dict[str, Any]:
        out = {
            "id": row["id"],
            "name": row["name"],
            "description": row["description"],
            "phone": row["phone"],
            "email": row["email"],
            "address": row["address"],
            "keep_in_touch": bool(row["keep_in_touch"]),
            "created": row["created"],
            "updated": row["updated"],
        }
        if with_images:
            out["images"] = await self._images_for(row["id"])
        return out

    # --- API -----------------------------------------------------------------

    def router(self) -> APIRouter:
        r = APIRouter()

        async def _row(contact_id: int) -> dict[str, Any]:
            c, _ = await self._ensure()
            row = await self.db.fetch_one(f"SELECT * FROM {c} WHERE id = ?", (contact_id,))
            if row is None:
                raise HTTPException(404, "contact not found")
            return row

        @r.get("/contacts")
        async def list_contacts() -> list[dict[str, Any]]:
            """All contacts, name-sorted, each with its photos. The text fields are
            plaintext so the list renders even when the vault is locked."""
            c, _ = await self._ensure()
            rows = await self.db.fetch_all(
                f"SELECT * FROM {c} ORDER BY name COLLATE NOCASE, id"
            )
            return [await self._contact_api(row) for row in rows]

        @r.get("/contacts/{contact_id}")
        async def get_contact(contact_id: int) -> dict[str, Any]:
            return await self._contact_api(await _row(contact_id))

        @r.post("/contacts", status_code=201)
        async def create_contact(body: ContactCreate) -> dict[str, Any]:
            c, _ = await self._ensure()
            now = time.time()
            new_id = await self.db.execute_insert(
                f"INSERT INTO {c} (name, description, phone, email, address, "
                f"keep_in_touch, created, updated) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                (
                    body.name.strip(),
                    body.description,
                    body.phone.strip(),
                    body.email.strip(),
                    body.address.strip(),
                    int(body.keep_in_touch),
                    now,
                    now,
                ),
            )
            self.events.publish("contacts.changed", {"id": new_id})
            return await self._contact_api(await _row(new_id))

        @r.patch("/contacts/{contact_id}")
        async def update_contact(contact_id: int, body: ContactUpdate) -> dict[str, Any]:
            c, _ = await self._ensure()
            await _row(contact_id)
            sets: list[str] = []
            params: list[Any] = []
            for field_, value in (
                ("name", body.name),
                ("description", body.description),
                ("phone", body.phone),
                ("email", body.email),
                ("address", body.address),
            ):
                if value is not None:
                    sets.append(f"{field_} = ?")
                    params.append(value.strip() if field_ != "description" else value)
            if body.keep_in_touch is not None:
                sets.append("keep_in_touch = ?")
                params.append(int(body.keep_in_touch))
            if sets:
                sets.append("updated = ?")
                params.append(time.time())
                params.append(contact_id)
                await self.db.execute(
                    f"UPDATE {c} SET {', '.join(sets)} WHERE id = ?", params
                )
            self.events.publish("contacts.changed", {"id": contact_id})
            return await self._contact_api(await _row(contact_id))

        @r.delete("/contacts/{contact_id}", status_code=204)
        async def delete_contact(contact_id: int) -> None:
            c, img = await self._ensure()
            await _row(contact_id)
            imgs = await self.db.fetch_all(
                f"SELECT hash FROM {img} WHERE contact_id = ?", (contact_id,)
            )
            await self.db.execute(f"DELETE FROM {img} WHERE contact_id = ?", (contact_id,))
            await self.db.execute(f"DELETE FROM {c} WHERE id = ?", (contact_id,))
            # GC blobs no longer referenced by any image row.
            for row_img in imgs:
                await self._gc_blob(row_img["hash"])
            self.events.publish("contacts.changed", {"id": contact_id})

        # --- images ---------------------------------------------------------

        @r.post("/contacts/{contact_id}/images", status_code=201)
        async def add_image(  # noqa: B008
            contact_id: int,
            file: UploadFile = ...,
            mime: str = Query(...),
            key_wrapped: str = Query(...),
            nonce_wrapped: str = Query(...),
            header: str = Query(...),
        ) -> dict[str, Any]:
            """Store an end-to-end-encrypted photo. ``file`` is opaque *ciphertext*
            (the client encrypted it with a fresh data key); ``key_wrapped`` /
            ``nonce_wrapped`` seal that data key under the master key, ``header`` is
            the secretstream header, ``mime`` is the (plaintext) declared type. The
            blob is content-addressed by the SHA-256 of the ciphertext, verified
            here — the only crypto the Pi does."""
            c, img = await self._ensure()
            await _row(contact_id)
            data = await file.read()
            if not data:
                raise HTTPException(400, "empty file")
            if len(data) > _MAX_IMAGE:
                raise HTTPException(413, "image too large")
            mime = (mime or "").split(";")[0].strip().lower()
            if not mime.startswith("image/"):
                raise HTTPException(415, "expected an image mime type")
            h = _hash_bytes(data)  # hash of the ciphertext = storage key
            path = self._blob_path(h)
            if not path.is_file():
                tmp = path.with_suffix(".tmp")
                tmp.write_bytes(data)
                tmp.replace(path)
            nxt = await self.db.fetch_one(
                f"SELECT COALESCE(MAX(ord), -1) + 1 AS n FROM {img} WHERE contact_id = ?",
                (contact_id,),
            )
            ord_ = int((nxt or {}).get("n", 0))
            img_id = await self.db.execute_insert(
                f"INSERT INTO {img} (contact_id, hash, mime, ord, created, "
                f"key_wrapped, nonce_wrapped, header) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                (contact_id, h, mime, ord_, time.time(), key_wrapped, nonce_wrapped, header),
            )
            # The very first photo becomes the cover automatically.
            await self._ensure_cover(contact_id)
            cover_row = await self.db.fetch_one(
                f"SELECT cover FROM {img} WHERE id = ?", (img_id,)
            )
            self.events.publish("contacts.changed", {"id": contact_id})
            return {
                "id": img_id,
                "hash": h,
                "mime": mime,
                "ord": ord_,
                "url": f"image/{h}",
                "enc": True,
                "key_wrapped": key_wrapped,
                "nonce_wrapped": nonce_wrapped,
                "header": header,
                "cover": bool((cover_row or {}).get("cover")),
            }

        @r.patch("/images/{image_id}/cover", status_code=204)
        async def set_cover(image_id: int) -> None:
            """Make this image the contact's cover; clears the flag on its siblings."""
            _, img = await self._ensure()
            row = await self.db.fetch_one(
                f"SELECT contact_id FROM {img} WHERE id = ?", (image_id,)
            )
            if row is None:
                raise HTTPException(404, "image not found")
            cid = row["contact_id"]
            await self.db.execute(
                f"UPDATE {img} SET cover = 0 WHERE contact_id = ?", (cid,)
            )
            await self.db.execute(f"UPDATE {img} SET cover = 1 WHERE id = ?", (image_id,))
            self.events.publish("contacts.changed", {"id": cid})

        @r.delete("/images/{image_id}", status_code=204)
        async def delete_image(image_id: int) -> None:
            _, img = await self._ensure()
            row = await self.db.fetch_one(
                f"SELECT contact_id, hash FROM {img} WHERE id = ?", (image_id,)
            )
            if row is None:
                raise HTTPException(404, "image not found")
            await self.db.execute(f"DELETE FROM {img} WHERE id = ?", (image_id,))
            await self._gc_blob(row["hash"])
            # If the cover was the one removed, promote another image.
            await self._ensure_cover(row["contact_id"])
            self.events.publish("contacts.changed", {"id": row["contact_id"]})

        @r.patch("/contacts/{contact_id}/images/order", status_code=204)
        async def reorder_images(contact_id: int, body: dict[str, list[int]]) -> None:
            """Body: {"order": [imageId, imageId, …]} in the desired display order."""
            _, img = await self._ensure()
            await _row(contact_id)
            order = body.get("order", [])
            for i, image_id in enumerate(order):
                await self.db.execute(
                    f"UPDATE {img} SET ord = ? WHERE id = ? AND contact_id = ?",
                    (i, image_id, contact_id),
                )
            self.events.publish("contacts.changed", {"id": contact_id})

        @r.get("/image/{blob_hash}")
        async def get_image(blob_hash: str) -> Response:
            if not all(ch in "0123456789abcdef" for ch in blob_hash) or len(blob_hash) != 64:
                raise HTTPException(400, "invalid hash")
            _, img = await self._ensure()
            path = self._blob_path(blob_hash)
            if not path.is_file():
                raise HTTPException(404, "image not found")
            row = await self.db.fetch_one(
                f"SELECT mime, key_wrapped FROM {img} WHERE hash = ? LIMIT 1", (blob_hash,)
            )
            # Encrypted blobs are opaque ciphertext — serve octet-stream and let the
            # client decrypt. Legacy plaintext rows (none yet) keep their real mime.
            if row and row.get("key_wrapped"):
                return FileResponse(path, media_type="application/octet-stream")
            mime = (row or {}).get("mime", "application/octet-stream")
            return FileResponse(path, media_type=mime)

        return r

    async def _gc_blob(self, h: str) -> None:
        img = self.db.table("images")
        still = await self.db.fetch_one(
            f"SELECT 1 AS x FROM {img} WHERE hash = ? LIMIT 1", (h,)
        )
        if still is None:
            self._blob_path(h).unlink(missing_ok=True)

    def ui(self) -> dict[str, Any]:
        return ui.view(title="Contacts", children=[ui.contacts()])


attachment = Contacts()

"""Vault — a zero-knowledge encrypted store (plan/shiny-painting-flask, Layer 2).

The Pi is a DUMB blob store. It never sees a plaintext filename, type, or byte:
everything is encrypted in the client (browser/Flutter) with the vault master key
(derived from the password, never sent here). This attachment only:

  * stores content-addressed encrypted blobs (key = SHA-256 of the *ciphertext*),
    verifying the hash on write so the store stays consistent — a cheap hash, the
    only "crypto" the Pi does;
  * stores ONE opaque encrypted manifest blob (the file list lives inside it,
    encrypted — the server can't read names/types);
  * streams blobs back for download with a progress bar on the client.

Blobs are written to the attachment data dir as files named by their hash; an
index table tracks size/created for listing + GC. Large blobs are streamed
straight over HTTP (they're already E2E-encrypted, so the Layer-1 channel is
intentionally bypassed for them — see frontend bypassChannel()).
"""

from __future__ import annotations

import hashlib
import re
import time
from pathlib import Path
from typing import Any

from fastapi import APIRouter, HTTPException, Request, Response
from fastapi.responses import StreamingResponse

from raspy.core.contract import AttachmentContext, BaseAttachment
from raspy.core import ui

_HASH_RE = re.compile(r"^[0-9a-f]{64}$")
_MANIFEST_NAME = "manifest.bin"
_CHUNK = 256 * 1024  # streaming read size
_MAX_BLOB = 2 * 1024 * 1024 * 1024  # 2 GiB hard cap per blob


def _validate_hash(h: str) -> str:
    if not _HASH_RE.match(h):
        raise HTTPException(400, "invalid blob hash")
    return h


class Vault(BaseAttachment):
    id = "vault"
    title = "Vault"
    icon = "lock"
    version = "1.0.0"

    _dir: Path

    async def on_load(self, ctx: AttachmentContext) -> None:
        self._dir = ctx.data_dir / "blobs"
        self._dir.mkdir(parents=True, exist_ok=True)
        t = self.db.table("blobs")
        await self.db.execute(
            f"""
            CREATE TABLE IF NOT EXISTS {t} (
                hash    TEXT PRIMARY KEY,
                size    INTEGER NOT NULL,
                created REAL NOT NULL
            )
            """
        )

    # --- helpers -------------------------------------------------------------

    def _blob_path(self, h: str) -> Path:
        # Shard by first 2 hex chars to avoid one huge directory.
        sub = self._dir / h[:2]
        sub.mkdir(parents=True, exist_ok=True)
        return sub / h

    def router(self) -> APIRouter:
        r = APIRouter()
        t = self.db.table("blobs")
        manifest_path = self._dir.parent / _MANIFEST_NAME

        # --- manifest (one opaque encrypted blob) ---------------------------

        @r.get("/manifest")
        async def get_manifest() -> Response:
            if not manifest_path.is_file():
                # Empty vault — client treats 204 as "no manifest yet".
                return Response(status_code=204)
            return Response(manifest_path.read_bytes(), media_type="application/octet-stream")

        @r.put("/manifest", status_code=204)
        async def put_manifest(request: Request) -> None:
            data = await request.body()
            if len(data) > 50 * 1024 * 1024:
                raise HTTPException(413, "manifest too large")
            tmp = manifest_path.with_suffix(".tmp")
            tmp.write_bytes(data)
            tmp.replace(manifest_path)  # atomic
            self.events.publish("vault.changed", {"what": "manifest"})

        # --- blobs (content-addressed opaque ciphertext) --------------------

        @r.get("/blobs")
        async def list_blobs() -> list[dict[str, Any]]:
            """Hashes + sizes only — no content, no names (names are inside the
            encrypted manifest). Lets the client reconcile / GC."""
            return await self.db.fetch_all(f"SELECT hash, size, created FROM {t}")

        @r.put("/blob/{blob_hash}", status_code=201)
        async def put_blob(blob_hash: str, request: Request) -> dict[str, Any]:
            h = _validate_hash(blob_hash)
            path = self._blob_path(h)
            # Stream to a temp file while hashing, so we never hold a huge blob in
            # memory and can reject a hash mismatch (corruption / wrong client).
            hasher = hashlib.sha256()
            size = 0
            tmp = path.with_suffix(".tmp")
            with tmp.open("wb") as fh:
                async for chunk in request.stream():
                    size += len(chunk)
                    if size > _MAX_BLOB:
                        fh.close()
                        tmp.unlink(missing_ok=True)
                        raise HTTPException(413, "blob too large")
                    hasher.update(chunk)
                    fh.write(chunk)
            if hasher.hexdigest() != h:
                tmp.unlink(missing_ok=True)
                raise HTTPException(400, "content hash mismatch")
            tmp.replace(path)
            await self.db.execute(
                f"INSERT INTO {t} (hash, size, created) VALUES (?, ?, ?) "
                f"ON CONFLICT(hash) DO NOTHING",
                (h, size, time.time()),
            )
            return {"hash": h, "size": size}

        @r.get("/blob/{blob_hash}")
        async def get_blob(blob_hash: str) -> StreamingResponse:
            h = _validate_hash(blob_hash)
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

            row = await self.db.fetch_one(f"SELECT size FROM {t} WHERE hash = ?", (h,))
            headers = {"Content-Length": str(row["size"])} if row else {}
            # Opaque ciphertext; octet-stream + the client knows the real type from
            # the decrypted manifest.
            return StreamingResponse(
                _iter(), media_type="application/octet-stream", headers=headers
            )

        @r.delete("/blob/{blob_hash}", status_code=204)
        async def delete_blob(blob_hash: str) -> None:
            h = _validate_hash(blob_hash)
            self._blob_path(h).unlink(missing_ok=True)
            await self.db.execute(f"DELETE FROM {t} WHERE hash = ?", (h,))
            self.events.publish("vault.changed", {"what": "blob", "hash": h})

        return r

    def ui(self) -> dict[str, Any]:
        return ui.view(title="Vault", children=[ui.vault()])


attachment = Vault()

"""Passwords — a zero-knowledge password keeper with per-entry notes.

The Pi is a DUMB store, exactly like the ``vault``'s manifest (plan/30-auth-security
§zero-knowledge, plan/20-attachments). It holds **one opaque encrypted blob** per
account: the password list (titles, usernames, passwords, URLs, and a small note
per entry) lives entirely *inside* that blob, encrypted in the client under the
vault master key (derived from the password, never sent here). The server cannot
read a single field — it only stores and returns ciphertext.

There are no per-entry endpoints: add/edit/delete/reorder all happen client-side
by mutating the decrypted list and re-uploading the whole encrypted blob. That
keeps the contract trivial (GET/PUT one blob) and the design auditably
zero-knowledge — there's no plaintext field for the server to leak.

Per-account isolated: the blob lives under the requesting account's data dir, so
each account has its own keeper.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from fastapi import APIRouter, HTTPException, Request, Response

from raspy.core import ui
from raspy.core.contract import AttachmentContext, BaseAttachment

_STORE_NAME = "store.bin"
_MAX_STORE = 16 * 1024 * 1024  # 16 MiB — generous for a text-only password list


class Passwords(BaseAttachment):
    id = "passwords"
    title = "Passwords"
    icon = "key"
    version = "1.0.0"

    async def on_load(self, ctx: AttachmentContext) -> None:
        # No tables: the entire keeper is one opaque encrypted file per account.
        # Nothing to create up front.
        return None

    def _store_path(self) -> Path:
        # Per-account: account_data_dir resolves to the requesting account's tree.
        d = self.account_data_dir
        d.mkdir(parents=True, exist_ok=True)
        return d / _STORE_NAME

    def router(self) -> APIRouter:
        r = APIRouter()

        @r.get("/store")
        async def get_store() -> Response:
            """Return this account's opaque encrypted password blob, or 204 if the
            keeper is empty (client treats that as "no entries yet")."""
            path = self._store_path()
            if not path.is_file():
                return Response(status_code=204)
            return Response(
                path.read_bytes(), media_type="application/octet-stream"
            )

        @r.put("/store", status_code=204)
        async def put_store(request: Request) -> None:
            """Replace the encrypted blob. The body is opaque ciphertext (nonce ||
            secretbox), produced in the client under the master key — the server
            never inspects it. Written atomically so a crash can't truncate it."""
            data = await request.body()
            if len(data) > _MAX_STORE:
                raise HTTPException(413, "password store too large")
            path = self._store_path()
            tmp = path.with_suffix(".tmp")
            tmp.write_bytes(data)
            tmp.replace(path)  # atomic
            self.events.publish("passwords.changed", None)

        @r.delete("/store", status_code=204)
        async def delete_store() -> None:
            """Wipe the keeper entirely (e.g. a reset). Idempotent."""
            self._store_path().unlink(missing_ok=True)
            self.events.publish("passwords.changed", None)

        return r

    def ui(self) -> dict[str, Any]:
        return ui.view(title="Passwords", children=[ui.passwords()])


attachment = Passwords()

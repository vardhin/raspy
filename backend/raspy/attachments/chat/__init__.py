"""Chat — pick an account and exchange end-to-end-encrypted messages + media.

Each conversation is between two accounts. A message is stored on **both** sides
(one row in each account's isolated store) so each party has their own copy of the
thread, encrypted so only they can read it:

  * **text** — the body is sealed twice by the sender: once to the recipient's
    public key (``sealed`` on the recipient's row) and once to the sender's own
    public key (``sealed`` on the sender's row). Each side stores the version it
    can open; the Pi sees only ciphertext.
  * **media** — the actual bytes are NOT stored by chat. The client encrypts each
    image and delivers it through the **dropbox** (``source='chat'``) to both the
    recipient and the sender, so the media lands in each one's drop box (filterable
    by sender) exactly as the design requires. The chat message then just carries
    the sealed metadata referencing those blobs (hash + data key), so the
    conversation view can render the media inline as a clustered carousel.

So chat stays decoupled from dropbox at the backend (the client orchestrates the
two writes); chat itself only persists small sealed message rows.

``peer`` on each stored row is *the other account* from the row owner's point of
view, so ``conversation?with=<peer>`` and the thread list are a simple lookup.

Per-account isolated. Authenticity is server-asserted (sealed boxes are anonymous)
— fine for this single-operator Pi. See the ``identity`` attachment.
"""

from __future__ import annotations

import time
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field

from raspy.core.auth.deps import require_auth, Principal
from raspy.core.contract import AttachmentContext, BaseAttachment

_MAX_SEALED = 256 * 1024  # sealed text or media-manifest header; generous cap
_KINDS = {"text", "media"}


class SendMessage(BaseModel):
    """One message, pre-sealed by the client for both sides.

    ``sealed_for_recipient`` / ``sealed_for_self`` are the same logical payload
    (the text, or a media header listing blob hashes + data keys) encrypted to the
    recipient's and the sender's public keys respectively. For a media message the
    blobs themselves are already delivered via the dropbox before this call.
    """

    to: str = Field(min_length=1, max_length=320)
    kind: str = Field(default="text")
    sealed_for_recipient: str = Field(min_length=1, max_length=_MAX_SEALED)
    sealed_for_self: str = Field(min_length=1, max_length=_MAX_SEALED)


class Chat(BaseAttachment):
    id = "chat"
    title = "Chat"
    icon = "message-circle"
    version = "1.0.0"

    async def on_load(self, ctx: AttachmentContext) -> None:
        self._ready: set[str] = set()

    # --- per-account storage (resolved against the ACTIVE scope) -------------

    async def _ensure(self) -> str:
        t = self.db.table("messages")
        if t not in self._ready:
            await self.db.execute(
                f"""
                CREATE TABLE IF NOT EXISTS {t} (
                    id      INTEGER PRIMARY KEY AUTOINCREMENT,
                    peer    TEXT NOT NULL,         -- the OTHER account in this thread
                    sender  TEXT NOT NULL,         -- who wrote it (peer or me)
                    kind    TEXT NOT NULL DEFAULT 'text',
                    sealed  TEXT NOT NULL,         -- payload sealed to THIS row owner
                    created REAL NOT NULL
                )
                """
            )
            await self.db.execute(
                f"CREATE INDEX IF NOT EXISTS {t}_peer ON {t} (peer, created)"
            )
            self._ready.add(t)
        return t

    async def _resolve_account(self, username: str) -> bool:
        """Return is_admin for a known account, else 404."""
        for a in await self.ctx.list_accounts():
            if a["username"] == username:
                return a.get("role", "admin") == "admin"
        raise HTTPException(404, "unknown account")

    def _row_api(self, row: dict[str, Any], *, me: str) -> dict[str, Any]:
        return {
            "id": row["id"],
            "kind": row["kind"],
            "sealed": row["sealed"],
            "from": row["sender"],
            "mine": row["sender"] == me,
            "created": row["created"],
        }

    async def _insert(
        self,
        *,
        owner: str,
        is_admin: bool,
        peer: str,
        sender: str,
        kind: str,
        sealed: str,
    ) -> dict[str, Any]:
        """Insert one message row into ``owner``'s isolated store."""
        with self.ctx.account_scope(owner, is_admin=is_admin):
            t = await self._ensure()
            now = time.time()
            new_id = await self.db.execute_insert(
                f"INSERT INTO {t} (peer, sender, kind, sealed, created) "
                f"VALUES (?, ?, ?, ?, ?)",
                (peer, sender, kind, sealed, now),
            )
            return {
                "id": new_id,
                "peer": peer,
                "sender": sender,
                "kind": kind,
                "sealed": sealed,
                "created": now,
            }

    def router(self) -> APIRouter:
        r = APIRouter()

        @r.post("/send", status_code=201)
        async def send(
            body: SendMessage, principal: Principal = Depends(require_auth)
        ) -> dict[str, Any]:
            """Send a message. Writes the recipient's copy into their store and the
            sender's copy into theirs, each sealed to the respective reader."""
            me = principal.username
            if body.to == me:
                raise HTTPException(400, "cannot message yourself")
            if body.kind not in _KINDS:
                raise HTTPException(400, "invalid kind")
            recipient_is_admin = await self._resolve_account(body.to)
            me_is_admin = principal.is_admin

            # Recipient's copy (sealed to them); peer = me, sender = me.
            await self._insert(
                owner=body.to,
                is_admin=recipient_is_admin,
                peer=me,
                sender=me,
                kind=body.kind,
                sealed=body.sealed_for_recipient,
            )
            # My own copy (sealed to me); peer = recipient, sender = me.
            mine = await self._insert(
                owner=me,
                is_admin=me_is_admin,
                peer=body.to,
                sender=me,
                kind=body.kind,
                sealed=body.sealed_for_self,
            )

            self.events.publish(
                "chat.message", {"to": body.to, "from": me, "kind": body.kind}
            )
            return self._row_api(mine, me=me)

        @r.get("/conversation")
        async def conversation(
            peer: str = Query(..., alias="with"),
            principal: Principal = Depends(require_auth),
        ) -> list[dict[str, Any]]:
            """All messages between me and ``peer``, oldest first."""
            me = principal.username
            t = await self._ensure()
            rows = await self.db.fetch_all(
                f"SELECT * FROM {t} WHERE peer = ? ORDER BY created, id", (peer,)
            )
            return [self._row_api(row, me=me) for row in rows]

        @r.get("/threads")
        async def threads(
            principal: Principal = Depends(require_auth),
        ) -> list[dict[str, Any]]:
            """One entry per account I've talked to, newest activity first. The
            ``last`` sealed payload lets the list show a preview once decrypted."""
            me = principal.username
            t = await self._ensure()
            rows = await self.db.fetch_all(
                f"""
                SELECT m.peer AS peer, m.kind AS kind, m.sealed AS sealed,
                       m.sender AS sender, m.created AS created
                FROM {t} m
                JOIN (
                    SELECT peer, MAX(created) AS mx FROM {t} GROUP BY peer
                ) last ON last.peer = m.peer AND last.mx = m.created
                ORDER BY m.created DESC
                """
            )
            out: list[dict[str, Any]] = []
            seen: set[str] = set()
            for row in rows:
                if row["peer"] in seen:
                    continue
                seen.add(row["peer"])
                out.append(
                    {
                        "peer": row["peer"],
                        "last": {
                            "kind": row["kind"],
                            "sealed": row["sealed"],
                            "mine": row["sender"] == me,
                            "created": row["created"],
                        },
                    }
                )
            return out

        @r.delete("/conversation", status_code=204)
        async def clear_conversation(
            peer: str = Query(..., alias="with"),
            principal: Principal = Depends(require_auth),
        ) -> None:
            """Delete MY copy of a conversation (the peer keeps theirs)."""
            t = await self._ensure()
            await self.db.execute(f"DELETE FROM {t} WHERE peer = ?", (peer,))
            self.events.publish("chat.changed", {"with": peer})

        return r

    def ui(self) -> dict[str, Any]:
        from raspy.core import ui

        return ui.view(title="Chat", children=[ui.chat()])


attachment = Chat()

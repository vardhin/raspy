"""Identity — the per-account public-key directory that makes cross-account E2E
messaging possible.

The vault is zero-knowledge: every account has only a *symmetric* master key
derived from its password, which the Pi never sees. That is great for "my own
encrypted store" but useless for "send something only account B can read" —
account A doesn't know B's master key and never can.

So each account also gets an **X25519 keypair** (libsodium ``crypto_box`` /
``crypto_box_seal``):

  * **public key** — stored here in plaintext, readable by *every* account. Anyone
    can encrypt *to* you with an anonymous sealed box.
  * **secret key** — generated in the client, wrapped (``crypto_secretbox``) under
    that account's own vault master key, and stored here as opaque ciphertext. The
    Pi holds it but cannot open it; only the owner, once the vault is unlocked,
    unwraps it to *read* what was sealed to them.

This attachment is a flat **directory** — one row per account, not per-account
isolated storage — because the whole point is that accounts can look each other's
public keys up. The owning account for a write is the request Principal, so an
account can only ever publish/replace *its own* keypair.

A sender never learns the recipient's secret key; the recipient never needs the
sender's password. The Pi stays a dumb store of ciphertext + public material.

Note on authenticity: sealed boxes are *anonymous* — the recipient cannot
cryptographically prove who sent a blob. The ``from`` shown in the UI is asserted
by the server from the sender's authenticated session. That is acceptable for this
single-operator Pi where every account is yours and mutually trusted; it is not a
defence against a compromised server. See plan/30-auth-security.md.

This app is a backend utility: it ships no sidebar UI (``ui()`` returns None) and
is excluded from manifests like other non-app services.
"""

from __future__ import annotations

import time
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, Field

from raspy.core.auth.deps import require_auth, Principal
from raspy.core.contract import AttachmentContext, BaseAttachment

# One flat, global directory table (NOT per-account-scoped): the directory is
# meant to be shared so accounts can resolve each other's public keys.
_TABLE = "att_identity_keys"

# X25519 public key is 32 bytes -> 44 chars base64; wrapped secret key + nonce are
# small. Generous caps just to reject obviously bogus input.
_MAX_FIELD = 4096


class PublishKeys(BaseModel):
    """The client generates the keypair, wraps the secret key under its vault
    master key, and publishes this once (idempotently)."""

    public_key: str = Field(min_length=1, max_length=_MAX_FIELD)  # b64 X25519 pk
    sk_wrapped: str = Field(min_length=1, max_length=_MAX_FIELD)  # b64 secretbox(sk)
    sk_nonce: str = Field(min_length=1, max_length=_MAX_FIELD)  # b64 secretbox nonce


class Identity(BaseAttachment):
    id = "identity"
    title = "Identity"
    icon = "key"
    version = "1.0.0"

    async def on_load(self, ctx: AttachmentContext) -> None:
        # Global directory table — created once, keyed by username. We touch the
        # raw db directly (not self.db.table) so the name is stable regardless of
        # which account is asking.
        await ctx.db.execute(
            f"""
            CREATE TABLE IF NOT EXISTS {_TABLE} (
                username    TEXT PRIMARY KEY,
                public_key  TEXT NOT NULL,
                -- The owner's secret key, sealed under their OWN vault master key.
                -- Opaque to the Pi; only the owner can unwrap it client-side.
                sk_wrapped  TEXT NOT NULL,
                sk_nonce    TEXT NOT NULL,
                created     REAL NOT NULL,
                updated     REAL NOT NULL
            )
            """
        )

    def router(self) -> APIRouter:
        r = APIRouter()

        @r.get("/keys")
        async def list_keys() -> list[dict[str, Any]]:
            """The public directory: every account that has published a key, with
            its public key only (no wrapped secret). This is the source for the
            account picker in the dropbox/chat apps."""
            accounts = await self.ctx.list_accounts()
            roles = {a["username"]: a.get("role", "admin") for a in accounts}
            rows = await self.db.fetch_all(
                f"SELECT username, public_key, created FROM {_TABLE} ORDER BY username"
            )
            return [
                {
                    "username": row["username"],
                    "public_key": row["public_key"],
                    "role": roles.get(row["username"], "admin"),
                }
                for row in rows
            ]

        @r.get("/key/{username}")
        async def get_key(username: str) -> dict[str, Any]:
            """One account's public key, for encrypting to it."""
            row = await self.db.fetch_one(
                f"SELECT username, public_key FROM {_TABLE} WHERE username = ?",
                (username,),
            )
            if row is None:
                raise HTTPException(404, "no published key for that account")
            return {"username": row["username"], "public_key": row["public_key"]}

        @r.get("/me")
        async def get_me(principal: Principal = Depends(require_auth)) -> Any:
            """My own keypair material (public key + wrapped secret key) so the
            client can recover its secret key after a reload. 204 if I haven't
            published yet."""
            row = await self.db.fetch_one(
                f"SELECT public_key, sk_wrapped, sk_nonce FROM {_TABLE} WHERE username = ?",
                (principal.username,),
            )
            if row is None:
                # FastAPI: returning None with default 200 would send "null"; use an
                # explicit 204 the client treats as "not published".
                from fastapi import Response

                return Response(status_code=204)
            return {
                "public_key": row["public_key"],
                "sk_wrapped": row["sk_wrapped"],
                "sk_nonce": row["sk_nonce"],
            }

        @r.put("/me", status_code=204)
        async def put_me(
            body: PublishKeys, principal: Principal = Depends(require_auth)
        ) -> None:
            """Publish (or replace) *my* keypair. Keyed by the authenticated
            principal, so an account can only ever write its own row.

            Replacing a key is allowed (e.g. password reset re-wraps the secret),
            but note: anything previously sealed to the OLD public key becomes
            unreadable if the secret key itself changed. The client keeps the same
            keypair across password changes by re-wrapping the *same* secret key
            under the new master key — see frontend identity.ts."""
            now = time.time()
            await self.db.execute(
                f"""
                INSERT INTO {_TABLE} (username, public_key, sk_wrapped, sk_nonce, created, updated)
                VALUES (?, ?, ?, ?, ?, ?)
                ON CONFLICT(username) DO UPDATE SET
                    public_key = excluded.public_key,
                    sk_wrapped = excluded.sk_wrapped,
                    sk_nonce   = excluded.sk_nonce,
                    updated    = excluded.updated
                """,
                (
                    principal.username,
                    body.public_key,
                    body.sk_wrapped,
                    body.sk_nonce,
                    now,
                    now,
                ),
            )

        return r

    def ui(self) -> None:
        # Backend utility — no sidebar app.
        return None


attachment = Identity()

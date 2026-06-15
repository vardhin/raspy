"""Accounts — the admin-only account management app.

The master admin (the single original account) uses this to create and manage
*child* accounts: each child gets its own isolated apps (vault/calendar/notes/…),
chosen from a per-account permission checklist. Account creation hands the child
a temp password + PIN; the child is frozen until it resets both on first sign-in.

The real work lives in the core auth admin endpoints (``/api/auth/admin/*``,
gated by ``require_admin``); this attachment is mostly the UI descriptor. Its own
router is also admin-gated so a child can never reach it even by guessing the URL,
and it is excluded from children's manifests (see core/manifest.py ``_ADMIN_ONLY``).
"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends

from raspy.core import ui
from raspy.core.auth.deps import require_admin
from raspy.core.contract import AttachmentContext, BaseAttachment


class Accounts(BaseAttachment):
    id = "accounts"
    title = "Accounts"
    icon = "users"
    version = "1.0.0"

    async def on_load(self, ctx: AttachmentContext) -> None:
        # No storage of its own — it drives the core auth account tables via the
        # admin endpoints.
        pass

    def router(self) -> APIRouter:
        # Admin-only at the router level too (defence in depth on top of the
        # manifest filter). A single dependency on the whole router 403s any
        # non-admin that reaches /api/att/accounts/*.
        return APIRouter(dependencies=[Depends(require_admin)])

    def ui(self) -> dict[str, Any]:
        return ui.view(title="Accounts", children=[ui.accounts()])


attachment = Accounts()

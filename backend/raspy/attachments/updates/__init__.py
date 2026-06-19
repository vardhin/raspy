"""Updates — the admin-only self-update app.

A UI for the core updater (``core/updater.py`` + ``core/update_routes.py``): shows
the current version, checks for updates, lists every published GitHub release with
its notes, and installs *any* version — upgrade or rollback — with a one-click
download-verify-swap-restart. Also exposes the periodic auto-check toggle.

Like ``accounts``, this is mostly a UI descriptor: the real work lives in the
admin-gated ``/api/update/*`` core endpoints. Its own router is admin-gated too
(defence in depth) and it is excluded from children's manifests (see
``core/manifest.py`` ``_ADMIN_ONLY``).
"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends

from raspy.core import ui
from raspy.core.auth.deps import require_admin
from raspy.core.contract import AttachmentContext, BaseAttachment


class Updates(BaseAttachment):
    id = "updates"
    title = "Updates"
    icon = "refresh-cw"
    version = "1.0.0"

    async def on_load(self, ctx: AttachmentContext) -> None:
        # No storage of its own — it drives the core updater via /api/update/*.
        pass

    def router(self) -> APIRouter:
        # Admin-only at the router level (the actual update endpoints live under
        # /api/update/* and are admin-gated there too).
        return APIRouter(dependencies=[Depends(require_admin)])

    def ui(self) -> dict[str, Any]:
        return ui.view(title="Updates", children=[ui.updates()])


attachment = Updates()

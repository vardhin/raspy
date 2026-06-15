"""The aggregated UI manifest endpoint. See plan/10-spine.md §4.

GET /api/manifest returns every loaded attachment's UI descriptor plus a global
version (ETag) so the frontend can cheaply skip refetching when nothing changed.
"""

from __future__ import annotations

import hashlib
import json
from typing import Any

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse, Response

from .auth.deps import principal_from_request

router = APIRouter()

# Apps that are never isolatable per-account and so are admin-only — never shown
# to children, only to admins:
#   accounts — the account-management app itself.
#   files    — browses the Pi's single shared home dir (~); can't be isolated.
#   stats    — system-wide host metrics; nothing per-account about them.
_ADMIN_ONLY = {"accounts", "files", "stats"}


async def _visible_attachments(request: Request) -> list[dict[str, Any]]:
    """The attachments the current account may see.

    Admin → everything (incl. the Accounts app). Child → only the ids in its
    ``allowed_apps`` allow-list, and never an admin-only app. The allow-list is
    read live from the DB so an admin toggling a permission takes effect on the
    child's next manifest fetch."""
    registry = request.app.state.registry
    attachments = registry.manifest()
    principal = principal_from_request(request)
    if principal is None:
        return []  # gate would normally 401 first; defensive.
    if principal.is_admin:
        return attachments
    svc = getattr(request.app.state, "auth", None)
    allowed = await svc.allowed_apps_of(principal.username) if svc else []
    allowed_set = set(allowed or [])
    return [
        a for a in attachments
        if a["id"] in allowed_set and a["id"] not in _ADMIN_ONLY
    ]


async def _manifest_payload(request: Request) -> dict[str, Any]:
    attachments = await _visible_attachments(request)
    # Hash the *filtered* list so each account gets its own ETag — a child's 304
    # can never replay an admin's (or another child's) app list.
    version = hashlib.sha256(
        json.dumps(attachments, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()[:16]
    return {"version": version, "attachments": attachments}


@router.get("/manifest")
async def get_manifest(request: Request) -> Response:
    payload = await _manifest_payload(request)
    etag = f'"{payload["version"]}"'
    headers = {"ETag": etag, "Cache-Control": "no-cache"}
    if request.headers.get("if-none-match") == etag:
        return Response(status_code=304, headers=headers)
    return JSONResponse(payload, headers=headers)

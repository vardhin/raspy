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

router = APIRouter()


def _manifest_payload(request: Request) -> dict[str, Any]:
    registry = request.app.state.registry
    attachments = registry.manifest()
    version = hashlib.sha256(
        json.dumps(attachments, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()[:16]
    return {"version": version, "attachments": attachments}


@router.get("/manifest")
async def get_manifest(request: Request) -> Response:
    payload = _manifest_payload(request)
    etag = f'"{payload["version"]}"'
    headers = {"ETag": etag, "Cache-Control": "no-cache"}
    if request.headers.get("if-none-match") == etag:
        return Response(status_code=304, headers=headers)
    return JSONResponse(payload, headers=headers)

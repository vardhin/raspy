"""Update endpoints (admin-only). See core/updater.py.

  GET  /api/update/status     latest-vs-current + whether an update is available
  POST /api/update/check      force a fresh check now
  GET  /api/update/releases   all published releases (version picker)
  POST /api/update/apply      download + verify + swap + restart; optional
                              {"target": "v0.4.0"} installs a specific version
                              (up OR down — rollback)
  DELETE /api/update/cache/{tag}  remove a cached binary (reclaim disk)
  GET  /api/update/autocheck  periodic-check config {enabled, interval_s}
  PUT  /api/update/autocheck  set the periodic-check config

Apply emits live ``update.progress`` events (downloading → downloaded → verifying
→ caching → verified/cached_hit → swapping → restarting | error) over the WS so
the UI can show exactly which step is happening.

These are gated by the global auth middleware (under /api/, not public) and
further restricted to admins here, since updating swaps the running binary.
"""

from __future__ import annotations

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel, Field

from .auth.deps import principal_from_request

router = APIRouter(prefix="/update", tags=["update"])


class ApplyBody(BaseModel):
    # A release tag (e.g. "v0.4.0") to install a specific version, or None for
    # the latest available update.
    target: str | None = None


class AutoCheckBody(BaseModel):
    enabled: bool = True
    interval_s: int = Field(ge=0)


def _require_admin(request: Request):
    principal = principal_from_request(request)
    if principal is None:
        raise HTTPException(status_code=401, detail="authentication required")
    if not principal.is_admin:
        raise HTTPException(status_code=403, detail="admin only")
    updater = getattr(request.app.state, "updater", None)
    if updater is None:
        raise HTTPException(status_code=503, detail="updater unavailable")
    return updater


@router.get("/status")
async def status(request: Request) -> dict:
    updater = _require_admin(request)
    info = await updater.check()
    return info.as_dict()


@router.post("/check")
async def check(request: Request) -> dict:
    updater = _require_admin(request)
    info = await updater.check()
    return info.as_dict()


@router.get("/releases")
async def releases(request: Request) -> dict:
    updater = _require_admin(request)
    return await updater.list_releases()


@router.post("/apply")
async def apply(request: Request, body: ApplyBody | None = None) -> dict:
    updater = _require_admin(request)
    target = body.target if body else None
    return await updater.apply(target=target)


@router.delete("/cache/{tag}")
async def delete_cache(request: Request, tag: str) -> dict:
    """Remove a cached binary to reclaim disk on the Pi's SD card."""
    updater = _require_admin(request)
    return updater.delete_cached(tag)


@router.get("/autocheck")
async def get_autocheck(request: Request) -> dict:
    updater = _require_admin(request)
    return updater.autocheck()


@router.put("/autocheck")
async def put_autocheck(request: Request, body: AutoCheckBody) -> dict:
    updater = _require_admin(request)
    return updater.set_autocheck(enabled=body.enabled, interval_s=body.interval_s)

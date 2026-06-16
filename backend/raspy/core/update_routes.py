"""Update endpoints (admin-only). See core/updater.py.

  GET  /api/update/status   cached/last-known + whether an update is available
  POST /api/update/check    force a fresh check now
  POST /api/update/apply    download + verify + swap + restart ("Update now")

These are gated by the global auth middleware (under /api/, not public) and
further restricted to admins here, since updating swaps the running binary.
"""

from __future__ import annotations

from fastapi import APIRouter, HTTPException, Request

from .auth.deps import principal_from_request

router = APIRouter(prefix="/update", tags=["update"])


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


@router.post("/apply")
async def apply(request: Request) -> dict:
    updater = _require_admin(request)
    return await updater.apply()

"""System / health endpoints. See plan/10-spine.md §1."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Request

from .. import __version__

router = APIRouter()


@router.get("/healthz")
async def healthz(request: Request) -> dict[str, Any]:
    registry = request.app.state.registry
    status = registry.status()
    return {
        "ok": True,
        "version": __version__,
        "attachments": status,
        "events": {"subscribers": request.app.state.events.subscriber_count},
    }

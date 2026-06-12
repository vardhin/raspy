"""WebSocket hub. See plan/10-spine.md §5 / plan/20-attachments.md §6.

Clients connect to /api/ws and receive every published event as a JSON message.
Filtering by topic is done client-side for now (one user, low volume); a
``subscribe`` message could narrow it later.
"""

from __future__ import annotations

import asyncio
import logging

from fastapi import APIRouter, WebSocket, WebSocketDisconnect

from .auth.deps import ACCESS_COOKIE
from .auth.service import AuthError

log = logging.getLogger("raspy.ws")

router = APIRouter()


def _ws_access_token(ws: WebSocket) -> str | None:
    """Token from the access cookie (web) or the `?access_token=` query param
    (native clients that can't set cookies on the WS handshake)."""
    cookie = ws.cookies.get(ACCESS_COOKIE)
    if cookie:
        return cookie
    return ws.query_params.get("access_token") or None


@router.websocket("/ws")
async def ws_endpoint(ws: WebSocket) -> None:
    # Authenticate before accepting. Closing with 1008 (policy violation) tells
    # the client to re-auth rather than blindly retry.
    auth = getattr(ws.app.state, "auth", None)
    token = _ws_access_token(ws)
    if auth is None or not token:
        await ws.close(code=1008)
        return
    try:
        auth.verify_access(token)
    except AuthError:
        await ws.close(code=1008)
        return

    await ws.accept()
    bus = ws.app.state.events
    queue = bus.subscribe()
    await ws.send_json({"type": "ready"})
    try:
        while True:
            event = await queue.get()
            await ws.send_json(event.as_message())
    except WebSocketDisconnect:
        pass
    except asyncio.CancelledError:
        raise
    except Exception:  # noqa: BLE001
        log.exception("websocket error")
    finally:
        bus.unsubscribe(queue)

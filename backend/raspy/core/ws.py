"""WebSocket hub. See plan/10-spine.md §5 / plan/20-attachments.md §6.

Clients connect to /api/ws and receive every published event as a JSON message.
Filtering by topic is done client-side for now (one user, low volume); a
``subscribe`` message could narrow it later.
"""

from __future__ import annotations

import asyncio
import logging

from fastapi import APIRouter, WebSocket, WebSocketDisconnect

log = logging.getLogger("raspy.ws")

router = APIRouter()


@router.websocket("/ws")
async def ws_endpoint(ws: WebSocket) -> None:
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

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
        claims = auth.verify_access(token)
    except AuthError:
        await ws.close(code=1008)
        return
    # A frozen child (pending setup) gets no live feed.
    if claims.get("mr"):
        await ws.close(code=1008)
        return

    # Which account is this socket? Notifications are per-account, so we only
    # forward notification events whose owner matches — otherwise a child's tab
    # would receive the admin's notifications and vice-versa (the bus broadcasts
    # every event to every subscriber). The key must match how notify() stamps
    # the owner (see notifications.owner_key).
    from .notifications import owner_key

    my_owner = owner_key(claims.get("sub"), is_admin=(claims.get("role") == "admin"))

    await ws.accept()
    bus = ws.app.state.events

    # Optional Layer-1 channel: if the client passes a valid channel session id,
    # seal every outbound frame so the tunnel sees only ciphertext. Frame shape
    # when sealed: {"type":"sealed","payload":"<b64 nonce||ct>"}; the client
    # opens it to recover the original event message.
    channel = getattr(ws.app.state, "channel", None)
    sid = ws.query_params.get("channel")
    sealed = bool(channel and sid and channel.has_session(sid))

    import json as _json

    def _frame(message: dict) -> dict:
        if not sealed:
            return message
        return {"type": "sealed", "payload": channel.seal(sid, _json.dumps(message).encode())}

    def _for_me(event) -> bool:
        """Notification events are owner-tagged; drop the ones not for this
        account. Everything else (app-data events) passes through unchanged."""
        if not event.topic.startswith(("notification.", "notifications.")):
            return True
        payload = event.payload
        owner = payload.get("account") if isinstance(payload, dict) else None
        # Untagged (legacy) notification events default to the legacy/admin owner.
        return (owner or owner_key(None, is_admin=True)) == my_owner

    queue = bus.subscribe()
    await ws.send_json(_frame({"type": "ready"}))
    try:
        while True:
            event = await queue.get()
            if not _for_me(event):
                continue
            await ws.send_json(_frame(event.as_message()))
    except WebSocketDisconnect:
        pass
    except asyncio.CancelledError:
        raise
    except Exception:  # noqa: BLE001
        log.exception("websocket error")
    finally:
        bus.unsubscribe(queue)

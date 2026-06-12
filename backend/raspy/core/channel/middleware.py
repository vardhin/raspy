"""Channel middleware: transparently decrypt sealed requests and encrypt
responses, so routers and attachments keep seeing/returning plaintext JSON.

Wire-format (only when the client opts into the channel):
  Request:  header ``X-Channel-Session: <sid>``; body is the raw base64 string
            ``nonce||ciphertext`` produced by ChannelService.seal on the client.
            The decrypted plaintext is the original request body (JSON, form, …)
            and we restore the original Content-Type from ``X-Channel-CT``.
  Response: header ``X-Channel-Enc: 1``; body is the sealed base64 of the original
            response body; original content-type moved to ``X-Channel-CT``.

Requests without the session header pass through untouched (LAN/dev, or the
handshake endpoints themselves), so the channel is strictly opt-in and additive.

Implemented as pure ASGI so we can rewrite the request/response byte streams
before/after the app, which a Starlette ``BaseHTTPMiddleware`` makes awkward.
"""

from __future__ import annotations

import logging

from starlette.types import ASGIApp, Message, Receive, Scope, Send

from .service import ChannelService

log = logging.getLogger("raspy.channel")

_SESSION_HEADER = b"x-channel-session"
_CT_HEADER = b"x-channel-ct"


class ChannelMiddleware:
    def __init__(self, app: ASGIApp, service_getter) -> None:
        self._app = app
        # service_getter() -> ChannelService | None (read from app.state lazily,
        # since the service is constructed in the lifespan after create_app()).
        self._get_service = service_getter

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self._app(scope, receive, send)
            return

        headers = dict(scope.get("headers") or [])
        sid_raw = headers.get(_SESSION_HEADER)
        svc: ChannelService | None = self._get_service()
        if not sid_raw or svc is None:
            await self._app(scope, receive, send)
            return
        sid = sid_raw.decode()
        if not svc.has_session(sid):
            # Stale/unknown session → 409 so the client re-handshakes.
            await _send_status(send, 409, b'{"detail":"channel session expired"}')
            return

        # --- decrypt the request body, restore original content-type ---------
        body = await _read_body(receive)
        try:
            plaintext = svc.open(sid, body.decode()) if body else b""
        except Exception:  # noqa: BLE001
            await _send_status(send, 400, b'{"detail":"channel decrypt failed"}')
            return

        orig_ct = headers.get(_CT_HEADER)
        new_headers = []
        for k, v in scope["headers"]:
            if k in (_SESSION_HEADER, _CT_HEADER, b"content-type", b"content-length"):
                continue
            new_headers.append((k, v))
        if orig_ct:
            new_headers.append((b"content-type", orig_ct))
        new_headers.append((b"content-length", str(len(plaintext)).encode()))
        scope = {**scope, "headers": new_headers}

        sent_body = False

        async def recv() -> Message:
            nonlocal sent_body
            if not sent_body:
                sent_body = True
                return {"type": "http.request", "body": plaintext, "more_body": False}
            return {"type": "http.disconnect"}

        # --- capture + re-encrypt the response -------------------------------
        start_msg: Message | None = None
        chunks: list[bytes] = []

        async def capture(message: Message) -> None:
            nonlocal start_msg
            if message["type"] == "http.response.start":
                start_msg = message
            elif message["type"] == "http.response.body":
                chunks.append(message.get("body", b""))
                if message.get("more_body"):
                    return
                await _emit_sealed(send, svc, sid, start_msg, b"".join(chunks))

        await self._app(scope, recv, capture)


async def _emit_sealed(
    send: Send, svc: ChannelService, sid: str, start: Message | None, body: bytes
) -> None:
    sealed = svc.seal(sid, body).encode()
    headers = []
    orig_ct = b"application/octet-stream"
    status = 200
    if start is not None:
        status = start["status"]
        for k, v in start.get("headers", []):
            if k == b"content-type":
                orig_ct = v
                continue
            if k == b"content-length":
                continue
            headers.append((k, v))
    headers.append((b"x-channel-enc", b"1"))
    headers.append((_CT_HEADER, orig_ct))
    headers.append((b"content-type", b"text/plain"))
    headers.append((b"content-length", str(len(sealed)).encode()))
    await send({"type": "http.response.start", "status": status, "headers": headers})
    await send({"type": "http.response.body", "body": sealed, "more_body": False})


async def _read_body(receive: Receive) -> bytes:
    chunks: list[bytes] = []
    while True:
        message = await receive()
        if message["type"] == "http.request":
            chunks.append(message.get("body", b""))
            if not message.get("more_body"):
                break
        elif message["type"] == "http.disconnect":
            break
    return b"".join(chunks)


async def _send_status(send: Send, status: int, body: bytes) -> None:
    await send({
        "type": "http.response.start",
        "status": status,
        "headers": [
            (b"content-type", b"application/json"),
            (b"content-length", str(len(body)).encode()),
        ],
    })
    await send({"type": "http.response.body", "body": body, "more_body": False})

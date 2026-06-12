"""Channel handshake endpoints. Both are PUBLIC (pre-auth) — the gate allow-lists
/api/channel/. Auth still happens inside the channel afterwards; the channel only
provides confidentiality from the tunnel, not authorization."""

from __future__ import annotations

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel, Field

from .service import ChannelService

router = APIRouter(prefix="/channel")


class HandshakeBody(BaseModel):
    client_pub: str = Field(min_length=1, max_length=128)


def _svc(request: Request) -> ChannelService:
    svc = getattr(request.app.state, "channel", None)
    if svc is None:
        raise HTTPException(503, "channel unavailable")
    return svc


@router.get("/pubkey")
async def pubkey(request: Request) -> dict[str, str]:
    """The Pi's pinned static identity. The client pins these on first contact
    and verifies the handshake signature against the Ed25519 key."""
    svc = _svc(request)
    return {
        "x25519": svc.static_x25519_pub,
        "ed25519": svc.static_ed25519_pub,
        "alg": "x25519-hkdf-sha256-chacha20poly1305-ietf",
        "version": "raspy-channel-v1",
    }


@router.post("/handshake")
async def handshake(request: Request, body: HandshakeBody) -> dict[str, str]:
    try:
        return _svc(request).handshake(body.client_pub)
    except ValueError as exc:
        raise HTTPException(400, str(exc))

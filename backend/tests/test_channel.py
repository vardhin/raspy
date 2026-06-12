"""Layer-1 channel: handshake, sealed round-trip through the middleware, tamper
rejection, and verifying ordinary endpoints still work over the channel.

The test plays the role of the *client*: it does its own X25519 + HKDF + ChaCha20
exactly as the browser (libsodium) does, then talks to the live app through the
ChannelMiddleware.
"""

from __future__ import annotations

import base64
import os

from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey
from cryptography.hazmat.primitives.asymmetric.x25519 import (
    X25519PrivateKey,
    X25519PublicKey,
)
from cryptography.hazmat.primitives.ciphers.aead import ChaCha20Poly1305
from cryptography.hazmat.primitives.kdf.hkdf import HKDF

_INFO = b"raspy-channel-v1"


def _b64e(raw: bytes) -> str:
    return base64.urlsafe_b64encode(raw).rstrip(b"=").decode()


def _b64d(s: str) -> bytes:
    return base64.urlsafe_b64decode(s + "=" * (-len(s) % 4))


class _Client:
    """Minimal client-side channel implementation for the test."""

    def __init__(self, client) -> None:
        self.http = client
        self.sid: str | None = None
        self.key: bytes | None = None

    def handshake(self) -> None:
        info = self.http.get("/api/channel/pubkey").json()
        eph = X25519PrivateKey.generate()
        eph_pub = eph.public_key().public_bytes_raw()
        resp = self.http.post("/api/channel/handshake",
                              json={"client_pub": _b64e(eph_pub)}).json()
        server_pub = _b64d(resp["server_pub"])
        # Verify the handshake signature against the pinned Ed25519 key.
        Ed25519PublicKey.from_public_bytes(_b64d(info["ed25519"])).verify(
            _b64d(resp["signature"]), eph_pub + server_pub
        )
        shared = eph.exchange(X25519PublicKey.from_public_bytes(server_pub))
        self.key = HKDF(algorithm=hashes.SHA256(), length=32,
                        salt=eph_pub + server_pub, info=_INFO).derive(shared)
        self.sid = resp["session_id"]

    def seal(self, plaintext: bytes) -> str:
        nonce = os.urandom(12)
        return _b64e(nonce + ChaCha20Poly1305(self.key).encrypt(nonce, plaintext, None))

    def open(self, payload_b64: str) -> bytes:
        blob = _b64d(payload_b64)
        return ChaCha20Poly1305(self.key).decrypt(blob[:12], blob[12:], None)

    def get(self, path: str):
        """A GET over the channel: empty sealed body + session header."""
        r = self.http.get(path, headers={"x-channel-session": self.sid})
        return self._unseal(r)

    def post(self, path: str, body: bytes, content_type="application/json"):
        r = self.http.post(
            path,
            content=self.seal(body),
            headers={
                "x-channel-session": self.sid,
                "x-channel-ct": content_type,
                "content-type": "text/plain",
            },
        )
        return self._unseal(r)

    def _unseal(self, r):
        if r.headers.get("x-channel-enc") == "1":
            return r.status_code, self.open(r.text)
        return r.status_code, r.content


def test_handshake_and_sealed_roundtrip(client):
    c = _Client(client)
    c.handshake()
    assert c.sid and c.key
    # healthz over the channel: response body comes back sealed and decrypts to
    # the real JSON.
    status, body = c.get("/api/healthz")
    assert status == 200
    assert b'"ok":true' in body.replace(b" ", b"")


def test_ordinary_attachment_works_over_channel(client):
    """A real mutating endpoint (todo create) through the sealed channel."""
    c = _Client(client)
    c.handshake()
    import json

    status, body = c.post("/api/att/todo/items", json.dumps({"title": "via channel"}).encode())
    assert status in (200, 201), (status, body)
    # And it's actually stored — list it back over the channel.
    status, body = c.get("/api/att/todo/items")
    assert status == 200
    assert b"via channel" in body


def test_tampered_ciphertext_rejected(client):
    c = _Client(client)
    c.handshake()
    sealed = c.seal(b'{"title":"x"}')
    # Flip a byte in the ciphertext → AEAD tag fails → 400.
    bad = sealed[:-2] + ("A" if sealed[-1] != "A" else "B")
    r = client.post("/api/att/todo/items", content=bad, headers={
        "x-channel-session": c.sid, "x-channel-ct": "application/json",
        "content-type": "text/plain",
    })
    assert r.status_code == 400


def test_unknown_session_409(client):
    r = client.get("/api/healthz", headers={"x-channel-session": "nope"})
    assert r.status_code == 409


def test_no_session_header_passes_through_cleartext(client):
    # Without the channel header, the middleware is a no-op — normal cleartext.
    r = client.get("/api/healthz")
    assert r.status_code == 200
    assert "x-channel-enc" not in r.headers

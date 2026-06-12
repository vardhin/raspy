"""ChannelService — handshake + per-session seal/open. In-memory session table
(single operator; sessions are cheap and forward-secret per connection).

A session is created by POST /api/channel/handshake: the client posts its
ephemeral X25519 public key, we generate our own ephemeral key, both sides derive
the same session key. (We use an ephemeral key on the server side too, so the
long-term static key only authenticates the server — it's never used to encrypt,
giving forward secrecy even if the static key later leaks.)

The static key is loaded from data/channel_key (PEM, created by raspy-auth) and
its public half is pinned by the client. The handshake response is signed by the
static key so a MITM can't substitute its own ephemeral key.
"""

from __future__ import annotations

import base64
import logging
import os
import time
from dataclasses import dataclass
from pathlib import Path

from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import (
    Ed25519PrivateKey,
    Ed25519PublicKey,
)
from cryptography.hazmat.primitives.asymmetric.x25519 import (
    X25519PrivateKey,
    X25519PublicKey,
)
from cryptography.hazmat.primitives.ciphers.aead import ChaCha20Poly1305
from cryptography.hazmat.primitives.kdf.hkdf import HKDF

from ...config import ChannelSettings

log = logging.getLogger("raspy.channel")

_HKDF_INFO = b"raspy-channel-v1"
_NONCE_LEN = 12


def _b64e(raw: bytes) -> str:
    return base64.urlsafe_b64encode(raw).rstrip(b"=").decode()


def _b64d(s: str) -> bytes:
    return base64.urlsafe_b64decode(s + "=" * (-len(s) % 4))


@dataclass
class _Session:
    key: bytes
    created: float


class ChannelService:
    def __init__(self, settings: ChannelSettings, static_pem: bytes) -> None:
        self._cfg = settings
        # The static key is X25519 for the pinned identity, but we sign handshakes
        # with a derived Ed25519 key so the client can verify the response wasn't
        # tampered. We keep both from one stored seed for simplicity: the PEM is an
        # X25519 private key; we also derive a stable Ed25519 signer from its raw
        # bytes so there's a single file to manage.
        self._x_priv = serialization.load_pem_private_key(static_pem, password=None)
        if not isinstance(self._x_priv, X25519PrivateKey):
            raise ValueError("channel_key is not an X25519 private key")
        raw = self._x_priv.private_bytes(
            encoding=serialization.Encoding.Raw,
            format=serialization.PrivateFormat.Raw,
            encryption_algorithm=serialization.NoEncryption(),
        )
        self._ed_priv = Ed25519PrivateKey.from_private_bytes(raw)
        self._sessions: dict[str, _Session] = {}

    # --- public identity (pinned by the client) -----------------------------

    @property
    def static_x25519_pub(self) -> str:
        return _b64e(
            self._x_priv.public_key().public_bytes(
                encoding=serialization.Encoding.Raw,
                format=serialization.PublicFormat.Raw,
            )
        )

    @property
    def static_ed25519_pub(self) -> str:
        return _b64e(
            self._ed_priv.public_key().public_bytes(
                encoding=serialization.Encoding.Raw,
                format=serialization.PublicFormat.Raw,
            )
        )

    # --- handshake -----------------------------------------------------------

    def handshake(self, client_pub_b64: str) -> dict[str, str]:
        """Given the client's ephemeral X25519 pubkey, create a session and
        return our ephemeral pubkey + a signature over both pubkeys (so the
        client can verify the server identity / detect a MITM)."""
        client_pub = _b64d(client_pub_b64)
        if len(client_pub) != 32:
            raise ValueError("bad client public key")

        eph = X25519PrivateKey.generate()
        eph_pub = eph.public_key().public_bytes(
            encoding=serialization.Encoding.Raw, format=serialization.PublicFormat.Raw
        )
        shared = eph.exchange(X25519PublicKey.from_public_bytes(client_pub))
        # salt = client_pub || server_eph_pub  (must match the client's order)
        key = HKDF(
            algorithm=hashes.SHA256(), length=32,
            salt=client_pub + eph_pub, info=_HKDF_INFO,
        ).derive(shared)

        sid = _b64e(os.urandom(12))
        self._sessions[sid] = _Session(key=key, created=time.time())
        self._gc()

        # Sign (client_pub || eph_pub) so the client knows the eph key really came
        # from the holder of the pinned static key.
        sig = self._ed_priv.sign(client_pub + eph_pub)
        return {
            "session_id": sid,
            "server_pub": _b64e(eph_pub),
            "signature": _b64e(sig),
        }

    # --- seal / open ---------------------------------------------------------

    def open(self, session_id: str, payload_b64: str) -> bytes:
        """Decrypt a sealed payload (nonce||ciphertext, base64) → plaintext."""
        sess = self._sessions.get(session_id)
        if sess is None:
            raise KeyError("unknown channel session")
        blob = _b64d(payload_b64)
        nonce, ct = blob[:_NONCE_LEN], blob[_NONCE_LEN:]
        return ChaCha20Poly1305(sess.key).decrypt(nonce, ct, None)

    def seal(self, session_id: str, plaintext: bytes) -> str:
        """Encrypt plaintext → base64(nonce||ciphertext)."""
        sess = self._sessions.get(session_id)
        if sess is None:
            raise KeyError("unknown channel session")
        nonce = os.urandom(_NONCE_LEN)
        ct = ChaCha20Poly1305(sess.key).encrypt(nonce, plaintext, None)
        return _b64e(nonce + ct)

    def has_session(self, session_id: str) -> bool:
        return session_id in self._sessions

    def _gc(self) -> None:
        cutoff = time.time() - self._cfg.session_ttl_s
        stale = [sid for sid, s in self._sessions.items() if s.created < cutoff]
        for sid in stale:
            del self._sessions[sid]


def load_static_pem(path: Path) -> bytes:
    p = Path(path)
    if not p.is_file():
        raise FileNotFoundError(
            f"channel key not found at {p} — run `raspy-auth gen-channel-key` "
            f"(or create-account)"
        )
    return p.read_bytes()

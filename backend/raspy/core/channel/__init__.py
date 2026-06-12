"""Layer-1 encrypted channel (see plan/shiny-painting-flask, Layer 1).

A forward-secret tunnel *inside* the Cloudflare TLS so the tunnel middleman only
ever relays ciphertext. The client encrypts request bodies + WS frames in the
browser/Flutter with a session key negotiated directly with the Pi (X25519 +
HKDF-SHA256); the Pi decrypts to operate normally on ordinary attachments. The
vault (Layer 2) rides through this but does not depend on it.

Crypto is byte-for-byte interoperable with libsodium on the client:
  * X25519 (crypto_scalarmult)
  * HKDF-SHA256 (RFC 5869), salt = client_pub||server_pub, info = b"raspy-channel-v1"
  * ChaCha20-Poly1305 IETF (12-byte nonce) AEAD per message
"""

from __future__ import annotations

from .service import ChannelService

__all__ = ["ChannelService"]

"""Generate a VAPID keypair for Web Push.

Run ``raspy-vapid`` once and paste the output into ``data/config.toml`` (or set
the env vars). The public key is handed to the browser as the
``applicationServerKey``; the spine keeps the private key. See
core/notifications.py.

VAPID keys are an ECDSA P-256 keypair:
  - public  → base64url of the uncompressed EC point (65 bytes).
  - private → base64url of the 32-byte private scalar. pywebpush accepts this
    string directly as ``vapid_private_key``.
"""

from __future__ import annotations

import base64

from cryptography.hazmat.primitives import serialization
from py_vapid import Vapid01


def _b64url(raw: bytes) -> str:
    return base64.urlsafe_b64encode(raw).rstrip(b"=").decode()


def generate_keypair() -> tuple[str, str]:
    """Return (public_key_b64url, private_key_b64url)."""
    vapid = Vapid01()
    vapid.generate_keys()
    public_raw = vapid.public_key.public_bytes(
        serialization.Encoding.X962,
        serialization.PublicFormat.UncompressedPoint,
    )
    private_raw = vapid.private_key.private_numbers().private_value.to_bytes(32, "big")
    return _b64url(public_raw), _b64url(private_raw)


def main() -> None:
    public, private = generate_keypair()
    print("VAPID keypair generated. Add to data/config.toml:\n")
    print(f"vapid_public_key = {public!r}")
    print(f"vapid_private_key = {private!r}")
    print('vapid_subject = "mailto:you@example.com"')
    print("\n…or export as env vars:\n")
    print(f"export RASPY_VAPID_PUBLIC_KEY={public}")
    print(f"export RASPY_VAPID_PRIVATE_KEY={private}")


if __name__ == "__main__":
    main()

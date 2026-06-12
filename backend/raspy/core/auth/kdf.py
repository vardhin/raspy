"""Client-parity KDF: derive the same ``auth_key`` the browser derives.

The browser computes, with libsodium:

    raw = crypto_pwhash(32, password, salt(16B), OPS, MEM, ALG_ARGON2ID13)
    auth_key = base64url(raw)

For first-run account creation the CLI runs on the Pi (no browser), so it must
reproduce that derivation to store a matching hash. We use argon2-cffi's
low-level Argon2id with parameters chosen to match libsodium's crypto_pwhash:

  * libsodium OPSLIMIT  == argon2 time_cost (iterations)
  * libsodium MEMLIMIT  == argon2 memory_cost in BYTES; argon2-cffi wants KiB
  * parallelism is fixed at 1 in libsodium's crypto_pwhash

So the *channel/auth* KDF parameters are a small fixed pair (ops, mem) shared by
both sides, independent of the server-side storage Argon2 params (which hash the
auth_key again). Keep these in lock-step with frontend/src/lib/crypto/kdf.ts.
"""

from __future__ import annotations

import base64

from argon2.low_level import Type, hash_secret_raw

# Interactive-tier params (libsodium crypto_pwhash_OPSLIMIT/MEMLIMIT_INTERACTIVE).
# These run client-side, so the (strong) laptop/phone bears the cost. Bump to
# MODERATE if you want more; just change both sides together.
PWHASH_OPSLIMIT = 2
PWHASH_MEMLIMIT_BYTES = 64 * 1024 * 1024  # 64 MiB
PWHASH_PARALLELISM = 1
KEY_BYTES = 32


def _b64decode(s: str) -> bytes:
    pad = "=" * (-len(s) % 4)
    return base64.urlsafe_b64decode(s + pad)


# libsodium's crypto_pwhash requires exactly this salt length (ARGON2ID13).
SALT_BYTES = 16


def derive_key(password: str, salt_b64: str) -> bytes:
    """Reproduce the browser's crypto_pwhash(ARGON2ID13) → 32 raw bytes."""
    salt = _b64decode(salt_b64)
    if len(salt) != SALT_BYTES:
        # libsodium would reject this; fail loudly so client/server never diverge.
        raise ValueError(f"salt must be {SALT_BYTES} bytes, got {len(salt)}")
    return hash_secret_raw(
        secret=password.encode("utf-8"),
        salt=salt,
        time_cost=PWHASH_OPSLIMIT,
        memory_cost=PWHASH_MEMLIMIT_BYTES // 1024,  # argon2-cffi takes KiB
        parallelism=PWHASH_PARALLELISM,
        hash_len=KEY_BYTES,
        type=Type.ID,
    )


def derive_auth_key(password: str, auth_salt_b64: str) -> str:
    """The client-facing ``auth_key`` string sent at login."""
    return base64.urlsafe_b64encode(derive_key(password, auth_salt_b64)).rstrip(b"=").decode()

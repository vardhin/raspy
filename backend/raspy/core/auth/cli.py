"""raspy-auth — first-run account setup + auth admin, run on the Pi over SSH.

No HTTP setup surface exists; account creation happens only here. Commands:

  raspy-auth create-account [--username U]   create the initial account (+ PIN)
  raspy-auth set-pin        [--username U]   set/replace the mini-PIN
  raspy-auth reset-password [--username U]   change the password (revokes sessions)
  raspy-auth revoke-all     [--username U]   log out everywhere
  raspy-auth gen-channel-key                 (re)generate the Layer-1 static key
  raspy-auth calibrate                       tune server-side Argon2 for this Pi

All commands operate directly on data/ (SQLite + secrets), generating the HMAC
signing secret and the channel keypair on first create.
"""

from __future__ import annotations

import argparse
import asyncio
import getpass
import os
import secrets
import sys
import time
from base64 import urlsafe_b64encode

from ...config import get_settings
from ..db import Database
from . import kdf
from .service import AuthService, load_or_create_secret


def _rand_salt() -> str:
    return urlsafe_b64encode(os.urandom(16)).rstrip(b"=").decode()


def _prompt_password(label: str) -> str:
    pw = getpass.getpass(f"{label}: ")
    again = getpass.getpass(f"{label} (again): ")
    if pw != again:
        print("error: entries did not match", file=sys.stderr)
        sys.exit(1)
    if not pw:
        print("error: empty value", file=sys.stderr)
        sys.exit(1)
    return pw


def _read_secret(label: str, *, from_stdin: bool) -> str:
    """Get a secret either by interactive double-prompt (TTY) or one line from
    stdin (installer/non-interactive). The installer pipes
    ``printf 'pw\\npin\\n'`` so each call consumes the next line."""
    if from_stdin:
        line = sys.stdin.readline()
        if not line:
            print(f"error: expected {label} on stdin", file=sys.stderr)
            sys.exit(1)
        value = line.rstrip("\n")
        if not value:
            print(f"error: empty {label}", file=sys.stderr)
            sys.exit(1)
        return value
    return _prompt_password(label)


async def _service() -> tuple[AuthService, Database]:
    settings = get_settings()
    settings.data_dir.mkdir(parents=True, exist_ok=True)
    secret = load_or_create_secret(settings.auth_secret_path, create=True)
    db = Database(settings.db_path)
    db.connect()
    svc = AuthService(db=db, settings=settings.auth, secret=secret)
    await svc.init()
    return svc, db


async def _create_account(args: argparse.Namespace) -> None:
    svc, db = await _service()
    try:
        if await svc.has_account() and not args.force:
            print("error: an account already exists (use --force to add another)",
                  file=sys.stderr)
            sys.exit(1)
        stdin = bool(getattr(args, "stdin", False))
        username = args.username or (
            sys.stdin.readline().strip() if stdin else input("username: ").strip()
        )
        if not username:
            print("error: username required", file=sys.stderr)
            sys.exit(1)
        password = _read_secret("password", from_stdin=stdin)
        pin = _read_secret("mini-PIN", from_stdin=stdin)

        auth_salt = _rand_salt()
        master_salt = _rand_salt()
        # Derive auth_key exactly as the browser will (so login matches).
        auth_key = kdf.derive_auth_key(password, auth_salt)
        await svc.create_account(
            username, auth_key, pin, auth_salt=auth_salt, master_salt=master_salt
        )
        # Ensure the channel static key exists too.
        _ensure_channel_key()
        print(f"created account {username!r}. The spine is ready to start.")
    finally:
        db.close()


async def _set_pin(args: argparse.Namespace) -> None:
    svc, db = await _service()
    try:
        username = args.username or input("username: ").strip()
        pin = _prompt_password("new mini-PIN")
        await svc.set_pin(username, pin)
        print(f"PIN updated for {username!r}.")
    finally:
        db.close()


async def _reset_password(args: argparse.Namespace) -> None:
    svc, db = await _service()
    try:
        username = args.username or input("username: ").strip()
        account = await svc.kdf_salts(username)
        if account is None:
            print(f"error: no such account {username!r}", file=sys.stderr)
            sys.exit(1)
        password = _prompt_password("new password")
        auth_key = kdf.derive_auth_key(password, account["auth_salt"])
        await svc.set_password(username, auth_key)
        print(f"password updated for {username!r}; all sessions revoked.")
    finally:
        db.close()


async def _revoke_all(args: argparse.Namespace) -> None:
    svc, db = await _service()
    try:
        await svc.revoke_all(args.username)
        print("all sessions revoked.")
    finally:
        db.close()


def _ensure_channel_key(path=None) -> None:
    """Generate the Pi's long-term static X25519 keypair if absent (PEM, 600)."""
    from cryptography.hazmat.primitives.asymmetric.x25519 import X25519PrivateKey
    from cryptography.hazmat.primitives import serialization

    if path is None:
        path = get_settings().channel_key_path
    if path.is_file():
        return
    key = X25519PrivateKey.generate()
    pem = key.private_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PrivateFormat.PKCS8,
        encryption_algorithm=serialization.NoEncryption(),
    )
    path.parent.mkdir(parents=True, exist_ok=True)
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    with os.fdopen(fd, "wb") as fh:
        fh.write(pem)
    print(f"generated channel static key at {path}")


def _gen_channel_key(args: argparse.Namespace) -> None:
    settings = get_settings()
    if settings.channel_key_path.is_file() and not args.force:
        print("error: channel key exists (use --force to replace; this breaks "
              "all pinned clients)", file=sys.stderr)
        sys.exit(1)
    if args.force and settings.channel_key_path.is_file():
        settings.channel_key_path.unlink()
    _ensure_channel_key()


def _calibrate(args: argparse.Namespace) -> None:
    """Find Argon2 params (server-side storage hash) hitting ~target ms on this
    box. Prints a [auth] config.toml snippet to paste."""
    from argon2 import PasswordHasher

    target_ms = args.target_ms
    mem_kib = 64 * 1024
    parallelism = args.parallelism
    print(f"calibrating Argon2id for ~{target_ms}ms/verify "
          f"(mem={mem_kib//1024}MiB, parallelism={parallelism})…")
    for time_cost in range(1, 12):
        ph = PasswordHasher(time_cost=time_cost, memory_cost=mem_kib, parallelism=parallelism)
        h = ph.hash("calibration-probe")
        t0 = time.perf_counter()
        ph.verify(h, "calibration-probe")
        ms = (time.perf_counter() - t0) * 1000
        print(f"  time_cost={time_cost}: {ms:.0f}ms")
        if ms >= target_ms:
            print("\nrecommended config.toml:\n")
            print("[auth]")
            print(f"argon_time_cost = {time_cost}")
            print(f"argon_memory_kib = {mem_kib}")
            print(f"argon_parallelism = {parallelism}")
            return
    print("hit time_cost ceiling without reaching target; raise memory instead.")


def main() -> None:
    parser = argparse.ArgumentParser(prog="raspy-auth", description="Raspy auth admin")
    sub = parser.add_subparsers(dest="command", required=True)

    p = sub.add_parser("create-account", help="create the initial account")
    p.add_argument("--username")
    p.add_argument("--force", action="store_true", help="add another account")
    p.add_argument(
        "--stdin",
        action="store_true",
        help="read username (if no --username), password, then PIN as lines from "
        "stdin — for non-interactive installers",
    )
    p.set_defaults(func=lambda a: asyncio.run(_create_account(a)))

    p = sub.add_parser("set-pin", help="set/replace the mini-PIN")
    p.add_argument("--username")
    p.set_defaults(func=lambda a: asyncio.run(_set_pin(a)))

    p = sub.add_parser("reset-password", help="change the password")
    p.add_argument("--username")
    p.set_defaults(func=lambda a: asyncio.run(_reset_password(a)))

    p = sub.add_parser("revoke-all", help="log out everywhere")
    p.add_argument("--username")
    p.set_defaults(func=lambda a: asyncio.run(_revoke_all(a)))

    p = sub.add_parser("gen-channel-key", help="(re)generate the channel static key")
    p.add_argument("--force", action="store_true")
    p.set_defaults(func=_gen_channel_key)

    p = sub.add_parser("calibrate", help="tune Argon2 for this Pi")
    p.add_argument("--target-ms", type=float, default=350.0)
    p.add_argument("--parallelism", type=int, default=2)
    p.set_defaults(func=_calibrate)

    args = parser.parse_args()
    args.func(args)


if __name__ == "__main__":
    main()

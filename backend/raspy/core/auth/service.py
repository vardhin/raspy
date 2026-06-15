"""AuthService — the one object that owns auth state + logic.

Mirrors core/notifications.py: tables created in ``init()``, called from the app
lifespan. Single-operator system, but the schema leaves room for more than one
account (keyed by username).

What it guarantees (plan/30-auth-security.md §3):
  * password + PIN stored as Argon2id hashes (memory-hard).
  * every login/unlock attempt is rate-limited per account *and* per IP, with
    exponential lockout, all server-side — nothing offline-crackable.
  * refresh tokens rotate; presenting an already-rotated refresh (theft signal)
    revokes the whole family.
  * constant-ish timing: a verify always runs even when the user/credential is
    absent, so you can't probe existence by timing.

The client sends an ``auth_key`` (= Argon2id(password) computed in the browser),
never the raw password — but the server still hashes *that* with Argon2id before
storing/comparing, so a DB leak doesn't expose a directly-usable credential.
"""

from __future__ import annotations

import hmac
import json
import logging
import os
import secrets
import time
from dataclasses import dataclass
from typing import Any

from argon2 import PasswordHasher
from argon2.exceptions import VerifyMismatchError, InvalidHashError

from ...config import AuthSettings
from ..db import Database
from . import tokens

log = logging.getLogger("raspy.auth")

_T_ACCOUNT = "core_auth_account"
_T_REFRESH = "core_auth_refresh"
_T_ATTEMPTS = "core_auth_attempts"
_T_AUDIT = "core_auth_audit"

# A throwaway hash we verify against when no account/credential exists, purely so
# the failure path spends the same ~Argon2 time as the success path (no timing
# oracle for "does this user exist"). Recomputed at init with live params.
_DUMMY_PASSWORD = b"raspy-timing-equalizer"


@dataclass
class LoginResult:
    access_token: str
    refresh_token: str
    family_id: str
    username: str
    # 'admin' | 'child'. Stamped so the client/router can branch without a
    # second lookup.
    role: str = "admin"
    # True when the account is frozen pending first-time password/PIN reset; the
    # only thing the client may do is POST /auth/complete-setup.
    must_reset: bool = False


class AuthError(Exception):
    """Auth failed. ``retry_after`` is set when the cause is a lockout."""

    def __init__(self, message: str, *, retry_after: float | None = None) -> None:
        super().__init__(message)
        self.retry_after = retry_after


class AuthService:
    def __init__(self, db: Database, settings: AuthSettings, secret: bytes) -> None:
        self._db = db
        self._cfg = settings
        self._secret = secret
        self._ph = PasswordHasher(
            time_cost=settings.argon_time_cost,
            memory_cost=settings.argon_memory_kib,
            parallelism=settings.argon_parallelism,
        )
        self._dummy_hash = self._ph.hash(_DUMMY_PASSWORD)

    # --- schema --------------------------------------------------------------

    async def init(self) -> None:
        await self._db.execute(
            f"""
            CREATE TABLE IF NOT EXISTS {_T_ACCOUNT} (
                username   TEXT PRIMARY KEY,
                pw_hash    TEXT NOT NULL,
                pin_hash   TEXT,
                -- Salts the *client* uses to derive auth_key / master_key from
                -- the raw password (Argon2id, in the browser). Public by design:
                -- they are not secret, only per-account-unique. master_salt
                -- never affects anything server-side — it just has to be stable
                -- and reach the client so the vault key is reproducible.
                auth_salt   TEXT NOT NULL,
                master_salt TEXT NOT NULL,
                created    REAL NOT NULL,
                -- 'admin' | 'child'. The original CLI-created account is admin by
                -- default (no migration needed); children are made via the UI.
                role        TEXT NOT NULL DEFAULT 'admin',
                -- 1 = frozen pending first-time password/PIN reset (temp creds).
                must_reset  INTEGER NOT NULL DEFAULT 0,
                -- JSON list of attachment ids this account may see; NULL = all
                -- (admin). Children get an explicit allow-list.
                allowed_apps TEXT
            )
            """
        )
        # Migrate already-deployed account tables that predate the columns above.
        await self._migrate_account_columns()
        # One row per *live* refresh token. A family shares family_id; rotation
        # inserts a new row (new jti) and marks the old one used. Reuse of a used
        # row => theft => revoke the family.
        await self._db.execute(
            f"""
            CREATE TABLE IF NOT EXISTS {_T_REFRESH} (
                jti        TEXT PRIMARY KEY,
                family_id  TEXT NOT NULL,
                username   TEXT NOT NULL,
                secret_hash TEXT NOT NULL,
                issued     REAL NOT NULL,
                expires    REAL NOT NULL,
                used       INTEGER NOT NULL DEFAULT 0,
                revoked    INTEGER NOT NULL DEFAULT 0,
                pin_fails  INTEGER NOT NULL DEFAULT 0,
                downgraded INTEGER NOT NULL DEFAULT 0
            )
            """
        )
        await self._db.execute(
            f"CREATE INDEX IF NOT EXISTS {_T_REFRESH}_fam ON {_T_REFRESH} (family_id)"
        )
        # Rate-limit / lockout state keyed by (scope, key) where scope is
        # 'account' or 'ip'. Survives restarts.
        await self._db.execute(
            f"""
            CREATE TABLE IF NOT EXISTS {_T_ATTEMPTS} (
                scope        TEXT NOT NULL,
                key          TEXT NOT NULL,
                fails        INTEGER NOT NULL DEFAULT 0,
                locked_until REAL NOT NULL DEFAULT 0,
                updated      REAL NOT NULL,
                PRIMARY KEY (scope, key)
            )
            """
        )
        await self._db.execute(
            f"""
            CREATE TABLE IF NOT EXISTS {_T_AUDIT} (
                id      INTEGER PRIMARY KEY AUTOINCREMENT,
                ts      REAL NOT NULL,
                event   TEXT NOT NULL,
                ok      INTEGER NOT NULL,
                ip      TEXT,
                detail  TEXT
            )
            """
        )

    async def _migrate_account_columns(self) -> None:
        """Add the role/must_reset/allowed_apps columns to an account table that
        was created before isolation existed. SQLite has no ``ADD COLUMN IF NOT
        EXISTS``, so we introspect and add what's missing. Existing rows keep the
        column defaults — i.e. the lone existing account becomes the admin with
        ``allowed_apps`` NULL (all apps)."""
        rows = await self._db.fetch_all(f"PRAGMA table_info({_T_ACCOUNT})")
        have = {r["name"] for r in rows}
        adds = {
            "role": "TEXT NOT NULL DEFAULT 'admin'",
            "must_reset": "INTEGER NOT NULL DEFAULT 0",
            "allowed_apps": "TEXT",
        }
        for col, decl in adds.items():
            if col not in have:
                await self._db.execute(
                    f"ALTER TABLE {_T_ACCOUNT} ADD COLUMN {col} {decl}"
                )

    # --- account existence (for first-run / setup-mode checks) ---------------

    async def has_account(self) -> bool:
        row = await self._db.fetch_one(f"SELECT COUNT(*) AS n FROM {_T_ACCOUNT}")
        return bool((row or {}).get("n", 0))

    async def _get_account(self, username: str) -> dict[str, Any] | None:
        return await self._db.fetch_one(
            f"SELECT * FROM {_T_ACCOUNT} WHERE username = ?", (username,)
        )

    async def kdf_salts(self, username: str) -> dict[str, str] | None:
        """Public per-account KDF salts the client needs to derive auth_key and
        master_key. Returns None if the user doesn't exist (the client should
        treat a missing account the same as a wrong password — don't leak)."""
        account = await self._get_account(username)
        if account is None:
            return None
        return {
            "auth_salt": account["auth_salt"],
            "master_salt": account["master_salt"],
            "argon_time_cost": self._cfg.argon_time_cost,
            "argon_memory_kib": self._cfg.argon_memory_kib,
            "argon_parallelism": self._cfg.argon_parallelism,
        }

    def decoy_salts(self, username: str) -> dict[str, Any]:
        """Stable, username-derived decoy salts for a non-existent account, so
        ``GET /auth/kdf/<user>`` doesn't reveal whether the user exists. Derived
        via HMAC(secret, username) so they look random but are reproducible."""
        import base64 as _b64
        import hashlib as _h

        def _salt(tag: str) -> str:
            digest = hmac.new(
                self._secret, f"{tag}:{username}".encode(), _h.sha256
            ).digest()[:16]
            return _b64.urlsafe_b64encode(digest).rstrip(b"=").decode()

        return {
            "auth_salt": _salt("auth"),
            "master_salt": _salt("master"),
            "argon_time_cost": self._cfg.argon_time_cost,
            "argon_memory_kib": self._cfg.argon_memory_kib,
            "argon_parallelism": self._cfg.argon_parallelism,
        }

    async def create_account(
        self, username: str, auth_key: str, pin: str | None,
        auth_salt: str, master_salt: str,
    ) -> None:
        """Create the account. Called by the CLI (first-run). ``auth_key`` is the
        client-derived value (the CLI replicates the browser derivation); we hash
        *that* with Argon2id before storing."""
        if await self._get_account(username) is not None:
            raise AuthError(f"account {username!r} already exists")
        pw_hash = self._ph.hash(auth_key)
        pin_hash = self._ph.hash(pin) if pin else None
        await self._db.execute(
            f"INSERT INTO {_T_ACCOUNT} "
            f"(username, pw_hash, pin_hash, auth_salt, master_salt, created) "
            f"VALUES (?, ?, ?, ?, ?, ?)",
            (username, pw_hash, pin_hash, auth_salt, master_salt, time.time()),
        )

    async def create_child(
        self, username: str, auth_key: str, pin: str,
        auth_salt: str, master_salt: str, allowed_apps: list[str],
    ) -> None:
        """Create a frozen child account with admin-supplied temp credentials.

        ``role='child'`` and ``must_reset=1`` so the first sign-in forces a
        password+PIN reset (the admin never sees the new ones). ``allowed_apps``
        is the explicit per-account app allow-list."""
        if await self._get_account(username) is not None:
            raise AuthError(f"account {username!r} already exists")
        pw_hash = self._ph.hash(auth_key)
        pin_hash = self._ph.hash(pin)
        await self._db.execute(
            f"INSERT INTO {_T_ACCOUNT} "
            f"(username, pw_hash, pin_hash, auth_salt, master_salt, created, "
            f" role, must_reset, allowed_apps) "
            f"VALUES (?, ?, ?, ?, ?, ?, 'child', 1, ?)",
            (username, pw_hash, pin_hash, auth_salt, master_salt, time.time(),
             json.dumps(sorted(set(allowed_apps)))),
        )

    async def list_accounts(self) -> list[dict[str, Any]]:
        """All accounts (no hashes). ``allowed_apps`` decoded to a list (or None
        for admins = all apps)."""
        rows = await self._db.fetch_all(
            f"SELECT username, role, must_reset, allowed_apps, created "
            f"FROM {_T_ACCOUNT} ORDER BY created"
        )
        out: list[dict[str, Any]] = []
        for r in rows:
            raw = r.get("allowed_apps")
            out.append({
                "username": r["username"],
                "role": r["role"] or "admin",
                "must_reset": bool(r["must_reset"]),
                "allowed_apps": json.loads(raw) if raw else None,
                "created": r["created"],
            })
        return out

    async def role_of(self, username: str) -> str | None:
        account = await self._get_account(username)
        if account is None:
            return None
        return account.get("role") or "admin"

    async def allowed_apps_of(self, username: str) -> list[str] | None:
        """The account's app allow-list, or None = all apps (admins)."""
        account = await self._get_account(username)
        if account is None:
            return []
        raw = account.get("allowed_apps")
        return json.loads(raw) if raw else None

    async def set_allowed_apps(self, username: str, allowed_apps: list[str]) -> None:
        account = await self._get_account(username)
        if account is None:
            raise AuthError(f"no such account {username!r}")
        if (account.get("role") or "admin") == "admin":
            raise AuthError("cannot restrict an admin account")
        await self._db.execute(
            f"UPDATE {_T_ACCOUNT} SET allowed_apps = ? WHERE username = ?",
            (json.dumps(sorted(set(allowed_apps))), username),
        )

    async def delete_account(self, username: str) -> None:
        """Delete a child account + revoke its sessions. Refuses admins (an admin
        is never deletable via this path)."""
        account = await self._get_account(username)
        if account is None:
            raise AuthError(f"no such account {username!r}")
        if (account.get("role") or "admin") == "admin":
            raise AuthError("cannot delete an admin account")
        await self.revoke_all(username)
        await self._db.execute(
            f"DELETE FROM {_T_ACCOUNT} WHERE username = ?", (username,)
        )

    async def complete_setup(
        self, refresh_token: str, new_auth_key: str, new_pin: str, *, ip: str | None
    ) -> None:
        """First-run reset for a frozen child: set the real password+PIN, clear
        must_reset, and revoke the temp session so they log in fresh. Requires a
        valid (non-revoked/used) refresh token for the frozen account."""
        try:
            claims = tokens.verify(self._secret, refresh_token, expected_type="refresh")
        except tokens.TokenError as exc:
            raise AuthError(f"invalid refresh: {exc}")
        username = claims.get("sub")
        jti = claims.get("jti")
        tok_secret = claims.get("s")
        if not isinstance(username, str):
            raise AuthError("malformed refresh")
        if not isinstance(jti, str) or not isinstance(tok_secret, str):
            raise AuthError("malformed refresh")
        row = await self._db.fetch_one(
            f"SELECT * FROM {_T_REFRESH} WHERE jti = ?", (jti,)
        )
        if (
            row is None
            or row["revoked"]
            or row["used"]
            or row["expires"] < time.time()
            or not self._verify(row["secret_hash"], tok_secret)
        ):
            raise AuthError("refresh revoked")
        account = await self._get_account(username)
        if account is None:
            raise AuthError("no such account")
        if not bool(account.get("must_reset")):
            raise AuthError("account is not pending setup")
        await self._db.execute(
            f"UPDATE {_T_ACCOUNT} SET pw_hash = ?, pin_hash = ?, must_reset = 0 "
            f"WHERE username = ?",
            (self._ph.hash(new_auth_key), self._ph.hash(new_pin), username),
        )
        await self.revoke_all(username)
        await self._audit("complete_setup", True, ip, username)

    async def set_pin(self, username: str, pin: str) -> None:
        if await self._get_account(username) is None:
            raise AuthError(f"no such account {username!r}")
        await self._db.execute(
            f"UPDATE {_T_ACCOUNT} SET pin_hash = ? WHERE username = ?",
            (self._ph.hash(pin), username),
        )

    async def set_password(self, username: str, auth_key: str) -> None:
        if await self._get_account(username) is None:
            raise AuthError(f"no such account {username!r}")
        await self._db.execute(
            f"UPDATE {_T_ACCOUNT} SET pw_hash = ? WHERE username = ?",
            (self._ph.hash(auth_key), username),
        )
        # Changing the password invalidates all sessions.
        await self.revoke_all(username)

    # --- rate limiting / lockout ---------------------------------------------

    async def _check_locked(self, scope: str, key: str) -> None:
        row = await self._db.fetch_one(
            f"SELECT locked_until FROM {_T_ATTEMPTS} WHERE scope = ? AND key = ?",
            (scope, key),
        )
        locked_until = (row or {}).get("locked_until", 0) or 0
        now = time.time()
        if locked_until > now:
            raise AuthError("too many attempts", retry_after=locked_until - now)

    async def _record_failure(self, scope: str, key: str) -> None:
        now = time.time()
        row = await self._db.fetch_one(
            f"SELECT fails FROM {_T_ATTEMPTS} WHERE scope = ? AND key = ?",
            (scope, key),
        )
        fails = int((row or {}).get("fails", 0)) + 1
        locked_until = 0.0
        if fails >= self._cfg.max_attempts:
            delay = min(
                self._cfg.lockout_cap_s,
                self._cfg.lockout_base_s * (2 ** (fails - self._cfg.max_attempts)),
            )
            locked_until = now + delay
        await self._db.execute(
            f"INSERT INTO {_T_ATTEMPTS} (scope, key, fails, locked_until, updated) "
            f"VALUES (?, ?, ?, ?, ?) "
            f"ON CONFLICT(scope, key) DO UPDATE SET fails = ?, locked_until = ?, updated = ?",
            (scope, key, fails, locked_until, now, fails, locked_until, now),
        )

    async def _reset_attempts(self, scope: str, key: str) -> None:
        await self._db.execute(
            f"DELETE FROM {_T_ATTEMPTS} WHERE scope = ? AND key = ?", (scope, key)
        )

    # --- audit ---------------------------------------------------------------

    async def _audit(self, event: str, ok: bool, ip: str | None, detail: str = "") -> None:
        await self._db.execute(
            f"INSERT INTO {_T_AUDIT} (ts, event, ok, ip, detail) VALUES (?, ?, ?, ?, ?)",
            (time.time(), event, 1 if ok else 0, ip, detail),
        )

    # --- token minting -------------------------------------------------------

    def _mint_access(
        self, username: str, family_id: str, *, role: str = "admin", must_reset: bool = False
    ) -> str:
        now = time.time()
        return tokens.sign(
            self._secret,
            {
                "typ": "access",
                "sub": username,
                "fam": family_id,
                # role + must_reset travel in the token so the gate and
                # require_admin stay stateless (no DB hit per request). They go
                # stale only until the next mint; complete_setup revokes + forces
                # a fresh login, and a role change is rare + can revoke_all.
                "role": role,
                "mr": 1 if must_reset else 0,
                "iat": int(now),
                "exp": int(now + self._cfg.access_ttl_s),
            },
        )

    async def _mint_refresh(self, username: str, family_id: str) -> str:
        """Create a fresh refresh token in ``family_id`` and persist its row.

        The token carries a random per-token secret; we store only its hash, so a
        DB leak can't forge a refresh. Rotation = new jti + new secret in the
        same family.
        """
        jti = secrets.token_urlsafe(12)
        tok_secret = secrets.token_urlsafe(24)
        now = time.time()
        expires = now + self._cfg.refresh_ttl_s
        secret_hash = self._ph.hash(tok_secret)
        await self._db.execute(
            f"INSERT INTO {_T_REFRESH} "
            f"(jti, family_id, username, secret_hash, issued, expires) "
            f"VALUES (?, ?, ?, ?, ?, ?)",
            (jti, family_id, username, secret_hash, now, expires),
        )
        # The signed wrapper lets us reject tampered tokens before any DB hit.
        return tokens.sign(
            self._secret,
            {
                "typ": "refresh",
                "sub": username,
                "fam": family_id,
                "jti": jti,
                "s": tok_secret,
                "iat": int(now),
                "exp": int(expires),
            },
        )

    # --- public API ----------------------------------------------------------

    async def login(
        self, username: str, auth_key: str, *, pin: str | None = None, ip: str | None
    ) -> LoginResult:
        """Verify credentials and start a brand-new refresh family."""
        await self._check_locked("ip", ip or "?")
        await self._check_locked("account", username)

        account = await self._get_account(username)
        # Always verify against *something* to equalize timing.
        target_hash = account["pw_hash"] if account else self._dummy_hash
        ok = self._verify(target_hash, auth_key)

        role = (account or {}).get("role") or "admin"
        must_reset = bool((account or {}).get("must_reset"))
        pin_ok = True
        if account and must_reset:
            pin_hash = account.get("pin_hash")
            pin_ok = bool(pin and pin_hash and self._verify(pin_hash, pin))

        if not account or not ok or not pin_ok:
            await self._record_failure("ip", ip or "?")
            await self._record_failure("account", username)
            await self._audit("login", False, ip, username)
            raise AuthError("invalid credentials")

        await self._reset_attempts("ip", ip or "?")
        await self._reset_attempts("account", username)

        family_id = secrets.token_urlsafe(12)
        access = self._mint_access(username, family_id, role=role, must_reset=must_reset)
        refresh = await self._mint_refresh(username, family_id)
        await self._audit("login", True, ip, username)
        return LoginResult(access, refresh, family_id, username, role=role, must_reset=must_reset)

    async def refresh(self, refresh_token: str, *, ip: str | None) -> LoginResult:
        """Rotate a refresh token. Detects reuse and revokes the family."""
        try:
            claims = tokens.verify(self._secret, refresh_token, expected_type="refresh")
        except tokens.TokenError as exc:
            raise AuthError(f"invalid refresh: {exc}")

        jti = claims.get("jti")
        family_id = claims.get("fam")
        username = claims.get("sub")
        tok_secret = claims.get("s")
        if not all(isinstance(x, str) for x in (jti, family_id, username, tok_secret)):
            raise AuthError("malformed refresh")

        row = await self._db.fetch_one(
            f"SELECT * FROM {_T_REFRESH} WHERE jti = ?", (jti,)
        )
        if row is None or row["revoked"]:
            # Unknown or already-revoked jti — treat as compromise; nuke family.
            await self._revoke_family(family_id)
            await self._audit("refresh", False, ip, f"revoked/unknown jti fam={family_id}")
            raise AuthError("refresh revoked")
        if row["used"]:
            # Reuse of a rotated token => theft. Revoke the whole family.
            await self._revoke_family(family_id)
            await self._audit("refresh", False, ip, f"reuse detected fam={family_id}")
            raise AuthError("refresh reuse detected")
        if not self._verify(row["secret_hash"], tok_secret):
            await self._revoke_family(family_id)
            await self._audit("refresh", False, ip, "secret mismatch")
            raise AuthError("refresh secret mismatch")

        # Mark the presented token used (rotation) and mint a successor.
        await self._db.execute(
            f"UPDATE {_T_REFRESH} SET used = 1 WHERE jti = ?", (jti,)
        )
        account = await self._get_account(username)
        role = (account or {}).get("role") or "admin"
        must_reset = bool((account or {}).get("must_reset"))
        access = self._mint_access(username, family_id, role=role, must_reset=must_reset)
        new_refresh = await self._mint_refresh(username, family_id)
        await self._audit("refresh", True, ip, username)
        return LoginResult(access, new_refresh, family_id, username, role=role, must_reset=must_reset)

    async def unlock(self, refresh_token: str, pin: str, *, ip: str | None) -> LoginResult:
        """Mini-PIN re-unlock: needs a still-valid refresh token. Mints a new
        access token (and rotates the refresh). Wrong PINs are counted on the
        family; after ``pin_max_attempts`` the family is downgraded so the next
        prompt must be the full password."""
        await self._check_locked("ip", ip or "?")
        try:
            claims = tokens.verify(self._secret, refresh_token, expected_type="refresh")
        except tokens.TokenError as exc:
            raise AuthError(f"invalid refresh: {exc}")

        family_id = claims.get("fam")
        username = claims.get("sub")
        jti = claims.get("jti")
        if not all(isinstance(x, str) for x in (family_id, username, jti)):
            raise AuthError("malformed refresh")

        row = await self._db.fetch_one(
            f"SELECT * FROM {_T_REFRESH} WHERE jti = ?", (jti,)
        )
        if row is None or row["revoked"] or row["used"]:
            await self._revoke_family(family_id)
            raise AuthError("refresh invalid")
        if row["downgraded"]:
            raise AuthError("password required")

        account = await self._get_account(username)
        has_pin = bool(account and account.get("pin_hash"))
        pin_hash = account["pin_hash"] if has_pin else self._dummy_hash
        # Always verify (even with no PIN set) to keep timing constant.
        ok = self._verify(pin_hash, pin) and has_pin

        if not ok:
            fails = int(row["pin_fails"]) + 1
            downgrade = fails >= self._cfg.pin_max_attempts
            await self._db.execute(
                f"UPDATE {_T_REFRESH} SET pin_fails = ?, downgraded = ? WHERE family_id = ?",
                (fails, 1 if downgrade else 0, family_id),
            )
            await self._record_failure("ip", ip or "?")
            await self._audit("unlock", False, ip, f"fails={fails}")
            raise AuthError("password required" if downgrade else "invalid pin")

        await self._reset_attempts("ip", ip or "?")
        await self._db.execute(
            f"UPDATE {_T_REFRESH} SET pin_fails = 0, used = 1 WHERE jti = ?", (jti,)
        )
        role = (account or {}).get("role") or "admin"
        must_reset = bool((account or {}).get("must_reset"))
        access = self._mint_access(username, family_id, role=role, must_reset=must_reset)
        new_refresh = await self._mint_refresh(username, family_id)
        await self._audit("unlock", True, ip, username)
        return LoginResult(access, new_refresh, family_id, username, role=role, must_reset=must_reset)

    async def logout(self, refresh_token: str | None) -> None:
        """Revoke the family of the presented refresh token (this device)."""
        if not refresh_token:
            return
        try:
            claims = tokens.verify(self._secret, refresh_token, expected_type="refresh")
        except tokens.TokenError:
            return
        family_id = claims.get("fam")
        if isinstance(family_id, str):
            await self._revoke_family(family_id)
            await self._audit("logout", True, None, family_id)

    async def revoke_all(self, username: str | None = None) -> None:
        """Log out everywhere (optionally for one user)."""
        if username:
            await self._db.execute(
                f"UPDATE {_T_REFRESH} SET revoked = 1 WHERE username = ?", (username,)
            )
        else:
            await self._db.execute(f"UPDATE {_T_REFRESH} SET revoked = 1")

    async def _revoke_family(self, family_id: str) -> None:
        await self._db.execute(
            f"UPDATE {_T_REFRESH} SET revoked = 1 WHERE family_id = ?", (family_id,)
        )

    def verify_access(self, access_token: str) -> dict[str, Any]:
        """Stateless access-token check (signature + exp). Raises AuthError."""
        try:
            return tokens.verify(self._secret, access_token, expected_type="access")
        except tokens.TokenError as exc:
            raise AuthError(str(exc))

    async def session_state(self, refresh_token: str | None) -> str:
        """What the client should show when there's no valid access token:
        'pin' if a usable (non-downgraded, unexpired) refresh exists,
        else 'password'. A frozen child should always re-enter via the password
        screen (its temp session is short-lived), so we never offer PIN there."""
        if not refresh_token:
            return "password"
        try:
            claims = tokens.verify(self._secret, refresh_token, expected_type="refresh")
        except tokens.TokenError:
            return "password"
        row = await self._db.fetch_one(
            f"SELECT revoked, used, downgraded FROM {_T_REFRESH} WHERE jti = ?",
            (claims.get("jti"),),
        )
        if row is None or row["revoked"] or row["downgraded"]:
            return "password"
        username = claims.get("sub")
        if isinstance(username, str):
            account = await self._get_account(username)
            if account is not None and bool(account.get("must_reset")):
                return "password"
        return "pin"

    # --- helpers -------------------------------------------------------------

    def _verify(self, stored_hash: str, candidate: str) -> bool:
        """Argon2id verify, swallowing the mismatch into a bool. Always does the
        full hash work (constant-ish time) even on the dummy path."""
        try:
            self._ph.verify(stored_hash, candidate)
            return True
        except (VerifyMismatchError, InvalidHashError):
            return False
        except Exception:  # noqa: BLE001
            log.exception("argon2 verify error")
            return False


# --- secret + hashing helpers shared with the CLI ----------------------------


def load_or_create_secret(path: Any, *, create: bool = False) -> bytes:
    """Load the HMAC signing secret, or (when ``create``) generate it with 600
    perms. The CLI creates it; the app only loads it."""
    from pathlib import Path

    p = Path(path)
    if p.is_file():
        return p.read_bytes()
    if not create:
        raise FileNotFoundError(
            f"auth secret not found at {p} — run `raspy-auth create-account` first"
        )
    p.parent.mkdir(parents=True, exist_ok=True)
    secret = os.urandom(32)
    # Write with restrictive perms from the start.
    fd = os.open(p, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    with os.fdopen(fd, "wb") as fh:
        fh.write(secret)
    return secret


def hasher_from_settings(settings: AuthSettings) -> PasswordHasher:
    return PasswordHasher(
        time_cost=settings.argon_time_cost,
        memory_cost=settings.argon_memory_kib,
        parallelism=settings.argon_parallelism,
    )

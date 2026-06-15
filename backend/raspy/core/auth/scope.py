"""Request-scoped "current account" — the seam for per-account data isolation.

There is one Pi but (now) many accounts, and every account must be totally
isolated: its own vault, calendar, notes, etc. Attachments don't see the request,
they just call ``self.db.table(...)`` / use a data dir — so we propagate *who is
asking* out-of-band via a ``ContextVar`` set by the auth gate (core/app.py) and
the WS endpoint, and read it lazily wherever storage is resolved.

``account_slug`` turns an arbitrary username into a filesystem/SQL-safe token
(usernames can contain anything; table names and dirs can't). The original admin
account is special-cased by callers to keep its *existing* unsuffixed tables and
data dir intact — see core/db.py and core/contract.py.
"""

from __future__ import annotations

import hashlib
from contextvars import ContextVar

# The username of the account making the current request, or None when there is
# no authenticated principal (pre-auth endpoints, background tasks, tests before
# a fixture sets it). Default None so a missing context never crashes — callers
# decide the fallback (usually the legacy/global scope).
current_account: ContextVar[str | None] = ContextVar("current_account", default=None)

# True when the current account should use the *legacy* (unsuffixed) storage
# prefix / data dir — i.e. the original admin, whose vault/calendar/etc. predate
# isolation and must stay readable. Set by the auth gate alongside
# ``current_account``. Defaults True so that an unset context (background tasks,
# pre-isolation tests) keeps the historical global behaviour.
current_account_legacy: ContextVar[bool] = ContextVar(
    "current_account_legacy", default=True
)


def account_slug(username: str) -> str:
    """A short, stable, SQL/FS-safe token for an account.

    ``u<hex8>`` where the hex is the first 8 chars of sha256(username). Matches
    ``[a-z][a-z0-9_]*`` (so it passes db._validate_ident) and never collides with
    a real attachment id. Stable across restarts since it's a pure hash.
    """
    digest = hashlib.sha256(username.encode("utf-8")).hexdigest()[:8]
    return f"u{digest}"

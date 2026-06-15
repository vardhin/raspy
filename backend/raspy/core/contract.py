"""The attachment contract. See plan/20-attachments.md.

An attachment is a self-contained mini-app providing backend logic *and* its own
UI descriptor. Subclass :class:`BaseAttachment`, set the identity fields, and
implement ``router()`` and ``ui()``. A trivial attachment is ~20 lines.

The package must expose a module-level ``attachment`` instance (or be registered
via the ``raspy.attachments`` entry point) so the registry can find it.
"""

from __future__ import annotations

import hashlib
import json
import contextlib
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Awaitable, Callable, Iterator

from fastapi import APIRouter

from typing import TYPE_CHECKING

from .db import ScopedDB
from .events import EventBus
from .ui import UINode

if TYPE_CHECKING:
    from .notifications import NotificationService


@dataclass
class AttachmentContext:
    """Everything the core hands an attachment at load time."""

    db: ScopedDB
    data_dir: Path
    events: EventBus
    config: dict[str, Any]
    notifications: "NotificationService | None" = None
    attachment_id: str = "core"
    # Returns ``[{"username", "role", ...}]`` for every account — wired to the
    # auth service by the registry. Lets background workers (e.g. the mail poller)
    # iterate each account's isolated storage. None in tests / when auth is down.
    accounts_provider: "Callable[[], Awaitable[list[dict[str, Any]]]] | None" = None

    async def list_accounts(self) -> list[dict[str, Any]]:
        """All accounts (no secrets). Empty if no provider is wired."""
        if self.accounts_provider is None:
            return []
        return await self.accounts_provider()

    @contextlib.contextmanager
    def account_scope(self, username: str, *, is_admin: bool) -> "Iterator[None]":
        """Run a block as if ``username`` made the request, so ScopedDB / data
        dirs resolve to that account. For background workers that have no HTTP
        request context. The admin keeps the legacy (unsuffixed) scope."""
        from .auth.scope import current_account, current_account_legacy

        tok_a = current_account.set(username)
        tok_l = current_account_legacy.set(is_admin)
        try:
            yield
        finally:
            current_account.reset(tok_a)
            current_account_legacy.reset(tok_l)

    @property
    def account_data_dir(self) -> Path:
        """The data dir for the account making the current request.

        The original admin keeps the legacy ``data_dir`` (so its existing files
        stay where they are); a child account gets an isolated
        ``data_dir/accounts/<slug>/`` subtree. Read the account from the
        ``current_account`` ContextVar at call time, so attachments must use this
        *inside* a request handler (not capture ``data_dir`` once at load).
        """
        # Imported lazily to avoid a core<->auth import cycle at module load.
        from .auth.scope import account_slug, current_account, current_account_legacy

        username = current_account.get()
        if username is None or current_account_legacy.get():
            return self.data_dir
        return self.data_dir / "accounts" / account_slug(username)

    def publish(self, topic: str, payload: Any = None) -> None:
        self.events.publish(topic, payload)

    async def notify(
        self,
        title: str,
        body: str = "",
        *,
        icon: str | None = None,
        url: str | None = None,
        data: dict[str, Any] | None = None,
    ) -> dict[str, Any] | None:
        """Send a notification (history + live WS + background push).

        Tagged with this attachment's id as the source. No-op (returns None) if
        the core notification service is unavailable, so attachments stay
        decoupled from whether notifications are configured.
        """
        if self.notifications is None:
            return None
        return await self.notifications.notify(
            title, body, source=self.attachment_id, icon=icon, url=url, data=data
        )


class BaseAttachment:
    """Base class for attachments. Override the fields and the two methods."""

    # --- identity (override these) ------------------------------------------
    id: str = ""  # stable slug, URL-safe, unique. e.g. "todo"
    title: str = ""  # human label. e.g. "Todo"
    icon: str = "square"  # icon id the shell knows
    version: str = "0.1.0"

    # Populated by the registry at load time.
    ctx: AttachmentContext

    # --- lifecycle (override as needed) -------------------------------------

    async def on_load(self, ctx: AttachmentContext) -> None:
        """Called once at startup. Create tables, start background tasks."""

    async def on_shutdown(self) -> None:
        """Called once at shutdown. Stop background tasks, flush state."""

    # --- contract surface (override) ----------------------------------------

    def router(self) -> APIRouter:
        """Return the attachment's API router (mounted at /api/att/<id>)."""
        return APIRouter()

    def ui(self) -> UINode | None:
        """Return the declarative UI descriptor (Tier 1), or None."""
        return None

    def ui_bundle(self) -> str | None:
        """Return a URL to a Tier-2 JS bundle, or None. See plan/20 §Tier 2."""
        return None

    # --- derived (don't override) -------------------------------------------

    @property
    def db(self) -> ScopedDB:
        return self.ctx.db

    @property
    def events(self) -> EventBus:
        return self.ctx.events

    @property
    def account_data_dir(self) -> Path:
        """Per-account data dir for the current request. See
        :attr:`AttachmentContext.account_data_dir`. Call inside a handler."""
        return self.ctx.account_data_dir

    async def notify(self, title: str, body: str = "", **kwargs: Any) -> Any:
        """Convenience: send a notification tagged with this attachment.
        See :meth:`AttachmentContext.notify`."""
        return await self.ctx.notify(title, body, **kwargs)

    def ui_version(self) -> str:
        """Hash of the UI descriptor, for client-side caching."""
        spec = self.ui()
        if spec is None:
            return "none"
        blob = json.dumps(spec, sort_keys=True, separators=(",", ":"))
        return hashlib.sha256(blob.encode()).hexdigest()[:12]

    def manifest_entry(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "title": self.title,
            "icon": self.icon,
            "version": self.version,
            "ui": self.ui(),
            "ui_version": self.ui_version(),
            "bundle": self.ui_bundle(),
        }

    def validate(self) -> None:
        if not self.id:
            raise ValueError(f"{type(self).__name__}: id is required")
        if not self.title:
            raise ValueError(f"{type(self).__name__}: title is required")

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
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from fastapi import APIRouter

from .db import ScopedDB
from .events import EventBus
from .ui import UINode


@dataclass
class AttachmentContext:
    """Everything the core hands an attachment at load time."""

    db: ScopedDB
    data_dir: Path
    events: EventBus
    config: dict[str, Any]

    def publish(self, topic: str, payload: Any = None) -> None:
        self.events.publish(topic, payload)


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

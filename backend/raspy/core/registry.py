"""Attachment discovery + lifecycle. See plan/20-attachments.md §3.

This is what makes the spine modular: drop an attachment package under
``raspy/attachments/`` (or a configured drop-in dir, or install one exposing the
``raspy.attachments`` entry point) and it is discovered, loaded, mounted, and
added to the UI manifest automatically — with no edits to the core server code.

A failing attachment is isolated: it's recorded as ``errored`` and surfaced in
the manifest / health, but never crashes the spine.
"""

from __future__ import annotations

import importlib
import importlib.util
import logging
import pkgutil
from dataclasses import dataclass, field
from importlib.metadata import entry_points
from pathlib import Path
from typing import Any

from fastapi import FastAPI

from ..config import Settings
from .contract import AttachmentContext, BaseAttachment
from .db import Database, ScopedDB
from .events import EventBus
from .notifications import NotificationService

log = logging.getLogger("raspy.registry")

_BUILTIN_PACKAGE = "raspy.attachments"
_ENTRY_POINT_GROUP = "raspy.attachments"


@dataclass
class LoadedAttachment:
    attachment: BaseAttachment
    source: str  # "builtin" | "dropin" | "entrypoint"


@dataclass
class AttachmentError:
    id: str
    source: str
    error: str


@dataclass
class AttachmentRegistry:
    app: FastAPI
    settings: Settings
    db: Database
    events: EventBus
    notifications: NotificationService | None = None

    loaded: dict[str, LoadedAttachment] = field(default_factory=dict)
    errors: list[AttachmentError] = field(default_factory=list)

    # --- discovery -----------------------------------------------------------

    def _discover(self) -> list[tuple[BaseAttachment, str]]:
        """Find all candidate attachments without loading them yet."""
        found: list[tuple[BaseAttachment, str]] = []
        found += self._discover_builtins()
        found += self._discover_dropins()
        found += self._discover_entrypoints()
        return found

    def _instance_from_module(self, module: Any) -> BaseAttachment | None:
        """An attachment module exposes a module-level ``attachment`` instance,
        or a single ``BaseAttachment`` subclass we can instantiate."""
        obj = getattr(module, "attachment", None)
        if isinstance(obj, BaseAttachment):
            return obj
        # Fallback: a lone BaseAttachment subclass defined in the module.
        for value in vars(module).values():
            if (
                isinstance(value, type)
                and issubclass(value, BaseAttachment)
                and value is not BaseAttachment
                and value.__module__ == module.__name__
            ):
                return value()
        return None

    def _discover_builtins(self) -> list[tuple[BaseAttachment, str]]:
        out: list[tuple[BaseAttachment, str]] = []
        try:
            pkg = importlib.import_module(_BUILTIN_PACKAGE)
        except ModuleNotFoundError:
            return out
        for info in pkgutil.iter_modules(pkg.__path__):
            if not info.ispkg and info.name.startswith("_"):
                continue
            mod_name = f"{_BUILTIN_PACKAGE}.{info.name}"
            try:
                module = importlib.import_module(mod_name)
                inst = self._instance_from_module(module)
                if inst is not None:
                    out.append((inst, "builtin"))
            except Exception as exc:  # noqa: BLE001 - isolate bad attachment
                self.errors.append(AttachmentError(info.name, "builtin", repr(exc)))
                log.exception("failed importing builtin attachment %s", info.name)
        return out

    def _discover_dropins(self) -> list[tuple[BaseAttachment, str]]:
        out: list[tuple[BaseAttachment, str]] = []
        d: Path | None = self.settings.attachments_dir
        if not d or not d.is_dir():
            return out
        for child in sorted(d.iterdir()):
            init = child / "__init__.py"
            name = child.name
            if not init.is_file() or name.startswith("_"):
                continue
            try:
                spec = importlib.util.spec_from_file_location(
                    f"raspy_dropin_{name}", init
                )
                if spec is None or spec.loader is None:
                    continue
                module = importlib.util.module_from_spec(spec)
                spec.loader.exec_module(module)
                inst = self._instance_from_module(module)
                if inst is not None:
                    out.append((inst, "dropin"))
            except Exception as exc:  # noqa: BLE001
                self.errors.append(AttachmentError(name, "dropin", repr(exc)))
                log.exception("failed importing drop-in attachment %s", name)
        return out

    def _discover_entrypoints(self) -> list[tuple[BaseAttachment, str]]:
        out: list[tuple[BaseAttachment, str]] = []
        try:
            eps = entry_points(group=_ENTRY_POINT_GROUP)
        except Exception:  # noqa: BLE001
            return out
        for ep in eps:
            try:
                obj = ep.load()
                inst = obj() if isinstance(obj, type) else obj
                if isinstance(inst, BaseAttachment):
                    out.append((inst, "entrypoint"))
            except Exception as exc:  # noqa: BLE001
                self.errors.append(AttachmentError(ep.name, "entrypoint", repr(exc)))
                log.exception("failed loading entry-point attachment %s", ep.name)
        return out

    # --- lifecycle -----------------------------------------------------------

    async def load_all(self) -> None:
        disabled = set(self.settings.disabled_attachments)
        for inst, source in self._discover():
            try:
                inst.validate()
            except Exception as exc:  # noqa: BLE001
                self.errors.append(
                    AttachmentError(getattr(inst, "id", "?"), source, repr(exc))
                )
                continue

            if inst.id in disabled:
                log.info("attachment %s disabled by config", inst.id)
                continue
            if inst.id in self.loaded:
                self.errors.append(
                    AttachmentError(inst.id, source, "duplicate id (already loaded)")
                )
                continue

            try:
                await self._load_one(inst, source)
            except Exception as exc:  # noqa: BLE001
                self.errors.append(AttachmentError(inst.id, source, repr(exc)))
                log.exception("failed loading attachment %s", inst.id)

    async def _load_one(self, inst: BaseAttachment, source: str) -> None:
        data_dir = self.settings.attachment_data_dir(inst.id)
        data_dir.mkdir(parents=True, exist_ok=True)
        ctx = AttachmentContext(
            db=ScopedDB(self.db, inst.id),
            data_dir=data_dir,
            events=self.events,
            config=self.settings.attachment_config(inst.id),
            notifications=self.notifications,
            attachment_id=inst.id,
        )
        inst.ctx = ctx
        await inst.on_load(ctx)
        self.app.include_router(
            inst.router(),
            prefix=f"/api/att/{inst.id}",
            tags=[f"att:{inst.id}"],
        )
        self.loaded[inst.id] = LoadedAttachment(attachment=inst, source=source)
        log.info("loaded attachment %s (%s) from %s", inst.id, inst.version, source)

    async def shutdown_all(self) -> None:
        for entry in self.loaded.values():
            try:
                await entry.attachment.on_shutdown()
            except Exception:  # noqa: BLE001
                log.exception("error shutting down %s", entry.attachment.id)

    # --- introspection -------------------------------------------------------

    def manifest(self) -> list[dict[str, Any]]:
        return [e.attachment.manifest_entry() for e in self.loaded.values()]

    def status(self) -> dict[str, Any]:
        return {
            "loaded": [
                {"id": e.attachment.id, "version": e.attachment.version, "source": e.source}
                for e in self.loaded.values()
            ],
            "errored": [
                {"id": err.id, "source": err.source, "error": err.error}
                for err in self.errors
            ],
        }

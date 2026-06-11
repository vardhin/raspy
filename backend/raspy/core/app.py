"""App factory. See plan/10-spine.md §3.

Wires core routers (always present) and, in the lifespan, discovers + loads every
attachment. Attachment routers are mounted under /api/att/<id> by the registry —
no core edits needed to add one.
"""

from __future__ import annotations

import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from ..config import Settings, get_settings
from . import manifest, system, ws
from .db import Database
from .events import EventBus
from .registry import AttachmentRegistry

log = logging.getLogger("raspy")


@asynccontextmanager
async def lifespan(app: FastAPI):
    settings: Settings = app.state.settings

    db = Database(settings.db_path)
    db.connect()
    app.state.db = db

    events = EventBus()
    app.state.events = events

    registry = AttachmentRegistry(app=app, settings=settings, db=db, events=events)
    await registry.load_all()
    app.state.registry = registry

    log.info(
        "spine ready: %d attachment(s) loaded, %d errored",
        len(registry.loaded),
        len(registry.errors),
    )
    try:
        yield
    finally:
        await registry.shutdown_all()
        db.close()


def create_app(settings: Settings | None = None) -> FastAPI:
    settings = settings or get_settings()

    app = FastAPI(title="Raspy Spine", version="0.1.0", lifespan=lifespan)
    app.state.settings = settings

    # CORS: the served shell is same-origin; in dev the Vite server (5173) and a
    # Capacitor APK use different origins. Tighten in production via config.
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_credentials=False,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # Core routers — always present, independent of any attachment.
    app.include_router(system.router, prefix="/api")
    app.include_router(manifest.router, prefix="/api")
    app.include_router(ws.router, prefix="/api")

    return app

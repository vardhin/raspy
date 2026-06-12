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
from fastapi.responses import JSONResponse

from ..config import Settings, get_settings
from . import manifest, notifications, static, system, ws
from .auth import AuthService
from .auth import router as auth_router
from .auth.deps import principal_from_request
from .auth.service import load_or_create_secret
from .db import Database
from .events import EventBus
from .notifications import NotificationService
from .registry import AttachmentRegistry

# /api paths reachable without a valid access token. Everything else under /api
# (including attachment routers mounted at startup, the WS, manifest, etc.)
# requires auth via the gate middleware below.
_PUBLIC_API_PREFIXES = (
    "/api/auth/",       # login / refresh / unlock / session / kdf
    "/api/healthz",
    "/api/channel/",    # Layer-1 handshake (pubkey + handshake) — pre-auth
)

log = logging.getLogger("raspy")


@asynccontextmanager
async def lifespan(app: FastAPI):
    settings: Settings = app.state.settings

    db = Database(settings.db_path)
    db.connect()
    app.state.db = db

    # Auth: load the signing secret (created by `raspy-auth create-account`) and
    # stand up the service. If the secret is missing the spine still boots, but
    # the gate will 401 everything protected until an account is created.
    try:
        secret = load_or_create_secret(settings.auth_secret_path, create=False)
        auth = AuthService(db=db, settings=settings.auth, secret=secret)
        await auth.init()
        app.state.auth = auth
        if not await auth.has_account():
            log.warning("no account yet — run `raspy-auth create-account`")
    except FileNotFoundError:
        app.state.auth = None
        log.warning(
            "auth secret missing — run `raspy-auth create-account`; "
            "protected API will 401 until then"
        )

    events = EventBus()
    app.state.events = events

    notifier = NotificationService(db=db, events=events, settings=settings)
    await notifier.init()
    notifier.start()  # background outbox drain worker
    app.state.notifications = notifier

    registry = AttachmentRegistry(
        app=app, settings=settings, db=db, events=events, notifications=notifier
    )
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
        await notifier.stop()
        db.close()


def create_app(settings: Settings | None = None) -> FastAPI:
    settings = settings or get_settings()

    app = FastAPI(title="Raspy Spine", version="0.1.0", lifespan=lifespan)
    app.state.settings = settings

    # The served shell is same-origin (no CORS needed); the Vite dev server and a
    # native client are cross-origin and need an explicit allow-list. Cookie auth
    # requires credentialed CORS, which forbids "*" — hence a configured list.
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # Global auth gate: enforce a valid access token for every /api path except
    # the public allow-list. Runs for attachment routers too (they're mounted at
    # startup), so no per-attachment wiring is needed. The WS path is allowed
    # through here and authenticates itself inside ws_endpoint (middleware can't
    # read the handshake the way a route dependency can).
    @app.middleware("http")
    async def auth_gate(request, call_next):
        path = request.url.path
        if not path.startswith("/api/"):
            return await call_next(request)  # static shell, etc.
        if path == "/api/ws" or any(path.startswith(p) for p in _PUBLIC_API_PREFIXES):
            return await call_next(request)
        if principal_from_request(request) is None:
            return JSONResponse({"detail": "authentication required"}, status_code=401)
        return await call_next(request)

    # Core routers — always present, independent of any attachment.
    app.include_router(auth_router.router, prefix="/api")
    app.include_router(system.router, prefix="/api")
    app.include_router(manifest.router, prefix="/api")
    app.include_router(ws.router, prefix="/api")
    app.include_router(notifications.router, prefix="/api")

    # Frontend last: the SPA catch-all must not shadow the /api routes above.
    static.mount_frontend(app, settings.static_dir)

    return app

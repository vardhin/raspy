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

from .. import __version__
from ..config import Settings, get_settings
from . import manifest, notifications, static, system, update_routes, ws
from .auth import AuthService
from .auth import router as auth_router
from .auth.deps import principal_from_request
from .auth.scope import current_account, current_account_legacy
from .auth.service import load_or_create_secret
from .channel import ChannelService
from .channel import router as channel_router
from .channel.middleware import ChannelMiddleware
from .channel.service import load_static_pem
from .db import Database
from .events import EventBus
from .notifications import NotificationService
from .registry import AttachmentRegistry
from .updater import Updater

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

    # Layer-1 channel: load the static key (created by raspy-auth) and stand up
    # the handshake/seal service. Optional — if absent or disabled, the channel
    # middleware is a no-op and traffic flows in cleartext (LAN/dev).
    app.state.channel = None
    if settings.channel.enabled:
        try:
            pem = load_static_pem(settings.channel_key_path)
            app.state.channel = ChannelService(settings.channel, pem)
        except FileNotFoundError:
            log.warning(
                "channel key missing — run `raspy-auth gen-channel-key`; "
                "Layer-1 encryption disabled until then"
            )

    events = EventBus()
    app.state.events = events

    notifier = NotificationService(db=db, events=events, settings=settings)
    await notifier.init()
    notifier.start()  # background outbox drain worker
    app.state.notifications = notifier

    registry = AttachmentRegistry(
        app=app, settings=settings, db=db, events=events, notifications=notifier,
        auth=app.state.auth,
    )
    await registry.load_all()
    app.state.registry = registry

    # Self-update: periodic check + one-click apply. Safe on a source checkout
    # (it just reports updatable=False). Uses the same event bus + notifier so an
    # available update surfaces as a live banner and a bell entry.
    updater = Updater(settings=settings, events=events, notifications=notifier)
    updater.start()
    app.state.updater = updater

    log.info(
        "spine ready: %d attachment(s) loaded, %d errored",
        len(registry.loaded),
        len(registry.errors),
    )
    try:
        yield
    finally:
        await updater.stop()
        await registry.shutdown_all()
        await notifier.stop()
        db.close()


def create_app(settings: Settings | None = None) -> FastAPI:
    settings = settings or get_settings()

    app = FastAPI(title="Raspy Spine", version=__version__, lifespan=lifespan)
    app.state.settings = settings

    # Middleware order matters. Starlette wraps later-added middleware OUTERMOST,
    # so we add inner→outer to get the runtime order:
    #   CORS → ChannelMiddleware(decrypt req / encrypt resp) → auth gate → routers
    # The channel layer must decrypt before the gate inspects auth cookies/headers,
    # and CORS must be outermost so even error/decrypt responses get CORS headers.

    # (innermost) Global auth gate: valid access token required for /api/* except
    # the public allow-list. Covers attachment routers mounted later by the
    # registry. The WS path passes through here and authenticates itself inside
    # ws_endpoint (middleware can't read the WS handshake like a route dep can).
    @app.middleware("http")
    async def auth_gate(request, call_next):
        path = request.url.path
        if not path.startswith("/api/"):
            return await call_next(request)  # static shell, etc.
        if path == "/api/ws" or any(path.startswith(p) for p in _PUBLIC_API_PREFIXES):
            return await call_next(request)
        principal = principal_from_request(request)
        if principal is None:
            return JSONResponse({"detail": "authentication required"}, status_code=401)
        # A frozen child (temp creds, not yet reset) may touch nothing but the
        # auth endpoints (its only legal move is /api/auth/complete-setup).
        if principal.must_reset:
            return JSONResponse({"detail": "account setup required"}, status_code=403)
        if not principal.is_admin and path.startswith("/api/att/"):
            app_id = path.removeprefix("/api/att/").split("/", 1)[0]
            svc = getattr(request.app.state, "auth", None)
            allowed = await svc.allowed_apps_of(principal.username) if svc else []
            if app_id in manifest._ADMIN_ONLY or app_id not in set(allowed or []):
                return JSONResponse({"detail": "app not allowed"}, status_code=403)
        # Per-account isolation: stamp who is asking so ScopedDB / data dirs land
        # in this account's namespace. Admin keeps the legacy (unsuffixed) scope
        # so its pre-isolation data stays reachable; children get an isolated one.
        tok_account = current_account.set(principal.username)
        tok_legacy = current_account_legacy.set(principal.is_admin)
        try:
            return await call_next(request)
        finally:
            current_account.reset(tok_account)
            current_account_legacy.reset(tok_legacy)

    # Channel decrypt/encrypt (no-op unless the request carries a channel session
    # header AND the service is up). Reads the service lazily from app.state since
    # it's constructed in the lifespan, after create_app().
    app.add_middleware(ChannelMiddleware, service_getter=lambda: getattr(app.state, "channel", None))

    # (outermost) CORS. Credentialed (cookie) CORS forbids "*", so an explicit
    # allow-list is required in production.
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # Core routers — always present, independent of any attachment.
    app.include_router(channel_router.router, prefix="/api")
    app.include_router(auth_router.router, prefix="/api")
    app.include_router(system.router, prefix="/api")
    app.include_router(manifest.router, prefix="/api")
    app.include_router(ws.router, prefix="/api")
    app.include_router(notifications.router, prefix="/api")
    app.include_router(update_routes.router, prefix="/api")

    # Frontend last: the SPA catch-all must not shadow the /api routes above.
    static.mount_frontend(app, settings.static_dir)

    return app

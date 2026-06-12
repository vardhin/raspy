"""Serve the built SvelteKit frontend bundle from the spine itself.

In production there is no separate web server: the spine hosts both the API
(under /api/) and the static UI (everything else) on one origin, fronted by the
Cloudflare tunnel (app.vardhin.com). See plan/50-deployment.md §4.

The bundle is produced by @sveltejs/adapter-static (frontend/build/). Because the
UI uses client-side routes that have no file on disk (e.g. /a/<id>), we serve a
**SPA fallback**: any GET that doesn't map to a real file — and isn't an API or
WebSocket path — returns index.html, letting the in-browser router render the
view. This mirrors the adapter's ``fallback: 'index.html'`` config.

Routing/precedence note: attachment API routes are mounted under /api/att/<id>
at *startup* (in the lifespan), i.e. *after* create_app() runs. Anything we
register here at the root — a catch-all route OR a StaticFiles mount at "/" —
would be registered first and shadow those later routes. So we deliberately do
NOT claim "/". Instead:
  1. mount the content-hashed assets at their real subpath (/_app), and
  2. register a 404 exception handler that serves index.html (and the few
     root-level files) for non-/api GET misses.
The handler only fires once *all* routes — including the lifespan-registered API
routes — have been consulted and missed, so API 404s stay JSON and the UI shell
is served for everything else.
"""

from __future__ import annotations

import logging
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.responses import FileResponse, JSONResponse, Response
from fastapi.staticfiles import StaticFiles
from starlette.exceptions import HTTPException as StarletteHTTPException

log = logging.getLogger("raspy")

# Root-level files the bundle emits alongside _app/ (served by exact path).
_ROOT_FILES = ("sw.js", "robots.txt", "favicon.svg")


def mount_frontend(app: FastAPI, static_dir: Path) -> None:
    """Serve the static bundle with SPA fallback, without claiming "/".

    No-op (with a warning) if the bundle is missing, so the spine still boots and
    the API stays usable when the frontend hasn't been built yet.
    """
    index = static_dir / "index.html"
    if not index.is_file():
        log.warning(
            "frontend bundle not found at %s — UI will 404 until it's built "
            "(see scripts/build-frontend.sh). API is unaffected.",
            static_dir,
        )
        return

    # Content-hashed immutable assets. Safe to mount at a fixed subpath: it can't
    # collide with /api, and StaticFiles 404s (not 200-HTML) on a miss.
    assets = static_dir / "_app"
    if assets.is_dir():
        app.mount("/_app", StaticFiles(directory=assets), name="frontend-assets")

    # A few root-level files the SW / browser request by exact name.
    for name in _ROOT_FILES:
        path = static_dir / name
        if not path.is_file():
            continue

        # Bind `path` per-iteration via default arg.
        async def _serve(_: Request, _path: Path = path) -> Response:
            return FileResponse(_path)

        app.add_api_route(f"/{name}", _serve, methods=["GET"], include_in_schema=False)

    # SPA fallback: any unmatched GET that isn't an API path renders the shell.
    @app.exception_handler(StarletteHTTPException)
    async def spa_fallback(request: Request, exc: StarletteHTTPException) -> Response:
        path = request.url.path
        # Don't render the shell for API misses (stay JSON) or missing static
        # assets under /_app (a missing hashed asset is a deploy bug — let it
        # 404 rather than return HTML for a .js/.css request).
        if (
            exc.status_code == 404
            and request.method in ("GET", "HEAD")
            and not path.startswith("/api")
            and not path.startswith("/_app")
        ):
            return FileResponse(index)
        # Preserve normal error responses (API 404s stay JSON, etc.), including
        # any headers the raiser set (e.g. Retry-After on a 429 lockout).
        return JSONResponse(
            {"detail": exc.detail if exc.detail is not None else ""},
            status_code=exc.status_code,
            headers=getattr(exc, "headers", None),
        )

    log.info("serving frontend bundle from %s", static_dir)

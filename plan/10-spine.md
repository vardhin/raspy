# The Spine — FastAPI Core

The spine is the always-on FastAPI process. It owns nothing domain-specific; it
provides the **core services** that attachments plug into and the **plumbing**
clients talk to.

## 1. Responsibilities

The core does exactly these things and no more:

1. **HTTP/WS server** — single ASGI app (Uvicorn).
2. **Auth & sessions** — login, token issue/verify, rate limiting. See
   [30-auth-security.md](30-auth-security.md).
3. **Attachment registry** — discover, load, mount, and lifecycle-manage
   attachments. See [20-attachments.md](20-attachments.md).
4. **UI manifest endpoint** — aggregate every attachment's UI descriptor into one
   manifest the frontend fetches and caches.
5. **Event bus / WebSocket hub** — push events from attachments to clients
   (e.g. "new email arrived", "todo updated on another device").
6. **Static asset host** — serve the frontend shell *and* any UI bundles an
   attachment ships.
7. **System/health** — `/healthz`, version, attachment status.

Everything else (todos, email, etc.) lives in attachments.

## 2. Directory layout (proposed)

```
raspy/
├── pyproject.toml
├── raspy/
│   ├── __init__.py
│   ├── main.py                # app factory + uvicorn entry
│   ├── config.py              # settings (pydantic-settings, env + file)
│   ├── core/
│   │   ├── app.py             # create_app(): wires everything
│   │   ├── auth/              # see 30-auth-security.md
│   │   │   ├── routes.py
│   │   │   ├── service.py     # password hash/verify, lockout
│   │   │   └── tokens.py      # session token sign/verify
│   │   ├── registry.py        # attachment discovery + lifecycle
│   │   ├── contract.py        # Attachment base class / Protocol
│   │   ├── manifest.py        # builds the aggregated UI manifest
│   │   ├── events.py          # in-proc pub/sub + WS hub
│   │   ├── db.py              # SQLite connection mgmt, per-attachment ns
│   │   └── static.py          # serve shell + attachment UI bundles
│   └── attachments/           # built-in attachments live here
│       ├── todo/
│       └── ...                # (each is a package; see 20-attachments.md)
├── data/                      # SQLite files, secrets, runtime state (gitignored)
└── plan/
```

External/third-party attachments can also be loaded from a configured directory
or installed as packages exposing an entry point — see
[20-attachments.md](20-attachments.md) §discovery.

## 3. App lifecycle

```python
# core/app.py  (sketch — not final code)
def create_app() -> FastAPI:
    settings = load_settings()
    app = FastAPI(lifespan=lifespan)

    # core routers — always present
    app.include_router(auth.router,     prefix="/api/auth")
    app.include_router(manifest.router, prefix="/api")          # /api/manifest
    app.include_router(events.router,   prefix="/api")          # /api/ws
    app.include_router(system.router,   prefix="/api")          # /healthz etc.

    return app

@asynccontextmanager
async def lifespan(app):
    db.init()                          # open SQLite, run migrations
    registry = AttachmentRegistry(app) # discover + import attachments
    await registry.load_all()          # mount routers, register UI, start tasks
    app.state.registry = registry
    yield
    await registry.shutdown_all()      # graceful stop of background tasks
    db.close()
```

Key points:
- **Attachments mount under `/api/att/<name>/…`** so namespacing is automatic and
  collisions are impossible.
- Loading is in the `lifespan` so failures are visible at startup and background
  tasks (a mail poller, etc.) get a clean shutdown hook.

## 4. The aggregated UI manifest

The single most important endpoint for the frontend:

```
GET /api/manifest          → {
  "version": "<hash of all attachment UI specs>",
  "attachments": [
    {
      "name": "todo",
      "title": "Todo",
      "icon": "checkbox",
      "ui": { ...UI descriptor... },     # declarative (see 20-attachments.md)
      "ui_version": "abc123",            # for client-side caching
      "bundle": null                     # or a URL to a JS bundle escape hatch
    },
    ...
  ]
}
```

- The top-level `version` lets the frontend cheaply check "did anything change?"
  with a `HEAD`/`If-None-Match` (ETag). If unchanged, it uses its cache.
- Per-attachment `ui_version` lets it refetch only what changed.
- This is what makes "no frontend rebuild per attachment" real.

## 5. Data: SQLite, namespaced

- One SQLite database file, or one file per attachment under `data/`. Start with
  **one file, per-attachment table prefixes** (`todo_items`, `email_accounts`)
  for simplicity; a busy/locking attachment (mail server) can get its own file.
- The core hands each attachment a scoped DB handle so attachments can't read
  each other's tables by accident.
- WAL mode on; it's a single-writer-ish workload, fine for one user.

## 6. Configuration

`pydantic-settings`, layered: defaults → `data/config.toml` → env vars. Holds:
the bind address/port, secret key location, enabled attachments, auth tuning
(rate limits, lockout thresholds), trusted-transport hints (see
[30-auth-security.md](30-auth-security.md) §transport trust).

## 7. Why single-process / in-process to start

- Far easier to develop, debug, and deploy on a Pi.
- The attachment contract ([20-attachments.md](20-attachments.md)) is written so
  an attachment's *interface* doesn't reveal whether it's in-process or remote.
  When something genuinely needs isolation (the mail server, untrusted code), we
  can run it separately and have the core proxy to it — **without** touching the
  frontend or other attachments. We defer that until a concrete need appears.

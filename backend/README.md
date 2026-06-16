# Raspy Backend

The async FastAPI spine for Raspy. It owns auth, sessions, account visibility,
SQLite storage, the attachment registry, live events, notifications, and the
static frontend bundle in production.

Functionality lives in **attachments** that are auto-discovered, mounted, and
added to the UI manifest at startup. Adding one requires no edits to the core
server code. See [../plan](../plan) for the full architecture.

## Run

```sh
uv sync                       # install deps
uv run raspy-auth create-account
uv run raspy                  # start the spine (http://127.0.0.1:49317)
# or:
uv run uvicorn raspy.app:app --reload
```

Health/status: `GET /api/healthz` is public. The UI manifest
(`GET /api/manifest`), live events (`WS /api/ws`), notifications, and attachment
APIs require an authenticated session.

The CLI also provides:

```sh
uv run raspy-auth calibrate
uv run raspy-auth set-pin --username <name>
uv run raspy-auth reset-password --username <name>
uv run raspy-auth revoke-all --username <name>
uv run raspy-auth gen-channel-key
uv run raspy-vapid
```

## Test

```sh
uv run pytest -q
```

## Layout

```text
raspy/
|-- app.py              # uvicorn entry: `uvicorn raspy.app:app`
|-- __main__.py         # CLI entry: `uv run raspy`
|-- config.py           # layered settings (defaults < data/config.toml < env)
|-- core/
|   |-- app.py          # create_app() + lifespan (loads attachments)
|   |-- contract.py     # BaseAttachment + AttachmentContext
|   |-- registry.py     # auto-discovery + lifecycle
|   |-- db.py           # SQLite + per-attachment ScopedDB
|   |-- events.py       # in-process event bus
|   |-- ws.py           # WebSocket hub (/api/ws)
|   |-- manifest.py     # per-account UI manifest (/api/manifest, ETag)
|   |-- notifications.py # notification history + Web Push outbox
|   |-- static.py       # serves frontend/build/ with SPA fallback
|   |-- system.py       # /api/healthz
|   |-- channel/        # optional request/response encryption layer
|   |-- auth/           # accounts, sessions, PIN unlock, CLI
|   `-- ui.py           # declarative UI descriptor builders
`-- attachments/        # built-in attachments (auto-discovered)
    |-- accounts/       # account management
    |-- calendar/       # calendar entries + reminders + encrypted media
    |-- contacts/       # address book + keep-in-touch list + encrypted photos
    |-- files/          # confined file manager
    |-- mail/           # IMAP polling client
    |-- notes/          # quick notes
    |-- notifications/  # notification inbox
    |-- stats/          # system metrics
    |-- todo/           # persistent task list + live events
    |-- vault/          # encrypted vault storage
    `-- vibe/           # daily generated card
```

Runtime state lives in `data/` by default and is gitignored. That includes
SQLite, auth secrets, the channel key, and per-attachment data. Override with
`RASPY_DATA_DIR`.

## Configuration

Defaults are defined in `raspy/config.py`. They can be overridden with
environment variables (`RASPY_HOST`, `RASPY_PORT`, `RASPY_DATA_DIR`, and so on)
or with `data/config.toml`.

Attachment-specific config lives under `[attachments.<id>]` in `config.toml` and
is exposed as `self.ctx.config`.

## Adding an attachment (no core edits)

Create a package under `raspy/attachments/<id>/` exposing a module-level
`attachment` instance:

```python
# raspy/attachments/ping/__init__.py
from fastapi import APIRouter

from raspy.core.contract import BaseAttachment
from raspy.core import ui


class Ping(BaseAttachment):
    id = "ping"
    title = "Ping"
    icon = "activity"
    version = "0.1.0"

    def router(self) -> APIRouter:
        r = APIRouter()

        @r.get("/now")
        async def now():
            return {"pong": True}

        return r

    def ui(self):
        return ui.view(
            title="Ping",
            children=[ui.button("Ping", action=ui.get("now"))],
        )


attachment = Ping()
```

Restart and `ping` is discovered, mounted at `/api/att/ping/...`, and appears in
`/api/manifest`. The frontend renders its UI with no rebuild.

Discovery sources are built-ins here, an optional drop-in directory
(`RASPY_ATTACHMENTS_DIR`), and installed packages exposing the
`raspy.attachments` entry point. A failing attachment is isolated and reported
under `errored` in `/api/healthz`; it never crashes the spine.

### What each attachment gets

- `self.db` - a `ScopedDB`; `self.db.table("items")` becomes a namespaced table.
- `self.events` - publish live updates, for example
  `self.events.publish("todo.updated", payload)`.
- `self.ctx.data_dir` - a private directory under `data/att/<id>/`.
- `self.account_data_dir` - the current account's data directory inside request
  handlers.
- `self.ctx.config` - this attachment's `[attachments.<id>]` config slice.
- `self.notify(...)` - send notification history, live WebSocket events, and
  background push when VAPID is configured.

### The UI contract

`ui()` returns a declarative descriptor built with `raspy.core.ui` helpers.
Data/actions use relative paths (`"items"`, `"items/{id}/toggle"`) that the
frontend prefixes with `/api/att/<id>/`. The frontend maps each node `type` to a
themed component, so the backend ships structure and wiring rather than CSS.

See [../plan/20-attachments.md](../plan/20-attachments.md) and
[../plan/45-theming.md](../plan/45-theming.md).

# Raspy Spine (backend)

The async FastAPI control plane. Functionality lives in **attachments** (plugins)
that are auto-discovered, mounted, and added to the UI manifest at startup — adding
one requires **no edits to the core server code**. See [../plan](../plan) for the
full architecture.

## Run

```sh
uv sync                       # install deps
uv run raspy                  # start the spine (http://127.0.0.1:8787)
# or:
uv run uvicorn raspy.app:app --reload
```

Health/status: `GET /api/healthz` · UI manifest: `GET /api/manifest` ·
events: `WS /api/ws`.

## Test

```sh
uv run pytest -q
```

## Layout

```text
raspy/
├── app.py              # uvicorn entry: `uvicorn raspy.app:app`
├── __main__.py         # CLI entry: `uv run raspy`
├── config.py           # layered settings (defaults < data/config.toml < env)
├── core/
│   ├── app.py          # create_app() + lifespan (loads attachments)
│   ├── contract.py     # BaseAttachment + AttachmentContext
│   ├── registry.py     # auto-discovery + lifecycle (the modular engine)
│   ├── db.py           # SQLite + per-attachment ScopedDB
│   ├── events.py       # in-proc event bus
│   ├── ws.py           # WebSocket hub (/api/ws)
│   ├── manifest.py     # aggregated UI manifest (/api/manifest, ETag)
│   ├── system.py       # /api/healthz
│   └── ui.py           # declarative UI descriptor builders
└── attachments/        # built-in attachments (auto-discovered)
    ├── todo/           # persistent task list + live events
    └── notes/          # quick notes
```

Runtime state (SQLite, per-attachment data, future secrets) lives in `data/`
(gitignored). Override with `RASPY_DATA_DIR`.

## Adding an attachment (no core edits)

Create a package under `raspy/attachments/<id>/` exposing a module-level
`attachment` instance:

```python
# raspy/attachments/ping/__init__.py
from fastapi import APIRouter
from raspy.core.contract import BaseAttachment, AttachmentContext
from raspy.core import ui

class Ping(BaseAttachment):
    id, title, icon, version = "ping", "Ping", "activity", "0.1.0"

    def router(self) -> APIRouter:
        r = APIRouter()
        @r.get("/now")
        async def now(): return {"pong": True}
        return r

    def ui(self):
        return ui.view(title="Ping", children=[
            ui.button("Ping", action=ui.get("now")),
        ])

attachment = Ping()
```

Restart → `ping` is discovered, mounted at `/api/att/ping/…`, and appears in
`/api/manifest`. The frontend renders its UI with no rebuild.

**Discovery sources** (registry.py): built-ins here, an optional drop-in dir
(`RASPY_ATTACHMENTS_DIR`), and installed packages exposing the
`raspy.attachments` entry point. A failing attachment is isolated and reported
under `errored` in `/api/healthz` — it never crashes the spine.

### What each attachment gets (`self.ctx` / `AttachmentContext`)

- `self.db` — a `ScopedDB`; `self.db.table("items")` → `att_<id>_items` (namespaced).
- `self.events` — publish live updates: `self.events.publish("todo.updated", payload)`.
- `self.ctx.data_dir` — a private directory under `data/att/<id>/`.
- `self.ctx.config` — this attachment's `[attachments.<id>]` config slice.

### The UI contract

`ui()` returns a declarative descriptor (plain dicts via `raspy.core.ui` helpers).
Data/actions use **relative** paths (`"items"`, `"items/{id}/toggle"`) that the
frontend prefixes with `/api/att/<id>/`. The frontend maps each node `type` to a
themed, token-only component — so the backend ships structure + wiring, never CSS.
See [../plan/20-attachments.md](../plan/20-attachments.md) and
[../plan/45-theming.md](../plan/45-theming.md).

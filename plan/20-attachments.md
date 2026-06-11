# Attachments — The Plugin Contract

This is the heart of Raspy. An **attachment** is a self-contained mini-app that
provides both backend logic **and its own frontend UI**. The frontend shell never
hardcodes knowledge of any attachment.

## 1. What an attachment is

A Python package that exposes a single `Attachment` object the registry can load.
It declares:

- **Identity** — `name` (stable slug, used in URLs), `title`, `icon`, `version`.
- **API** — an `APIRouter` mounted at `/api/att/<name>/…`.
- **UI** — a *UI descriptor* (declarative) and/or a *bundle URL* (escape hatch).
- **Lifecycle hooks** — `on_load`, `on_shutdown` (start/stop background tasks).
- **Storage needs** — gets a namespaced DB handle and a data directory.
- **Permissions/capabilities** — what system access it needs (network, files,
  sending mail). Declared so we can reason about trust later.

## 2. The contract (sketch)

```python
# core/contract.py  — illustrative, not final
from fastapi import APIRouter
from typing import Protocol

class AttachmentContext:
    db: "ScopedDB"            # namespaced SQLite handle
    data_dir: "Path"          # private dir under data/att/<name>/
    events: "EventBus"        # publish/subscribe to push to clients
    config: dict              # this attachment's config slice

class Attachment(Protocol):
    name: str                 # "todo"  (slug, unique, URL-safe)
    title: str                # "Todo"
    icon: str                 # icon id the shell knows, or a shipped asset
    version: str

    def router(self) -> APIRouter: ...
    def ui(self) -> "UISpec | None": ...      # declarative descriptor
    def ui_bundle(self) -> str | None: ...    # or URL to a JS bundle
    async def on_load(self, ctx: AttachmentContext) -> None: ...
    async def on_shutdown(self) -> None: ...
```

A real attachment will subclass a `BaseAttachment` that fills in sensible
defaults, so a trivial attachment is ~20 lines.

## 3. Discovery & loading

The registry finds attachments three ways (in priority order):

1. **Built-in** — packages under `raspy/attachments/*`.
2. **Installed** — third-party packages that advertise an entry point group
   `raspy.attachments` in their `pyproject.toml`.
3. **Dropped-in** — packages in a configured `attachments_dir` (e.g.
   `data/attachments/`), imported dynamically. Good for quick personal hacks.

Each is `enabled`/`disabled` via config. The registry:
1. imports the package, gets the `Attachment`,
2. calls `on_load(ctx)`,
3. mounts `router()` under `/api/att/<name>`,
4. registers its UI into the manifest,
5. tracks background tasks for clean shutdown.

A failing attachment is isolated: it's marked `errored` in `/api/manifest` and
`/healthz` but does **not** crash the spine.

## 4. UI delivery — the important design

The frontend is generic, so attachments must *describe* their UI in a way the
shell can render. Two tiers, from safe-and-simple to powerful-and-careful:

### Tier 1 (default): declarative UI descriptor

A JSON schema of components the shell knows how to render. Think of it as a small,
fixed vocabulary — enough for 90% of personal tools (todo, forms, lists, tables,
buttons that call attachment endpoints).

```jsonc
// example: todo attachment UI descriptor
{
  "type": "view",
  "children": [
    { "type": "header", "text": "Todo" },
    { "type": "list",
      "source": { "get": "/api/att/todo/items" },   // shell fetches this
      "item": {
        "type": "row",
        "children": [
          { "type": "checkbox", "bind": "done",
            "action": { "post": "/api/att/todo/items/{id}/toggle" } },
          { "type": "text", "bind": "title" }
        ]
      }
    },
    { "type": "input", "name": "title", "placeholder": "New todo…" },
    { "type": "button", "text": "Add",
      "action": { "post": "/api/att/todo/items", "body": { "title": "$title" } } }
  ]
}
```

The shell has a renderer that maps each `type` → a Svelte component, binds data
from `source`/`get`, and wires `action`s to API calls. **Data binding and actions
always go through the attachment's own namespaced API**, so the shell stays dumb.

Component vocabulary (v1 starter set): `view, header, text, list, row, table,
input, textarea, select, checkbox, button, link, badge, divider, tabs, modal`.
We grow this deliberately — every new component is a new thing the shell must
support, so additions are reviewed, not casual.

### Tier 2 (escape hatch): shipped component bundle

When the declarative vocabulary isn't enough, an attachment can ship a compiled
JS bundle (a web component / custom element) served by the spine at
`/api/att/<name>/ui.js`. The shell loads it as a custom element inside a
sandboxed boundary and passes it an authenticated API client scoped to that
attachment.

- Pros: arbitrary UI.
- Cons: now the attachment ships code that runs in the client → trust + sandbox
  concerns. We use it sparingly, for attachments *we* author, and treat
  third-party bundles as untrusted (CSP, no ambient credentials, scoped fetch).

**Rule of thumb:** prefer Tier 1. Reach for Tier 2 only when a tool genuinely
needs custom interaction (a calendar grid, a mail reader pane).

### Flutter consideration

Tier 1 (declarative) maps cleanly to Flutter later — a Flutter renderer reads the
same descriptor and builds native widgets. Tier 2 (JS bundle) does **not** port to
native Flutter; such attachments would fall back to a WebView there. This is a
strong reason to keep most attachments in Tier 1. (For now: Svelte shell + a
Capacitor APK, where both tiers work since it's a WebView anyway.)

## 5. Caching & versioning

- The manifest carries `ui_version` per attachment (hash of its UI spec) and a
  global `version`.
- The shell caches descriptors and Tier-2 bundles keyed by version. On launch it
  does a cheap ETag check; unchanged → render from cache (works offline-ish).
- A changed `ui_version` → refetch just that attachment's UI.

## 6. Events (live updates)

Attachments push via `ctx.events.publish("todo.updated", payload)`. The core's
WebSocket hub fans out to connected clients subscribed to that attachment. The
shell's renderer re-pulls the affected `source` or applies the payload. This is
how "todo changes on my laptop show up on my phone" works without polling.

## 7. Capabilities & isolation (forward-looking)

Each attachment declares capabilities (`network`, `send_mail`, `read_files`,
`spawn_process`). For now in-process attachments are trusted (you write them).
The declaration exists so that later we can:
- show the user what an attachment can do,
- run a risky attachment (mail server) as a **separate process** the core proxies
  to — the contract above doesn't expose process boundaries, so the frontend and
  other attachments are unaffected.

## 8. A minimal attachment, end to end

```python
# raspy/attachments/ping/__init__.py
from raspy.core.contract import BaseAttachment, UISpec
from fastapi import APIRouter

class Ping(BaseAttachment):
    name, title, icon, version = "ping", "Ping", "activity", "0.1.0"

    def router(self) -> APIRouter:
        r = APIRouter()
        @r.get("/now")
        async def now(): return {"pong": True}
        return r

    def ui(self) -> UISpec:
        return UISpec.view([
            UISpec.header("Ping"),
            UISpec.button("Ping", action={"get": "/api/att/ping/now"}),
        ])

attachment = Ping()
```

Drop that package in, restart, and "Ping" appears in every client. No frontend
change. That's the whole point.

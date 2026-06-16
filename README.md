# Raspy

Raspy is a personal Raspberry Pi control plane: one FastAPI backend, a
server-driven Svelte shell, and a set of small "attachments" that add apps
without changing the frontend.

The backend is the spine. It owns auth, sessions, the attachment registry,
SQLite storage, WebSocket events, notifications, and the static frontend bundle.
Each attachment contributes an API router and a declarative UI descriptor. The
frontend downloads the manifest, renders whatever apps the current account can
see, and talks back to each app under `/api/att/<id>/`.

## What is here

- `backend/` - Python 3.13 FastAPI app, managed with `uv`.
- `frontend/` - SvelteKit static SPA, managed with `bun`.
- `scripts/` - frontend build and preview helpers.
- `systemd/` - service file for running the spine on a Pi.
- `plan/` - architecture notes and roadmap.

Built-in attachments currently include accounts, todo, notes, notifications,
files, system stats, mail, calendar, contacts, vault, and vibe-of-the-day. The exact list
is discovered at startup and filtered per account in `/api/manifest`.

## Current shape

Raspy is no longer just a sketch. The repo has:

- password login plus mini-PIN unlock, Argon2id storage, rotating sessions, CSRF
  protection, lockout/rate-limit behavior, and account-scoped app visibility;
- an optional browser-to-spine encrypted channel layered over HTTP requests;
- a WebSocket event bus for live app updates;
- foreground notification history plus optional Web Push via VAPID keys;
- per-attachment SQLite tables and data directories;
- a static Svelte shell served by FastAPI in production;
- a generic renderer for declarative attachment UIs, plus richer native Svelte
  views for apps that need them.

The project is still personal infrastructure, so assume the planning docs may
describe future work as well as completed work. The source is the authority.

## First run

Install tools:

```sh
# backend
curl -LsSf https://astral.sh/uv/install.sh | sh

# frontend
curl -fsSL https://bun.sh/install | bash
```

Install backend dependencies and create the first account:

```sh
cd backend
uv sync
uv run raspy-auth create-account
```

Start the spine:

```sh
uv run raspy
```

By default it binds to `127.0.0.1:49317`. Health is public at
`http://127.0.0.1:49317/api/healthz`. Protected APIs, including
`/api/manifest`, require login.

## Frontend development

Run the backend in one terminal. In another:

```sh
cd frontend
bun install
cp .env.example .env
```

Set `PUBLIC_API_BASE` in `frontend/.env` when the frontend runs on a different
origin than the spine:

```sh
PUBLIC_API_BASE=http://127.0.0.1:49317
```

Then start Vite:

```sh
bun run dev
```

Open the Vite URL, usually `http://localhost:5173`.

## Production build

The production frontend is static. Build it, then let the spine serve
`frontend/build/` from the same origin as the API:

```sh
scripts/build-frontend.sh
cd backend
uv run raspy
```

For local preview of the static bundle without the Python spine serving it:

```sh
scripts/build-and-serve.sh
```

## Configuration

Runtime state lives under `backend/data/` by default and is gitignored. Override
with environment variables or `data/config.toml`.

Common settings:

- `RASPY_HOST` and `RASPY_PORT` - bind address for the spine.
- `RASPY_DATA_DIR` - SQLite, secrets, and attachment data.
- `RASPY_STATIC_DIR` - built frontend directory to serve.
- `RASPY_ATTACHMENTS_DIR` - optional drop-in attachment packages.
- `RASPY_DISABLED_ATTACHMENTS` - disable discovered attachments by id.
- `RASPY_VAPID_PUBLIC_KEY`, `RASPY_VAPID_PRIVATE_KEY`, `RASPY_VAPID_SUBJECT` -
  enable background Web Push notifications.

Useful auth commands:

```sh
cd backend
uv run raspy-auth calibrate
uv run raspy-auth set-pin --username <name>
uv run raspy-auth reset-password --username <name>
uv run raspy-auth revoke-all --username <name>
uv run raspy-auth gen-channel-key
```

Generate VAPID keys for push notifications:

```sh
cd backend
uv run raspy-vapid
```

## Testing

Backend:

```sh
cd backend
uv run pytest -q
```

Frontend:

```sh
cd frontend
bun run check
bun run build
```

## Deployment notes

The provided systemd unit assumes:

- Linux user `raspberrypi`;
- repo cloned to `/home/raspberrypi/raspy`;
- backend working directory at `/home/raspberrypi/raspy/backend`;
- `uv` installed at `/home/raspberrypi/.local/bin/uv`.

Install on the Pi after adjusting paths if needed:

```sh
sudo cp systemd/raspy.service /etc/systemd/system/raspy.service
sudo systemctl daemon-reload
sudo systemctl enable --now raspy
```

The spine is designed to sit behind LAN access, Tailscale, Cloudflare Tunnel, or
another reverse layer. App auth stays inside Raspy either way.

## Adding an attachment

Create a package that exposes a `BaseAttachment` instance. Built-ins live under
`backend/raspy/attachments/`; external attachments can be loaded from
`RASPY_ATTACHMENTS_DIR` or via the `raspy.attachments` entry point.

```python
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

Restart the spine. The app is mounted at `/api/att/ping/...` and appears in the
manifest without rebuilding the frontend.

## Deeper docs

Start with [plan/README.md](plan/README.md), then read the backend and frontend
READMEs for implementation-specific notes.

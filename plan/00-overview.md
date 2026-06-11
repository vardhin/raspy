# Raspy — Architecture Overview

> Personal Raspberry Pi control plane. One async backend ("the spine"), a modular
> attachment system, and a thin frontend shell that renders UI shipped *by the
> backend*. Reachable over LAN, Cloudflare Tunnel, Tailscale, or (future) a
> port-forwarded static IP — all behind a single domain.

## 1. The one-paragraph version

You run a **FastAPI spine** on the Pi. It does async work on demand and exposes a
single HTTP/WebSocket API. Functionality is added as **attachments** (plugins):
a todo app, an email handler, a personal mail server, domain tooling, etc. The
clever part: **each attachment ships its own frontend UI** to the client. The
frontend (SvelteKit static build for laptop, Capacitor wrapper for an Android APK
now, native Flutter later) is a **generic shell** — it discovers attachments,
fetches their UI descriptors, renders them, and caches them. Adding a new
attachment never requires rebuilding or redeploying the frontend.

## 2. Goals & non-goals

**Goals**
- Single backend process, async, runs as a `systemd` service on the Pi.
- Modular: drop in an attachment, restart (or hot-reload), it appears in the UI.
- One frontend codebase → laptop web app + Android APK.
- **Server-driven UI**: attachments provide their own UI; frontend doesn't change.
- Multi-transport reachability: LAN IP, domain via Cloudflare Tunnel, Tailscale,
  future static-IP port-forward — the spine is transport-agnostic.
- Auth that is **brute-force resistant** and not offline-crackable (no capturable
  handshake à la WPA). Username + password is enough for a personal system, but
  hardened: strong KDF, rate limiting, lockout, signed session tokens.

**Non-goals (for now)**
- Multi-tenant / multiple users. This is single-operator (you). The design leaves
  room for a second account but won't over-build for it.
- Rust. Considered and dropped — unnecessary complexity for this scope.
- Native Flutter app in v1. Capacitor gives us an APK from the same Svelte build;
  Flutter is a later milestone.

## 3. System diagram (logical)

```
                     ┌──────────────────────────────────────────┐
                     │                Clients                    │
                     │  Laptop (SvelteKit static) │ Phone (APK)  │
                     │        the generic shell + cache          │
                     └───────────────┬──────────────────────────┘
                                     │  HTTPS / WSS
            ┌────────────────────────┼────────────────────────────┐
            │ Transports (any/all, same domain → same spine)       │
            │  LAN IP  │ Cloudflare Tunnel │ Tailscale │ port-fwd  │
            └────────────────────────┼────────────────────────────┘
                                     │
                     ┌───────────────▼──────────────────────────┐
                     │           THE SPINE (FastAPI)             │
                     │                                           │
                     │  Core:  auth · session · attachment       │
                     │         registry · UI manifest · events   │
                     │         (WebSocket) · static asset host    │
                     │                                           │
                     │  Attachment API (plugin contract)         │
                     │   ┌─────────┐ ┌─────────┐ ┌────────────┐  │
                     │   │  todo   │ │  email  │ │ mailserver │  │
                     │   │ +its UI │ │ +its UI │ │  +its UI   │  │
                     │   └─────────┘ └─────────┘ └────────────┘  │
                     └───────────────────────────────────────────┘
                                     │
                          Pi resources: disk, SQLite,
                          system services, network, etc.
```

## 4. The four pillars (each has its own doc)

| Pillar | Doc | One-liner |
|---|---|---|
| Spine core | [10-spine.md](10-spine.md) | FastAPI app structure, lifecycle, core services. |
| Attachments | [20-attachments.md](20-attachments.md) | The plugin contract: backend logic **+ shipped UI**. |
| Auth & security | [30-auth-security.md](30-auth-security.md) | Brute-force-resistant login, sessions, transport trust. |
| Frontend shell | [40-frontend.md](40-frontend.md) | Generic Svelte renderer, caching, Capacitor APK. |

Plus:
- [50-deployment.md](50-deployment.md) — running on the Pi, transports, updates.
- [60-roadmap.md](60-roadmap.md) — build order, milestones, what's v1 vs later.

## 5. Key architectural bets (read these even if you skip the rest)

1. **Server-driven UI is the spine of the spine.** It's what makes attachments
   self-contained. The risk is making a too-clever UI description format. We
   mitigate by starting with a *small, declarative* schema and an escape hatch
   (an attachment can ship a sandboxed component bundle) — see
   [20-attachments.md](20-attachments.md) §"UI delivery".

2. **The spine is transport-agnostic.** It binds to localhost/LAN and trusts a
   reverse layer (Cloudflare/Tailscale/nginx) for TLS termination. Auth happens
   *in the app*, not at the transport, so the same login works on every path in.

3. **One attachment contract, two kinds of payload.** Every attachment exposes
   (a) an API router and (b) a UI manifest. The frontend never hardcodes an
   attachment; it reads the manifest.

4. **Single process, in-process plugins to start.** Simpler to build and debug.
   The contract is designed so an attachment *could* later be split into its own
   process without the frontend noticing. We don't do that work until we need it
   (e.g. the mail server, which wants isolation).

## 6. Tech stack summary

| Layer | Choice | Why |
|---|---|---|
| Backend | FastAPI + Uvicorn, Python 3.13, `uv` | Async, you already started here. |
| Data | SQLite (per-attachment namespaced) | Zero-ops, fine for one user on a Pi. |
| Realtime | WebSocket (native FastAPI) | Push events / live attachment UI updates. |
| Auth | Argon2id + signed session tokens | Memory-hard KDF + rate limit = no offline crack. |
| Frontend | SvelteKit static adapter | Static bundle, no Node server needed on Pi. |
| Mobile (now) | Capacitor wrap of the Svelte build | Free APK from the same code. |
| Mobile (later) | Native Flutter | Better native integration; deferred. |
| Process mgmt | systemd | Native to the Pi, restart-on-boot. |

See [60-roadmap.md](60-roadmap.md) for the build order.

# Frontend — The Generic Shell

One Svelte codebase. It is **not** a collection of feature pages — it's a **renderer**
that fetches the attachment manifest and draws whatever the backend describes.
Adding an attachment never touches this codebase.

## 1. Build targets

| Target | How | Status |
|---|---|---|
| Laptop web app | SvelteKit + `@sveltejs/adapter-static` → static bundle, served by the spine | v1 |
| Android APK | Wrap the same static build with **Capacitor** | v1 (temp) |
| Native Android | **Flutter** renderer reading the same manifest schema | later |

Static adapter means **no Node runtime on the Pi** — the spine just serves files.
Capacitor wraps that same `build/` output into a WebView APK, so the phone gets the
identical app for near-zero extra work.

## 2. Anatomy of the shell

```
frontend/
├── src/
│   ├── lib/
│   │   ├── api.ts            # auth-aware fetch client (token/cookie, refresh)
│   │   ├── manifest.ts       # fetch + cache the /api/manifest
│   │   ├── ws.ts             # WebSocket client, event subscriptions
│   │   ├── cache.ts          # IndexedDB/localStorage cache of UI specs+bundles
│   │   └── renderer/
│   │       ├── Renderer.svelte      # walks a UISpec, picks components
│   │       ├── components/          # one Svelte comp per descriptor `type`
│   │       │   ├── View.svelte
│   │       │   ├── List.svelte
│   │       │   ├── Table.svelte
│   │       │   ├── Input.svelte
│   │       │   ├── Button.svelte
│   │       │   └── …
│   │       └── bundleHost.svelte    # Tier-2 escape hatch loader (custom elem)
│   ├── routes/
│   │   ├── +layout.svelte    # nav built from manifest (one entry per attachment)
│   │   ├── login/+page.svelte
│   │   └── a/[name]/+page.svelte    # renders attachment `name` via Renderer
│   └── app.html
├── capacitor.config.ts
└── package.json
```

## 3. Boot sequence

1. Determine the **base URL** of the spine. The web app served *by* the spine uses
   same-origin. The APK needs a configured server address (see §6, multi-transport).
2. Check auth (valid token/cookie?). If not → `login/`.
3. `GET /api/manifest` with an `If-None-Match` (ETag). 304 → use cached manifest.
4. Build the nav: one item per attachment (`title` + `icon`).
5. Open the WebSocket for live events.
6. Navigating to an attachment renders its `ui` descriptor through `Renderer`, or
   loads its Tier-2 bundle.

## 4. The Renderer (Tier 1)

`Renderer.svelte` takes a `UISpec` node and recursively renders. A registry maps
`node.type → Svelte component`. Each component:

- reads static props (`text`, `placeholder`, …),
- resolves data from `source`/`get` via the `api` client (scoped to the
  attachment's `/api/att/<name>/` prefix),
- wires `action`s (`get`/`post`/…) back through the same client,
- supports simple bindings (`bind`, `$var` interpolation from local form state).

Keep it small and declarative. The component set is the contract with attachment
authors — see vocabulary list in [20-attachments.md](20-attachments.md) §Tier 1.

## 5. The bundle host (Tier 2)

For attachments that ship a JS bundle: `bundleHost` loads
`/api/att/<name>/ui.js`, which registers a **custom element**, and mounts it inside
a boundary. It passes the element a **scoped, authenticated API client** (no raw
session cookie/token exposed — the client signs requests on the bundle's behalf and
only allows the attachment's own endpoints). CSP restricts what the bundle can do.

This tier won't port to native Flutter (would need a WebView fallback there), which
is why the shell nudges authors toward Tier 1.

## 6. Multi-transport from the client

The web app served by the spine is same-origin → trivial. The **APK / standalone
client** needs to know *where* the spine is, and you have several paths to the same
box:

- A **server picker / settings screen**: store one or more base URLs —
  e.g. `https://pi.yourdomain.com` (Cloudflare/port-forward),
  `http://raspy.tailnet-name.ts.net` (Tailscale),
  `http://192.168.1.x:PORT` (LAN).
- Optionally **auto-select**: try Tailscale/LAN first (fast, local), fall back to
  the public domain. Since auth is identical on every transport
  ([30-auth-security.md](30-auth-security.md) §5), switching transports doesn't
  re-authenticate beyond the normal session.
- The session token works regardless of which URL reached the spine.

## 7. Caching & offline-ish behavior

- Manifest + per-attachment UI specs cached (IndexedDB), keyed by `ui_version`.
- Tier-2 bundles cached by version too.
- On launch the shell renders from cache immediately, then revalidates via ETag —
  so the UI is instant and survives brief disconnects. Actual *data* still needs
  the server (it's a control plane for a live Pi, not an offline app).

## 8. Why Svelte first, Flutter later

- Svelte static build gives laptop + APK from **one** build with Capacitor — fastest
  path to a working product.
- The declarative descriptor is framework-neutral, so a Flutter renderer later reads
  the **same** `/api/manifest` and builds native widgets — no backend changes.
- We only pay the Flutter cost once the web/Capacitor version proves the model and we
  want real native polish.

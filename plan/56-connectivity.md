# Connectivity attachment — design note

Goal: one panel that answers "how do I reach Raspy from here?" and lets an admin
turn remote access on. It's a **networking dashboard** plus controls.

Admin-only (in `manifest._ADMIN_ONLY`): it shows addresses, controls public
exposure, and holds a stored secret. Its router refuses non-admins. It never runs
as root and never installs provider binaries — it detects them and links to docs.

## What it shows (GET /status)

A single dashboard object:

- **`local`** — every non-loopback interface IP (IPv4 + IPv6), each classified
  (`lan` / `tailscale` / `link-local`) and given a ready link
  `http://<host>:<port>` (IPv6 bracketed). Discovered with stdlib socket tricks,
  no `netifaces` dependency.
- **`public`** — the internet-facing IPv4/IPv6 via a keyless lookup
  (Cloudflare trace). Informational: only reachable if the port is actually
  forwarded/exposed.
- **`tailscale`** — installed?, backend state, connected?, the assigned IP(s) +
  MagicDNS name as access links, **the login account email** (`login_name` from
  `tailscale status --json`'s `User[Self.UserID].LoginName`), display name,
  tailnet, and whether Tailscale **SSH** is advertised. Tailscale is a
  machine-level VPN already running on the box — Raspy *discovers* the address,
  it doesn't assign it.
- **`cloudflare`** — installed?, configured? (token present), running?, and the
  public hostname/link when known.

The link port is the spine's configured `settings.port`.

## What it can do (admin POSTs)

- `cloudflare/token` — store the tunnel token (encrypted at rest, per-attachment
  Fernet key; never returned to the client).
- `cloudflare/up` / `cloudflare/down` — supervise `cloudflared tunnel run
  --token …` as a tracked child; `up` is idempotent (kills the old child first),
  and the spine's shutdown stops it so no tunnel is orphaned.
- `tailscale/up` — bring Tailscale up; if it needs an interactive login the
  daemon's login URL (`AuthURL` / scraped) is surfaced for the UI to show. No
  auth key is taken or stored — the normal flow is a browser login.
- `tailscale/down` — disconnect (keeps the node key).
- `tailscale/logout` — full logout (forgets the account/node key).
- `tailscale/ssh` — enable/disable Tailscale SSH (`tailscale set --ssh[=false]`).

## Edge cases (explicit)

- **Not installed**: status reports `installed: false` and the UI shows an install
  link; every action endpoint returns **503** with a clear message.
- **Installed but not configured / logged out**: Cloudflare shows `configured:
  false` (Connect disabled until a token is saved); Tailscale shows the login
  button and, after `up`, the login URL.
- **A failing probe never blanks the dashboard**: `local`, `public`, and
  `tailscale` are gathered independently and each falls back to an empty/neutral
  value on error.

## Security boundary

- The Cloudflare token is written only to the account data dir, encrypted, and
  never echoed back.
- Bringing a tunnel up / changing Tailscale is a mutating admin action behind the
  normal auth + CSRF gate.
- `tailscale up` may need root; if it fails we surface the real error rather than
  silently escalating.

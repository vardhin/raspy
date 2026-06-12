# Deployment & Operations

How Raspy runs on the actual Pi, how the four transports reach it, and how you
update it.

## 1. Process model

- The spine runs as a **`systemd` service** (`raspy.service`), `Restart=on-failure`,
  starts on boot. Runs under a dedicated unprivileged user (`raspy`), not root.
- Uvicorn, single worker (state — rate limits, WS hub, in-proc attachments — lives
  in one process; one user doesn't need multiple workers).
- `data/` (SQLite, secrets, attachment state) owned by the `raspy` user, `700`.
- Python managed by **`uv`**; a locked venv on the Pi. Deploy = pull + `uv sync` +
  restart.

```ini
# /etc/systemd/system/raspy.service  (sketch)
[Unit]
Description=Raspy spine
After=network-online.target

[Service]
User=raspy
WorkingDirectory=/opt/raspy
ExecStart=/opt/raspy/.venv/bin/uvicorn raspy.main:app --host 127.0.0.1 --port 8787
Restart=on-failure
RestartSec=2

[Install]
WantedBy=multi-user.target
```

Note `--host 127.0.0.1`: the spine binds **localhost only**. Every transport below
puts a layer in front; nothing reaches the spine without going through one of them.
(LAN access is the one case that needs a binding decision — see §2.)

## 2. The four transports (all → same domain → same spine)

You already have Cloudflare + a domain, and Tailscale. Future: static IP +
port-forward. All authenticate identically in-app
([30-auth-security.md](30-auth-security.md) §5).

| Transport | TLS | Exposure | Notes |
|---|---|---|---|
| **LAN** | self-signed/`mkcert` or via Tailscale | home network only | Bind a reverse proxy (Caddy) on the LAN interface, or just use Tailscale on-LAN. |
| **Cloudflare Tunnel** | Cloudflare edge cert | no open ports | `cloudflared` runs on the Pi, dials out, maps `pi.domain.com` → `127.0.0.1:8787`. Your current primary path. |
| **Tailscale** | WireGuard mesh | tailnet devices only | `raspy.<tailnet>.ts.net`; most secure remote path; device pre-authenticated. |
| **Static IP + port-forward** (future) | Caddy/nginx (Let's Encrypt) | open port 443 | Replaces the tunnel later; put Caddy in front for real certs + as the trusted proxy. |

**Recommended front layer:** run **Caddy** on the Pi as the single reverse proxy
for LAN + future port-forward (automatic certs, HTTP/2, sane defaults), and keep
`cloudflared`/Tailscale alongside. The spine only ever sees `127.0.0.1` traffic,
and only Caddy/cloudflared are trusted to set `X-Forwarded-For`
([30-auth-security.md](30-auth-security.md) §5).

```
Internet ──Cloudflare──► cloudflared ─┐
Tailnet ───WireGuard────► tailscaled ─┤
LAN/WAN ───443──────────► Caddy ──────┼──► 127.0.0.1:8787  (spine)
```

DNS: point `pi.yourdomain.com` at whichever front is active (Cloudflare now;
swap to the static IP's Caddy later) — clients don't care, the domain is stable.

## 3. First-run

1. Install, `uv sync`, enable the service.
2. Spine sees no account → **setup mode** (LAN/localhost only, or one-time token in
   the journal) to create your username + password
   ([30-auth-security.md](30-auth-security.md) §7).
3. Calibrate Argon2 params for the Pi (a one-time `raspy calibrate` helper).

## 4. Updates

- `git pull && uv sync && systemctl restart raspy` — or a small `deploy.sh`.
- Attachments can be enabled/disabled via config without code changes; a broken
  attachment is isolated, not fatal ([20-attachments.md](20-attachments.md) §3).
- Frontend: `scripts/build-frontend.sh` produces the static bundle at
  `frontend/build/`, which the spine serves **in place** at the root path (see
  `backend/raspy/core/static.py`). Deploy = `scripts/build-frontend.sh &&
  systemctl restart raspy`. Override the served dir with `RASPY_STATIC_DIR` if you
  relocate the bundle. APK: `npx cap sync &&` build in Android Studio / CI when you
  cut a phone release.

## 5. Backups

- `data/` is the whole state (SQLite + secrets). A periodic tar/rsync of `data/`
  (could itself be a Raspy attachment later) is the entire backup story.
- SQLite: use `.backup`/WAL-safe copy, not a raw `cp` of a live file.

## 6. Observability

- Logs to the journal (`journalctl -u raspy`).
- `/healthz` returns spine + per-attachment status; the manifest exposes `errored`
  attachments so the UI can show a badge.
- Audit log ([30-auth-security.md](30-auth-security.md) §6) for logins/token events.

## 7. The mail server caveat

A **personal mail server** (SMTP/IMAP, real inbound mail) is materially harder than
the rest: it needs **open ports 25/465/587/993**, **reverse DNS (PTR)**, **SPF/DKIM/
DMARC**, and a non-residential-IP reputation — Cloudflare Tunnel and most home ISPs
won't carry inbound SMTP well. Treat "host a personal mail **server**" as a distinct,
later milestone with its own doc; an **email *client*/handler** attachment (talk to
an existing mailbox over IMAP/SMTP) is easy and comes first. See
[60-roadmap.md](60-roadmap.md).

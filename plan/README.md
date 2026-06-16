# Raspy — Planning Docs

Architecture and roadmap for Raspy: a personal Raspberry Pi control plane. One async
FastAPI backend ("the spine"), modular **attachments** that ship their own UI, and a
generic frontend shell (SvelteKit static → laptop web + Capacitor APK now, Flutter
later). Reachable over LAN, Cloudflare Tunnel, Tailscale, or future static-IP
port-forward — all behind one domain, with brute-force-resistant username/password
auth.

## Read in this order

1. [00-overview.md](00-overview.md) — the whole system on one page; key bets; stack.
2. [10-spine.md](10-spine.md) — FastAPI core: structure, lifecycle, manifest, data.
3. [20-attachments.md](20-attachments.md) — the plugin contract + **server-driven UI**.
4. [30-auth-security.md](30-auth-security.md) — login, sessions, transport trust.
5. [40-frontend.md](40-frontend.md) — the generic renderer, caching, APK.
6. [45-theming.md](45-theming.md) — orthogonal color × concept themes, token-only components.
7. [50-deployment.md](50-deployment.md) — running on the Pi, the four transports, ops.
8. [55-distribution.md](55-distribution.md) — one-binary builds, the installer, self-update.
9. [56-connectivity.md](56-connectivity.md) — the connectivity attachment (tunnels), security boundary.
10. [60-roadmap.md](60-roadmap.md) — milestones and build order.

## The three ideas everything hangs on

- **Server-driven UI** — attachments describe their own UI; the frontend renders it
  and never changes per attachment. ([20-attachments.md](20-attachments.md))
- **Transport-agnostic spine** — auth happens in the app, so LAN / Cloudflare /
  Tailscale / port-forward all share one login. ([30-auth-security.md](30-auth-security.md) §5)
- **Online-only, memory-hard auth** — no capturable handshake to crack offline;
  every guess is a rate-limited Argon2id verify. ([30-auth-security.md](30-auth-security.md))

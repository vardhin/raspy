# Roadmap & Build Order

Build the **skeleton that proves the model** first (spine + auth + one trivial
attachment + shell rendering it end to end), then add real attachments. The riskiest
ideas — server-driven UI and brute-force-resistant auth — get validated early on
something tiny.

## Milestone 0 — Walking skeleton (prove the architecture)

Goal: log in from the laptop and see a "Ping" attachment's button, shipped by the
backend, rendered by the generic shell.

- [ ] Spine app factory + lifespan, config loading. ([10-spine.md](10-spine.md))
- [ ] SQLite init + scoped DB handles.
- [ ] Auth: Argon2id, first-run setup mode, login, signed session token, logout.
      ([30-auth-security.md](30-auth-security.md))
- [ ] Rate limiting + lockout on login.
- [ ] Attachment registry: discover built-ins, mount routers, build manifest.
      ([20-attachments.md](20-attachments.md))
- [ ] `GET /api/manifest` with ETag.
- [ ] One trivial attachment: **`ping`** (Tier-1 declarative UI).
- [ ] Frontend shell: login page, manifest fetch+cache, nav, Tier-1 `Renderer`
      with a *minimal* component set (`view, header, text, button, list, input`).
      ([40-frontend.md](40-frontend.md))
- [ ] Served by the spine as a static bundle; reachable over LAN.

**Exit criteria:** add a second trivial attachment as a package, restart, it appears
in the UI with **zero frontend changes**. That's the whole thesis, validated.

## Milestone 1 — Real first attachment: Todo

Goal: a genuinely useful attachment exercising data, lists, actions, and live events.

- [ ] `todo` attachment: items CRUD, namespaced storage.
- [ ] Renderer: `list` with item template, `checkbox`+`action`, add/delete.
- [ ] WebSocket events: edit on laptop → phone updates live.
      ([20-attachments.md](20-attachments.md) §6)
- [ ] Grow the component vocabulary as needed (deliberately).

## Milestone 2 — Mobile + remote access

Goal: use it from the phone, on and off the home network.

- [ ] **Capacitor** wrap of the Svelte build → installable APK.
      ([40-frontend.md](40-frontend.md) §1)
- [ ] Server picker (LAN / Tailscale / Cloudflare domain) in the app.
      ([40-frontend.md](40-frontend.md) §6)
- [ ] Cloudflare Tunnel + Tailscale verified end to end; Caddy front for LAN.
      ([50-deployment.md](50-deployment.md) §2)
- [ ] `systemd` service, first-run on the actual Pi, Argon2 calibration.
- [ ] **Optional TOTP** second factor for remote paths.
      ([30-auth-security.md](30-auth-security.md) §3)

## Milestone 3 — Email *handler* attachment (client, not server)

Goal: read/triage an existing mailbox. Easy, high value, tests Tier-2 UI.

- [ ] `email` attachment: IMAP/SMTP client to an existing account.
- [ ] Encrypted credential storage. ([30-auth-security.md](30-auth-security.md) §6)
- [ ] Likely a **Tier-2** bundle for the reading pane (justified custom UI).
      ([20-attachments.md](20-attachments.md) §Tier 2)

## Milestone 4 — Hardening & ops polish

- [ ] Audit log surfaced in a small `system` attachment.
- [ ] Backups of `data/` (maybe itself an attachment).
      ([50-deployment.md](50-deployment.md) §5)
- [ ] Capability declarations enforced/displayed.
      ([20-attachments.md](20-attachments.md) §7)
- [ ] Health/status UI for `errored` attachments.

## Later / bigger rocks (own docs when we get there)

- [ ] **Personal mail *server*** (inbound SMTP/IMAP). Real infra: ports 25/465/587/993,
      PTR, SPF/DKIM/DMARC, IP reputation — won't work over Cloudflare Tunnel or most
      home ISPs. Distinct project. ([50-deployment.md](50-deployment.md) §7)
- [ ] **Personal domain tooling** attachment (DNS records via Cloudflare API, etc.).
- [ ] **Out-of-process attachments** for isolation/untrusted code (the contract
      already hides the boundary). ([10-spine.md](10-spine.md) §7)
- [ ] **Native Flutter** renderer reading the same manifest.
      ([40-frontend.md](40-frontend.md) §8)
- [ ] Static IP + port-forward + Caddy replacing the Cloudflare Tunnel.
      ([50-deployment.md](50-deployment.md) §2)

## Sequencing logic (why this order)

1. **M0 de-risks the two novel ideas** (server-driven UI, online-only brute-force
   resistance) on something trivial — cheap to throw away if an assumption is wrong.
2. **M1** turns it into something you'd actually use daily, proving data + realtime.
3. **M2** makes it portable and remote — the original point of the project.
4. **M3+** adds the heavyweight attachments once the platform is solid.
5. The **mail server** and **native Flutter** are deliberately last: highest effort,
   and the architecture is built so they don't force rework of anything earlier.

# Auth & Security

Single operator, personal system. Requirement: **username + password is enough,
but it must be strong and brute-force resistant** — specifically *not* like a wifi
password where an attacker captures a handshake and cracks it offline without
limits. We achieve that by keeping all verification **online and server-side**,
behind a memory-hard hash, with rate limiting and lockout.

## 1. Threat model (honest, scoped)

**In scope:**
- The spine may be reachable from the public internet (Cloudflare Tunnel / future
  port-forward). So assume attackers *can* reach the login endpoint.
- Online password guessing.
- Session token theft / replay.
- Credential reuse from a leak elsewhere.

**Out of scope (accepted):**
- A nation-state targeting you specifically.
- Physical access to the Pi (if they have the box + disk, it's over; optionally
  mitigate with disk encryption later).

**Why no offline-crack risk:** unlike WPA, there is no exported "handshake" to
crack. The only way to test a password is to send it to the server, which (a)
hashes with Argon2id and (b) rate-limits + locks out. There's nothing capturable
that lets an attacker test guesses locally at unlimited speed.

## 2. Password storage

- **Argon2id** via `argon2-cffi`. Memory-hard → GPU/ASIC brute force is expensive
  even *if* the hash ever leaked.
- Tuned params (calibrate on the actual Pi; Argon2 is RAM-heavy and the Pi is
  modest): start around `time_cost=3, memory_cost=64MiB, parallelism=2`, then
  measure — target ~250–500ms per verify on the Pi.
- Per-password random salt (Argon2 handles this).
- A strong password is still required at setup (length/entropy check, reject
  known-breached via a local check or a k-anonymity HIBP range query — optional).

## 3. Brute-force resistance (the core requirement)

Layered, all server-side:

1. **Memory-hard hash** — each guess costs real CPU+RAM on the server. An attacker
   can't parallelize cheaply.
2. **Per-account + per-IP rate limiting** — e.g. token-bucket: N attempts/minute,
   then throttle. Backed by an in-memory store (or SQLite) so it survives across
   workers (we run a single worker anyway).
3. **Exponential backoff / lockout** — after K consecutive failures, enforce a
   growing delay (and/or temporary lock) on that account. Successful login resets.
4. **Constant-time-ish responses** — don't leak "user exists" vs "wrong password";
   same message, similar timing.
5. **Optional second factor for remote access** — a TOTP (authenticator app) as a
   later milestone. For a personal box this is the cheapest large security win and
   makes online guessing essentially hopeless. Marked optional in v1.

Tuning lives in config so you can tighten it without code changes.

## 4. Sessions

- On successful login, issue a **signed session token** (JWT or a signed opaque
  token via `itsdangerous`). Contains: subject, issued-at, expiry, a token id.
- Stored client-side. On web: **`HttpOnly`, `Secure`, `SameSite` cookie**
  (immune to JS/XSS theft). On the Capacitor APK / native app: secure storage
  (Keychain/Keystore) + sent as a bearer header.
- **Short access token + refresh** so a stolen token has a small window. Refresh
  rotates the token id; a replayed old refresh → revoke the family.
- **Server-side revocation list** (token ids) so "log out everywhere" works — cheap
  with one user.
- Signing secret stored in `data/` with tight file perms, generated on first run.

## 5. Transport trust — same auth on every path in

The spine **always authenticates in the application layer**, regardless of how the
request arrived. This is what lets LAN, Cloudflare, Tailscale, and port-forward
all share one login.

- **TLS termination** happens at the edge (Cloudflare, or nginx/Caddy in front for
  port-forward, or Tailscale's encrypted mesh). The spine itself can speak plain
  HTTP bound to localhost behind that layer — but **never** bind it to a public
  interface without a TLS terminator in front.
- **`Secure` cookies** require HTTPS end-to-end as the client sees it; all our
  transports provide that (Cloudflare/Caddy give real certs; Tailscale is
  encrypted; LAN can use a self-signed/`mkcert` cert or Tailscale).
- **Trusted-transport hint (optional convenience):** Tailscale already
  authenticates the device cryptographically. We *may* let config mark the
  Tailscale interface as "pre-trusted" to relax 2FA there — but password login is
  always still required. Default: treat every transport as untrusted; opt in
  deliberately.
- **Proxy headers:** only honor `X-Forwarded-For`/`Forwarded` from known local
  proxies (Cloudflared/Caddy on the box), so rate-limit-by-IP can't be spoofed.

## 6. Other hardening

- **CORS**: lock to the known frontend origins (the served shell + the APK's
  origin); not `*`.
- **CSP**: strict; matters especially for Tier-2 attachment bundles
  ([20-attachments.md](20-attachments.md) §Tier 2) — no inline eval, scoped fetch,
  attachment bundles can't read the session cookie (they get a scoped API client).
- **CSRF**: with cookie auth, use `SameSite=Strict`/`Lax` + a CSRF token on
  state-changing requests, *or* prefer bearer-header auth for the API and reserve
  cookies for the web shell.
- **Secrets at rest**: signing keys, attachment credentials (email passwords!)
  encrypted with a key derived from a master secret in `data/` with `600` perms.
  The mail attachment storing IMAP passwords is the main consumer here.
- **Audit log**: append-only log of logins (success/fail), token issues,
  attachment loads. One user → easy to eyeball anomalies.
- **Updates**: keep deps current (`uv` lockfile); the mail server attachment is the
  highest-risk surface and should be patchable independently.

## 7. First-run / account setup

- On first boot with no account, the spine enters a **setup mode**: reachable only
  from LAN/localhost (or prints a one-time setup token to the console/systemd log)
  to create the initial username + password. Prevents a race where the box is
  exposed before an account exists.
- Password strength enforced at creation.

## 8. Summary: why this meets your bar

| Your concern | How it's addressed |
|---|---|
| "Not wifi-style offline bruteforce" | No capturable handshake; every guess is an online Argon2id verify. |
| "Rate limited / strong" | Per-account + per-IP limits, exponential lockout, memory-hard KDF. |
| "Username + password is enough" | Yes — with optional TOTP later for remote paths. |
| "Personal, simple" | Single account, signed sessions, no external identity provider. |

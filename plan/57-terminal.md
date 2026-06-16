# Terminal attachment — design note

Goal: a real interactive shell on the box, in the browser. Detects the available
shells, lets you pick one, and streams a fully-interactive PTY (vim, htop, `sudo`
— all work) over the **encrypted channel**. tmux-like: a session survives a tab
close and can be reattached.

This is the most dangerous attachment in the system — it's a remote shell — so the
security boundary is the design.

## Security boundary (the whole point)

- **Admin-only.** In `manifest._ADMIN_ONLY`; children never see it and the HTTP
  routes 403 for non-admins via the core auth gate.
- **Requires the encrypted channel.** The PTY WebSocket refuses to open without a
  valid `?channel=<sid>` (core/channel). Every frame is sealed **both** directions
  — this is the first client→server sealed path (the core ws hub only sealed
  outbound). So keystrokes, including any `sudo` password you type, never cross the
  tunnel in plaintext.
- **Self-authenticating handshake.** The HTTP auth-gate middleware does not run for
  WebSockets, so the route authenticates itself exactly like `core/ws.py`: access
  token (cookie or `?access_token=`) → `verify_access` → reject non-admin and
  frozen children (close 1008).
- **No arbitrary argv.** You can only spawn a shell the server actually *detected*
  (`_validate_shell` checks the realpath against the detected set); an admin token
  can't be turned into "run this binary as argv[0]". An unknown choice falls back
  to the default shell.
- **Bounded.** At most `_MAX_SESSIONS` concurrent PTYs; an idle, detached session
  is reaped after `_IDLE_REAP_S`; all PTYs are killed on shutdown (process-group
  SIGTERM) so nothing is orphaned.

`sudo` needs no special handling here — you type it in the shell like any terminal,
and the PTY relays the password prompt. (Contrast the connectivity attachment,
which has no PTY and so uses an explicit sudo-password prompt; see
[56-connectivity.md](56-connectivity.md).)

## What it does

- `GET /shells` — `{supported, shells:[{id,name,path}]}`. Shells come from
  `/etc/shells` (filtered to real interactive shells — no `git-shell`/nologin) plus
  a PATH probe; the default ($SHELL, else bash/sh) is first.
- `GET /sessions` — live sessions for the reattach list.
- `DELETE /sessions/{id}` — kill a session.
- `WS /pty` — the stream. Client→server JSON messages: `open` (shell,cols,rows),
  `attach` (sid), `input` (utf8), `resize` (cols,rows). Server→client: `ready`
  (sid), `output`, `exit` (code), `error`. Each is wrapped as
  `{"type":"sealed","payload":...}` and opened/sealed with the channel session.

## Sessions (tmux-like)

A PTY is owned by the registry, not the socket. On disconnect we **detach** (cancel
the reader, keep the process); reconnecting with `attach` replays the recent
scrollback (a ring buffer capped at `_SCROLLBACK_BYTES`) then resumes the live
stream — replay is ordered *before* live output so there's no interleave. One viewer
at a time per session; a new `attach` steals the old viewer (closes it 1001).

## Frontend

A Tier-2-style dedicated Svelte component (`Terminal.svelte`, registered in the
renderer's `Node.svelte` like Connectivity) using **xterm.js** + the fit addon for
real VT100 emulation. Topbar = shell picker; a sealed WebSocket bound to the
channel; `ResizeObserver` re-fits and sends `resize`. A "Running sessions" list
offers attach/kill. Colours are pulled from the active theme tokens so it blends
with whatever color × concept is active ([45-theming.md](45-theming.md)).

## Platform

POSIX (Linux/the Pi) fully. On Windows the shells probe still works but opening a
PTY reports `unsupported` rather than half-implementing ConPTY — mirroring how
connectivity refuses cleanly when a provider binary is missing.

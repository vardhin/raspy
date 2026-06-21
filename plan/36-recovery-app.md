# 36 — Recovery: in-app export + login-screen restore

Two separate surfaces, deliberately split:

* **Recovery app** (in-app, authed) — a single button: "Download recovery
  bundle." Exports an encrypted zip of *all this account's data*. No restore UI
  here.
* **Restore** (on the **password login screen**, NOT an in-app feature) — "Restore
  from backup": pick a previously downloaded `.raspybundle`, enter the password,
  and it auto-decrypts, unzips, recreates the account, and additively links every
  store. Used on a fresh install or after sign-out.

The restorer is by definition someone who *already had an account and already
downloaded their bundle*, so the bundle is the source of truth — it **recreates
the account** (no CLI, no "create matching creds first"). The bundle is encrypted
under the **DEK** (plan 35), which the entered password unwraps via the account
row carried inside the bundle.

Depends on **plan 35** (the DEK + wraps): the bundle key is the DEK, and
`meta.json` carries the wraps so the password alone can re-derive it on a blank
machine.

## What "all their data" is

Per-account data lives in **two** backends, both keyed by `account_slug`
(`scope.py`); the admin uses the legacy unsuffixed scope:

| Backend | Admin (legacy) | Child account |
| --- | --- | --- |
| Files | `data_dir/att/<id>/…` | `data_dir/accounts/u<hex8>/att/<id>/…` |
| SQLite tables | `att_<id>_<table>` | `att_<id>_u<hex8>_<table>` |

So a user's complete footprint = their file subtree **plus** every SQLite table
whose name carries their slug (or, for the admin, every `att_*` table *not*
carrying any account slug). The bundle captures both.

Account-level secrets that are NOT in the bundle (system-level, not per-app
user data): `auth_secret`, `channel_key`. The account row itself (salts, wraps,
pw/pin hashes) IS included in `meta.json` so a relink onto a *fresh* install can
recreate the login. On a relink into an *existing* install the row is matched by
username and its wraps/salts are preserved (see Relink).

## Bundle format

The bundle is an outer container with a **plaintext header** (so the DEK can be
recovered from the password before anything is decrypted) and a **DEK-encrypted
body**:

```text
recovery-<username>-<YYYYMMDD>.raspybundle
  ├─ HEADER (plaintext JSON) ──────────────────
  │    meta.json   account row: username, role, allowed_apps, auth_salt,
  │                master_salt, recovery_salt, wrap_pw*, wrap_mn*, pw_hash,
  │                pin_hash, dek_migrated, body_nonce.
  │                None of this is secret (auth threat model): the wraps are
  │                opaque ciphertext, the salts are public-by-design. It MUST be
  │                plaintext so password→KEK_pw→unwrap(wrap_pw)→DEK works on a
  │                blank machine with no local account yet.
  └─ BODY = secretbox(zip, body_nonce, DEK) ───
       <plain zip inside>:
         manifest.json     schema version, username, slug, created, app list,
                           counts, sha256 of each member
         files/<id>/…      verbatim copy of the account's file subtree
         sqlite/<table>.ndjson   one file per per-account table; each line a row
                                 as JSON (column->value; bytes b64-tagged)
```

Why this split: `meta.json` carries the **wraps**, which are what let the password
(or mnemonic) re-derive the DEK. If it were inside the encrypted body you'd need
the DEK to read the wraps that produce the DEK — circular. So `meta.json` is the
plaintext header (harmlessly: it's all non-secret), and *everything that is actual
data* — including non-E2E app rows (notes, todo, calendar events…) — sits in the
DEK-encrypted body, protected at rest. This is the reason for encrypting the body
at all rather than shipping a plain zip.

## Why additive merge-into-live (not "position dir as the db", not destructive)

The literal "make the directory the db" can't work: `raspy.sqlite3` is one shared
file across all accounts (`db.py`). So relink **merges into the live store**, and
the merge is **purely additive** — it only ever *adds*, never deletes:

* **SQLite rows** (notes, todo, calendar events, chat, contacts): `INSERT OR
  IGNORE` by primary key. On an empty account every row inserts; pre-existing rows
  are left untouched. No `DELETE`, ever.
* **File blobs** (passwords `store.bin`, identity wrap, calendar/dropbox media):
  these are *single opaque ciphertext blobs per account* — you can't union two
  encrypted blobs (the merge would have to happen inside the plaintext, which only
  the client can see). So a blob is written **only into an empty slot**
  (`if not path.exists()`). An occupied slot is **skipped and reported**, never
  clobbered.

Intended use is relink onto an **empty install / fresh device**, where every slot
is free and every row is new — so additive restores everything. The empty-slot /
INSERT-OR-IGNORE guards exist purely so a misfired relink onto a non-empty account
can never destroy data; it degrades to "added what was missing, skipped the rest."

Because the merge is insert-or-ignore + write-if-absent, it is **idempotent**: a
re-run is a no-op. No destructive `DELETE`, no rollback snapshot, no whole-account
transaction needed. Every other account is untouched and the server keeps running.

## Export flow (WebSocket stream)

1. Client (vault unlocked) opens `ws /api/att/recovery/export` (authed; the WS
   endpoint sets the `current_account` scope, same as the HTTP gate).
2. Server, under that account's scope, builds the zip **to a temp file on disk**
   (not in memory — could be large): copy the file subtree, dump each scoped
   table to ndjson, write manifest/meta.
3. Server encrypts the temp zip under the DEK. The DEK isn't on the server — so
   the *client* must supply it. Two sub-options; we use **client-side seal**:
   server streams the *plain* zip in chunks over the (already TLS/Layer-1
   encrypted) socket; the **browser** secretbox-seals it under the in-memory DEK
   and triggers the `.raspybundle` download. Keeps the server zero-knowledge — it
   never holds the DEK, consistent with the whole design.
4. Progress frames (`{type:"progress", done, total}`) drive a UI bar; final
   `{type:"done"}` then close. Backpressure: chunk size ~256 KiB, await drain.

(Streaming over WS rather than a plain HTTP download because the build can be slow
and we want live progress + the Layer-1 channel; a one-shot GET is the fallback.)

## Restore flow (from the login screen — self-bootstrapping)

Entry point: a **"Restore from backup"** link on the password login screen
(`PasswordLogin.svelte`, the `'password'` auth state). This is *not* an in-app
feature — the whole point is to run before there is a usable session. The
restorer already has their `.raspybundle` from a prior export, so the bundle is
self-describing and recreates the account.

1. User picks the `.raspybundle` file (file picker; one file, not a folder) and
   enters their **password**.
2. **All client-side, before any account exists locally:** the browser reads the
   plaintext header of the bundle — `meta.json` is the *only* part stored
   unencrypted (it carries `master_salt`, `recovery_salt`, the wraps, and the
   account row; none of it is secret, per the auth threat model). From
   `master_salt` + password derive `KEK_pw`; unwrap `meta.wrap_pw` → **DEK**. A
   wrong password fails the secretbox MAC here → "wrong password," nothing
   written. (A "use recovery phrase instead" path unwraps `wrap_mn` → same DEK.)
3. DEK decrypts the bundle body → unzip in memory/OPFS → validate `manifest.json`
   (schema version + sha256 of each member).
4. Bootstrap the account: `POST /api/auth/restore-account` with the `meta.json`
   account row (username, role, allowed_apps, salts, wraps, pw_hash, pin_hash).
   Server creates the account row **only if no account with that username exists**
   (idempotent; never overwrites an existing account). This re-establishes login
   *and* the wraps, so the mnemonic keeps working afterwards.
5. Upload the unzipped data to `POST /api/att/recovery/relink` (authed by the
   session minted in step 4, scoped to the restored account). Server performs the
   **additive merge**:
   * `files/<id>/…` → write into `account_data_dir` **only where the target path
     does not already exist**; record skipped (occupied) paths;
   * each `sqlite/<table>.ndjson` → bulk `INSERT OR IGNORE` into the scoped table
     (creating it from the row shape if absent).
6. Return `{added: {<app>: rows/files}, skipped: {<app>: paths}}`; client logs in
   and lands fully restored.

No rollback machinery: account creation is create-if-absent and the merge is
insert-or-ignore + write-if-absent, so the whole restore is **idempotent and
non-destructive** — a crash mid-restore just means re-running finishes the rest.

System secrets (`auth_secret`, `channel_key`) regenerate on first run of the new
box; they are per-machine, not per-account, so they are deliberately *not* in the
bundle — a fresh login on the new machine is expected.

## Isolation & safety

* Per-account export: the recovery app only ever sees its own scope (files +
  tables), so a child can export only their own data. Enforced by the existing
  scope ContextVar — no special-casing.
* The restored data scopes to whatever account the bundle's `meta.json` names; the
  password must unwrap that account's `wrap_pw`, so you can't restore a bundle you
  don't have the password (or mnemonic) for.
* `restore-account` is **create-if-absent** — it never overwrites an existing
  local account, so a restore can't hijack a populated install.
* Size guard + sha256 manifest verification before the merge.
* The merge is **non-destructive** (additive only — never deletes a row or
  overwrites a blob); occupied-slot skips are surfaced so the user knows nothing
  was replaced. No rollback snapshot needed.

## Schema / API surface

* `ws   /api/att/recovery/export`    in-app, authed; stream plain zip chunks, the
  client seals under the DEK and triggers the `.raspybundle` download.
* `GET  /api/att/recovery/summary`   in-app; what would be exported (app list,
  counts, approx size) for the UI before the user commits.
* `POST /api/auth/restore-account`   **public** (pre-auth, login-screen path);
  body = the bundle's `meta.json` account row. Create-if-absent; mints a session
  on success so the follow-up relink is authed. Rate-limited via the existing
  attempts/lockout path.
* `POST /api/att/recovery/relink`    authed (by the session from restore-account);
  multipart upload of the unzipped body → additive merge into the scoped store.
* No new core tables; uses existing scoped storage. Audit via the auth audit table
  (`recovery_export` / `recovery_restore` / `recovery_relink`).

## Client

* `attachments/recovery/__init__.py` — the export attachment (export ws, summary,
  and the single "Download recovery bundle" UI). No restore UI here.
* `crypto/bundle.ts` — seal a `.raspybundle` under the DEK (export); read the
  plaintext header + unwrap DEK from password/mnemonic + decrypt + unzip + verify
  manifest sha256s (restore).
* `renderer/Recovery.svelte` — just the export button + progress bar.
* `components/PasswordLogin.svelte` — add the **"Restore from backup"** entry:
  file picker → password → derive DEK from header → decrypt → `restore-account` →
  `relink` → logged in. Wired through `auth.svelte.ts` (a `restoreFromBundle()`
  method alongside `login()`), reusing the plan-35 KEK/DEK helpers.

## Dependencies / ordering

1. **Plan 35 (DEK + wraps)** must land first — the bundle key is the DEK and the
   plaintext header carries the wraps.
2. Then **export** (read-only, in-app).
3. Then **restore** (login-screen): `restore-account` + additive `relink`.

## Out of scope

* Per-account SQLite files (rejected in favour of merge-into-live).
* Backing up system secrets (`auth_secret`, `channel_key`) — regenerated per box.
* Automatic/scheduled backups — this is on-demand, user-initiated.

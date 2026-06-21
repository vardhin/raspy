# 35 — Vault recovery via mnemonic (break-glass root)

## Problem

The vault root key is `master_key = Argon2id(password, master_salt)`, derived in
the browser and used *directly* as the secretbox key for every encrypted store:
passwords (`crypto/vault.ts`, `crypto/passwords.ts`), the X25519 identity secret
key wrap (`crypto/identity.ts`), and calendar media (`crypto/calendarMedia.ts`).

Two recovery scenarios:

* **PC dies, DB backup intact, password remembered** — *already works.* Nothing
  vault-secret lives on the PC. `master_salt` is in the DB; the identity secret
  key is stored wrapped-under-master_key on the Pi. Restore DB → enter password →
  everything re-derives. The IndexedDB PIN-wrap is pure local convenience.

* **Password forgotten, DB intact** — *unrecoverable today.* `reset-password`
  only rewrites `pw_hash`; it cannot reproduce the old `master_key`, so the vault,
  identity key, and all media are cryptographically lost (see the comment in
  `identity.ts ensureIdentity`). The password is the *sole* entropy source for the
  vault, with no second root.

This plan adds a **mnemonic** as a second, independent root that unwraps the same
vault — break-glass recovery for the forgotten-password case.

## Design: envelope (DEK + multiple KEK wraps)

Move the vault root from "password-derived key" to "a stable Data Encryption Key
(DEK) that is wrapped under N key-encryption-keys (KEKs)". Unlocking via *any* KEK
recovers the same DEK.

```text
DEK                       — the real vault root (what auth.masterKey resolves to)
KEK_pw  = Argon2id(password, master_salt)        (the existing derivation)
KEK_mn  = Argon2id(mnemonic, recovery_salt)      (new)

wrap_pw = secretbox(DEK, nonce_pw, KEK_pw)        stored in DB
wrap_mn = secretbox(DEK, nonce_mn, KEK_mn)        stored in DB
```

Password change ⇒ re-wrap `wrap_pw` only. DEK (and the whole vault + identity)
survives untouched. Mnemonic recovery ⇒ unwrap `wrap_mn` → DEK → set a new
password = re-wrap `wrap_pw` under the new `KEK_pw`.

### THE compatibility pin (non-negotiable: no data loss)

For an **existing** account the DEK is **defined to equal the current
`master_key`** (`= Argon2id(password, master_salt)`). Then:

* every existing ciphertext stays valid — nothing is re-encrypted, ever;
* `wrap_pw` becomes `secretbox(DEK, nonce, KEK_pw)` where `DEK == KEK_pw`, i.e. it
  encrypts the key under itself — trivially producible the moment the user unlocks
  with their password (master_key in memory);
* the mnemonic is minted and `wrap_mn` written in the same step.

So migration needs the vault *unlocked once* (master_key in memory) — which is
exactly the "on next in-browser unlock" trigger chosen. No SSH, no re-encryption,
no rewrap of identity/vault/media. New accounts get a fresh random DEK from the
start.

### The one chokepoint

Every consumer reads `auth.masterKey` (one in-memory `Uint8Array`) and uses it as
a secretbox key. **No consumer changes.** We only change what `auth.masterKey`
*resolves to*: after deriving `KEK_pw` (today's `deriveMasterKey`), run a
`resolveDEK(KEK_pw)` step that:

* migrated account → unwrap `wrap_pw` → DEK, assign DEK to `#masterKey`;
* not-yet-migrated account → DEK *is* `KEK_pw`; assign it, then lazily mint the
  mnemonic + write both wraps (DEK==KEK_pw makes `wrap_pw` self-wrap), flip a
  `migrated` flag, and show the phrase once.

## Backward compatibility / migration guarantees

* **No ciphertext is ever re-encrypted.** DEK==old master_key for existing data.
* **Pre-migration accounts keep working** unchanged until the user next unlocks
  with a password (PIN unlock alone can't migrate — it doesn't have KEK_pw; it
  unwraps the local PIN blob which holds the DEK either way, so PIN keeps working
  before *and* after).
* **Identity remint is avoided.** `ensureIdentity` already unwraps the stored
  secret key under `auth.masterKey`; since that still resolves to the same bytes,
  it opens — no new keypair, nothing sealed-to-old-key is lost.
* **Account row is additive** — new nullable columns only; absent = unmigrated.
* **Mnemonic shown exactly once**; never stored client-side, never sent to the
  server in any reversible form.

## Schema (additive, nullable — `core_auth_account`)

```text
recovery_salt   TEXT      -- salt for KEK_mn
wrap_pw         TEXT      -- secretbox(DEK, KEK_pw), b64  (nonce||cipher or split)
wrap_pw_nonce   TEXT
wrap_mn         TEXT      -- secretbox(DEK, KEK_mn), b64
wrap_mn_nonce   TEXT
dek_migrated    INTEGER NOT NULL DEFAULT 0
```

NULL wrap columns + `dek_migrated=0` ⇒ legacy account: `auth.masterKey` = KEK_pw,
migrate on next password unlock. Added via the existing `_migrate_account_columns`
introspection pattern. The wraps are opaque blobs to the server — it never sees
DEK, KEK_pw, KEK_mn, the password, or the mnemonic.

## HTTP surface (all carry only opaque blobs)

* `GET  /api/auth/recovery/<user>` → `{recovery_salt, wrap_mn, wrap_mn_nonce}`
  (public, like `kdf`; decoy for nonexistent users to avoid existence leak).
* `PUT  /api/auth/recovery` (authed) → store `{recovery_salt, wrap_pw, wrap_mn,
  …, dek_migrated:1}`. Written by the browser after it mints DEK + mnemonic.
* `POST /api/auth/recover` (public, rate-limited via the existing
  attempts/lockout path) → body `{username, new_auth_key, new_pin}`; server resets
  pw_hash/pin_hash like `complete_setup` but WITHOUT touching wraps. The browser,
  having unwrapped DEK locally from the mnemonic, then re-PUTs a fresh `wrap_pw`
  under the new KEK_pw. (Server can't do the rewrap — it never has the DEK.)

## Client flow

* `crypto/recovery.ts` — BIP39 mnemonic gen/validate (use a vetted wordlist;
  libsodium has no BIP39, add `@scure/bip39` or equivalent), `deriveRecoveryKey`,
  and DEK wrap/unwrap helpers (mirrors keystore.ts shape).
* `auth.svelte.ts` — add `resolveDEK(kekPw)` called right after every
  `deriveMasterKey(...)` (login, unlockWithPassword); migrate-if-legacy there.
  `#masterKey` now holds the DEK. PIN wrap/unwrap already stores whatever
  `#masterKey` is — so it transparently stores the DEK post-migration.
* Recovery UI — a "Forgot password?" entry on the password screen: enter mnemonic
  + new password/PIN -> unwrap DEK locally -> `POST /recover` -> re-PUT wrap_pw ->
  log in. A one-time "write down these words" modal at migration and child setup.

## Edge cases

* **Mnemonic minting must be atomic-ish:** write `wrap_mn` + `recovery_salt`
  before showing the words; if the user dismisses the modal, the phrase still
  works (it's already stored as a wrap). Offer "show again until confirmed".
* **Child accounts** (`must_reset`) mint their DEK + mnemonic at `complete_setup`
  (first real password), same path as a new account.
* **PIN-only sessions** never migrate (no KEK_pw); they keep working because the
  PIN blob wraps the DEK directly. First password unlock migrates.
* **A wrong mnemonic** fails the secretbox MAC → reject, count against the
  rate-limit, never produce a garbage key.

## Out of scope / non-goals

* Re-encrypting existing data (explicitly avoided — that's the whole point).
* Server-side knowledge of any root key (it stays zero-knowledge of the vault).
* Replacing the PIN convenience path (unchanged).

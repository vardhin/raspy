// Auth store — drives the shell gate and holds the in-memory vault master key.
//
// States:
//   'loading'  — initial; asking the server what we need
//   'password' — no usable session; show full password login
//   'pin'      — access token lapsed but refresh still valid; show mini-PIN
//   'reset'    — frozen child signed in with temp credentials; set real password/PIN
//   'active'   — authenticated; render the app
//
// The master_key (for the vault) lives only in memory here. On password login we
// also PIN-wrap it into IndexedDB (keystore.ts) so a later PIN unlock can recover
// it without the password. Logout clears both.

import { browser } from '$app/environment';
import { apiUrl } from '$lib/api';
import { deriveAuthKey, deriveMasterKey } from '$lib/crypto/kdf';
import {
	wrapMasterKey,
	unwrapMasterKey,
	clearWrappedMasterKey,
	hasWrappedMasterKey
} from '$lib/crypto/keystore';
import { ensureIdentity, type Keypair } from '$lib/crypto/identity';
import {
	migrateLegacy,
	unwrapWithPassword,
	unwrapWithMnemonic,
	rewrapForPassword,
	type RecoveryWraps
} from '$lib/crypto/recovery';

export type AuthState = 'loading' | 'password' | 'pin' | 'reset' | 'active';

interface KdfParams {
	auth_salt: string;
	master_salt: string;
}

interface RecoveryMaterial {
	recovery_salt: string | null;
	wrap_pw: string | null;
	wrap_pw_nonce: string | null;
	wrap_mn: string | null;
	wrap_mn_nonce: string | null;
	dek_migrated: boolean;
}

interface SessionResp {
	authenticated: boolean;
	needs: 'none' | 'pin' | 'password' | 'reset';
	username?: string;
	role?: 'admin' | 'child';
}

interface LoginResp {
	username: string;
	role: 'admin' | 'child';
	must_reset: boolean;
	csrf_token: string;
}

/** Read the readable CSRF cookie the server set, to echo in mutating requests. */
export function csrfToken(): string | null {
	if (!browser) return null;
	const m = document.cookie.match(/(?:^|;\s*)raspy_csrf=([^;]+)/);
	return m ? decodeURIComponent(m[1]) : null;
}

class Auth {
	state = $state<AuthState>('loading');
	username = $state<string | null>(null);
	role = $state<'admin' | 'child' | null>(null);
	error = $state<string | null>(null);
	busy = $state(false);

	/** In-memory vault key; null unless a password login or PIN unlock happened
	 *  this session. The vault module reads this. */
	#masterKey = $state<Uint8Array | null>(null);

	/** True when we have a live server session (`state==='active'`) but the vault
	 *  master key is missing — e.g. after a reload, which keeps the session cookie
	 *  but drops the in-memory key. The shell shows an unlock gate in this case.
	 *  Reactive so the gate appears/disappears as the key comes and goes. */
	get locked(): boolean {
		return this.state === 'active' && this.#masterKey === null;
	}

	/** Whether a PIN-wrapped key exists locally, so the lock gate can offer the
	 *  fast PIN unlock instead of the full password. Resolved on demand. */
	hasLocalPin = $state(false);

	get masterKey(): Uint8Array | null {
		return this.#masterKey;
	}

	/** This account's asymmetric identity keypair (for cross-account dropbox/chat
	 *  E2E). Provisioned lazily from the master key via ensureIdentity(); held in
	 *  memory only and cleared on lock/logout alongside the master key. */
	#keypair = $state<Keypair | null>(null);
	#identityPromise: Promise<Keypair> | null = null;

	get keypair(): Keypair | null {
		return this.#keypair;
	}

	/** Ensure the asymmetric identity is provisioned and return it. Idempotent and
	 *  coalesced: concurrent callers share one provisioning round-trip. Requires
	 *  the vault unlocked (master key in memory); throws otherwise. The dropbox and
	 *  chat apps call this on mount. */
	async ensureIdentity(): Promise<Keypair> {
		if (this.#keypair) return this.#keypair;
		if (!this.#masterKey) throw new Error('vault locked: cannot provision identity');
		if (!this.#identityPromise) {
			const key = this.#masterKey;
			this.#identityPromise = ensureIdentity(key)
				.then((kp) => {
					this.#keypair = kp;
					return kp;
				})
				.finally(() => {
					this.#identityPromise = null;
				});
		}
		return this.#identityPromise;
	}

	/** Ask the server what screen to show. Called on boot and after a 401. */
	async refresh(): Promise<void> {
		try {
			const res = await fetch(apiUrl('/api/auth/session'), {
				credentials: 'include',
				headers: { accept: 'application/json' }
			});
			const data: SessionResp = await res.json();
			if (data.authenticated && data.needs === 'none') {
				this.username = data.username ?? null;
				this.role = data.role ?? null;
				// The session survived but the in-memory master key may not have
				// (e.g. a page reload). If so, `locked` becomes true once we go
				// active; resolve whether the gate can offer the fast PIN unlock
				// BEFORE flipping state, so LockGate doesn't mount with a stale
				// hasLocalPin=false and wrongly default to the password form.
				if (this.#masterKey === null) {
					this.hasLocalPin = await hasWrappedMasterKey();
				}
				this.state = 'active';
			} else if (data.authenticated && data.needs === 'reset') {
				this.username = data.username ?? null;
				this.role = data.role ?? 'child';
				this.state = 'reset';
			} else if (data.needs === 'pin' && (await hasWrappedMasterKey())) {
				this.state = 'pin';
			} else {
				// needs password, OR pin but we have no local wrapped key to unwrap.
				this.state = 'password';
			}
		} catch {
			this.state = 'password';
		}
	}

	async login(username: string, password: string, pin?: string): Promise<void> {
		this.busy = true;
		this.error = null;
		try {
			const params = await this.#kdf(username);
			const authKey = await deriveAuthKey(password, params.auth_salt);
			const res = await fetch(apiUrl('/api/auth/login'), {
				method: 'POST',
				credentials: 'include',
				headers: { 'content-type': 'application/json' },
				body: JSON.stringify({ username, auth_key: authKey, ...(pin ? { pin } : {}) })
			});
			if (!res.ok) {
				this.error = res.status === 429 ? 'Too many attempts — wait and retry.' : 'Invalid credentials.';
				return;
			}
			const data = (await res.json()) as LoginResp;
			this.username = data.username;
			this.role = data.role;
			if (data.must_reset) {
				this.#masterKey = null;
				this.state = 'reset';
				return;
			}
			// Derive the password-KEK (== legacy master_key), then resolve it to the
			// vault DEK (unwrap for a migrated account, or migrate a legacy one). The
			// DEK is what every vault consumer reads; never sent anywhere.
			const kekPw = await deriveMasterKey(password, params.master_salt);
			this.#masterKey = await this.#resolveDEK(data.username, kekPw);
			this.state = 'active';
		} catch (e) {
			this.error = e instanceof Error ? e.message : 'Login failed.';
		} finally {
			this.busy = false;
		}
	}

	async completeSetup(newPassword: string, newPin: string): Promise<void> {
		if (!this.username) {
			this.error = 'No account is waiting for setup.';
			return;
		}
		this.busy = true;
		this.error = null;
		const username = this.username;
		try {
			const params = await this.#kdf(username);
			const authKey = await deriveAuthKey(newPassword, params.auth_salt);
			const res = await fetch(apiUrl('/api/auth/complete-setup'), {
				method: 'POST',
				credentials: 'include',
				headers: {
					'content-type': 'application/json',
					...(csrfToken() ? { 'x-csrf-token': csrfToken()! } : {})
				},
				body: JSON.stringify({ auth_key: authKey, pin: newPin })
			});
			if (!res.ok) {
				this.error = 'Could not finish setup.';
				return;
			}
			this.#masterKey = null;
			await clearWrappedMasterKey();
			await this.login(username, newPassword, newPin);
			if (this.state === 'active') {
				await this.setLocalPin(newPin);
			}
		} catch (e) {
			this.error = e instanceof Error ? e.message : 'Setup failed.';
		} finally {
			this.busy = false;
		}
	}

	/** Set/refresh the local PIN wrap of the current master key. Call after the
	 *  user picks a PIN (or reuse the account PIN flow). */
	async setLocalPin(pin: string): Promise<void> {
		if (!this.#masterKey) throw new Error('no master key in memory');
		await wrapMasterKey(this.#masterKey, pin);
	}

	async unlock(pin: string): Promise<void> {
		this.busy = true;
		this.error = null;
		try {
			// Server-side: PIN + valid refresh → new access token (rate-limited).
			const res = await fetch(apiUrl('/api/auth/unlock'), {
				method: 'POST',
				credentials: 'include',
				headers: {
					'content-type': 'application/json',
					...(csrfToken() ? { 'x-csrf-token': csrfToken()! } : {})
				},
				body: JSON.stringify({ pin })
			});
			if (!res.ok) {
				const body = await res.json().catch(() => ({}));
				if (typeof body.detail === 'string' && body.detail.includes('password')) {
					// Downgraded — must re-login with the password.
					await clearWrappedMasterKey();
					this.state = 'password';
					this.error = 'Too many PIN attempts — use your password.';
					return;
				}
				this.error = 'Wrong PIN.';
				return;
			}
			// Locally recover the master key from the PIN-wrapped blob.
			const key = await unwrapMasterKey(pin);
			if (!key) {
				// Server accepted but local unwrap failed (e.g. PIN changed) — fall
				// back to password to re-establish the master key.
				this.state = 'password';
				this.error = 'Please sign in with your password.';
				return;
			}
			this.#masterKey = key;
			this.state = 'active';
		} catch (e) {
			this.error = e instanceof Error ? e.message : 'Unlock failed.';
		} finally {
			this.busy = false;
		}
	}

	/** Recover the vault master key with a PIN, for the locked-but-active case
	 *  (reload kept the session, dropped the key). Local-only: the session is
	 *  already valid, so this just unwraps the PIN-wrapped key from IndexedDB. */
	async unlockWithPin(pin: string): Promise<void> {
		this.busy = true;
		this.error = null;
		try {
			const key = await unwrapMasterKey(pin);
			if (!key) {
				this.error = 'Wrong PIN.';
				return;
			}
			this.#masterKey = key;
		} catch (e) {
			this.error = e instanceof Error ? e.message : 'Unlock failed.';
		} finally {
			this.busy = false;
		}
	}

	/** Recover the vault master key by re-entering the password, for the
	 *  locked-but-active case. Re-derives the key from KDF params; verifies the
	 *  password against the server so a wrong one is rejected rather than silently
	 *  producing a garbage key. Re-wraps under the PIN if one is given. */
	async unlockWithPassword(password: string, pin?: string): Promise<void> {
		if (!this.username) {
			this.error = 'Session expired — sign in again.';
			this.state = 'password';
			return;
		}
		this.busy = true;
		this.error = null;
		try {
			const params = await this.#kdf(this.username);
			const authKey = await deriveAuthKey(password, params.auth_salt);
			// Verify the password by re-logging in (rotates the session, harmless).
			const res = await fetch(apiUrl('/api/auth/login'), {
				method: 'POST',
				credentials: 'include',
				headers: { 'content-type': 'application/json' },
				body: JSON.stringify({ username: this.username, auth_key: authKey, ...(pin ? { pin } : {}) })
			});
			if (!res.ok) {
				this.error = res.status === 429 ? 'Too many attempts — wait and retry.' : 'Wrong password.';
				return;
			}
			const kekPw = await deriveMasterKey(password, params.master_salt);
			this.#masterKey = await this.#resolveDEK(this.username, kekPw);
			if (pin) {
				try {
					await this.setLocalPin(pin);
					this.hasLocalPin = true;
				} catch {
					/* non-fatal */
				}
			}
		} catch (e) {
			this.error = e instanceof Error ? e.message : 'Unlock failed.';
		} finally {
			this.busy = false;
		}
	}

	async logout(): Promise<void> {
		try {
			await fetch(apiUrl('/api/auth/logout'), {
				method: 'POST',
				credentials: 'include',
				headers: { ...(csrfToken() ? { 'x-csrf-token': csrfToken()! } : {}) }
			});
		} catch {
			/* ignore */
		}
		this.#masterKey = null;
		this.#keypair = null;
		await clearWrappedMasterKey();
		this.username = null;
		this.role = null;
		this.state = 'password';
	}

	/** Called by api.ts when a request 401s and a refresh couldn't recover. */
	onAuthLost(needs: 'pin' | 'password'): void {
		this.#masterKey = needs === 'password' ? null : this.#masterKey;
		// The keypair was derived from the master key; if that's gone, drop it too.
		if (needs === 'password') this.#keypair = null;
		this.state = needs;
	}

	async #kdf(username: string): Promise<KdfParams> {
		const res = await fetch(apiUrl(`/api/auth/kdf/${encodeURIComponent(username)}`), {
			headers: { accept: 'application/json' }
		});
		if (!res.ok) throw new Error('could not fetch KDF params');
		return res.json();
	}

	// --- recovery / DEK envelope (plan/35) -----------------------------------

	/** A freshly-minted recovery phrase the UI must show the user exactly once.
	 *  Set during migration (or first setup); cleared once acknowledged. */
	pendingMnemonic = $state<string | null>(null);

	acknowledgeMnemonic(): void {
		this.pendingMnemonic = null;
	}

	async #recoveryMaterial(username: string): Promise<RecoveryMaterial> {
		const res = await fetch(apiUrl(`/api/auth/recovery/${encodeURIComponent(username)}`), {
			headers: { accept: 'application/json' }
		});
		if (!res.ok) throw new Error('could not fetch recovery material');
		return res.json();
	}

	async #putRecovery(wraps: RecoveryWraps): Promise<void> {
		const res = await fetch(apiUrl('/api/auth/recovery'), {
			method: 'PUT',
			credentials: 'include',
			headers: {
				'content-type': 'application/json',
				...(csrfToken() ? { 'x-csrf-token': csrfToken()! } : {})
			},
			body: JSON.stringify(wraps)
		});
		if (!res.ok) throw new Error(`could not store recovery envelope: ${res.status}`);
	}

	/**
	 * Turn the password-derived key (KEK_pw, today's master_key) into the vault
	 * DEK. This is the single chokepoint: every consumer reads `#masterKey`, so we
	 * only change *what it resolves to* here, after a password login/unlock.
	 *
	 *  - migrated account  → unwrap wrap_pw → DEK.
	 *  - legacy account    → DEK *is* KEK_pw (no ciphertext changes); mint a
	 *                        mnemonic, persist both wraps, surface the phrase once.
	 *
	 * Must run while authed (so the PUT is accepted) — i.e. after a successful
	 * login/unlock that established the session. Returns the DEK to store.
	 */
	async #resolveDEK(username: string, kekPw: Uint8Array): Promise<Uint8Array> {
		const mat = await this.#recoveryMaterial(username);
		if (mat.dek_migrated && mat.wrap_pw && mat.wrap_pw_nonce) {
			const dek = await unwrapWithPassword(kekPw, {
				wrap_pw: mat.wrap_pw,
				wrap_pw_nonce: mat.wrap_pw_nonce
			});
			// If the wrap won't open under this password-KEK, the account's wrap_pw
			// is stale relative to the password (shouldn't happen on a normal login;
			// a deliberate password change re-wraps). Fall back to treating KEK_pw as
			// the key so the session still works rather than bricking the vault.
			if (dek) return dek;
			return kekPw;
		}
		// Legacy account: migrate in place. DEK == KEK_pw, so nothing is
		// re-encrypted. Persist the envelope and show the phrase once.
		try {
			const { dek, wraps, mnemonic } = await migrateLegacy(kekPw);
			await this.#putRecovery(wraps);
			this.pendingMnemonic = mnemonic;
			return dek;
		} catch {
			// Migration is best-effort: if the PUT fails (offline, race), keep the
			// user working with KEK_pw as the key; we'll retry on the next unlock.
			return kekPw;
		}
	}

	/**
	 * Break-glass recovery from the login screen: the user supplies their mnemonic
	 * and a new password (+ optional PIN). We unwrap the DEK locally from wrap_mn,
	 * reset the server-side password via /recover, re-wrap wrap_pw under the new
	 * password-KEK, then log in fresh. The vault (DEK) is preserved end to end.
	 */
	async recoverWithMnemonic(
		username: string,
		mnemonic: string,
		newPassword: string,
		newPin?: string
	): Promise<void> {
		this.busy = true;
		this.error = null;
		try {
			const mat = await this.#recoveryMaterial(username);
			if (!mat.dek_migrated || !mat.wrap_mn || !mat.wrap_mn_nonce || !mat.recovery_salt) {
				this.error = 'No recovery phrase is set up for this account.';
				return;
			}
			const dek = await unwrapWithMnemonic(mnemonic, {
				recovery_salt: mat.recovery_salt,
				wrap_mn: mat.wrap_mn,
				wrap_mn_nonce: mat.wrap_mn_nonce
			});
			if (!dek) {
				this.error = 'That recovery phrase is not correct.';
				return;
			}
			// Reset the password server-side (proven by possession of the mnemonic).
			const params = await this.#kdf(username);
			const newAuthKey = await deriveAuthKey(newPassword, params.auth_salt);
			const res = await fetch(apiUrl('/api/auth/recover'), {
				method: 'POST',
				credentials: 'include',
				headers: { 'content-type': 'application/json' },
				body: JSON.stringify({
					username,
					new_auth_key: newAuthKey,
					...(newPin ? { new_pin: newPin } : {})
				})
			});
			if (!res.ok) {
				this.error = res.status === 429 ? 'Too many attempts — wait and retry.' : 'Recovery failed.';
				return;
			}
			// Log in with the new password to get a session, then re-wrap wrap_pw
			// under the new password-KEK and persist it.
			await this.login(username, newPassword, newPin);
			if (this.state !== 'active') return;
			const newKekPw = await deriveMasterKey(newPassword, params.master_salt);
			const wraps = await rewrapForPassword(dek, newKekPw, {
				recovery_salt: mat.recovery_salt,
				wrap_pw: mat.wrap_pw ?? '',
				wrap_pw_nonce: mat.wrap_pw_nonce ?? '',
				wrap_mn: mat.wrap_mn,
				wrap_mn_nonce: mat.wrap_mn_nonce
			});
			await this.#putRecovery(wraps);
			// The in-memory key must be the DEK (matches every existing ciphertext),
			// not the freshly-derived KEK_pw.
			this.#masterKey = dek;
			if (newPin) {
				try {
					await this.setLocalPin(newPin);
					this.hasLocalPin = true;
				} catch {
					/* non-fatal */
				}
			}
		} catch (e) {
			this.error = e instanceof Error ? e.message : 'Recovery failed.';
		} finally {
			this.busy = false;
		}
	}
}

export const auth = new Auth();

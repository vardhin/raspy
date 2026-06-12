// Auth store — drives the shell gate and holds the in-memory vault master key.
//
// States:
//   'loading'  — initial; asking the server what we need
//   'password' — no usable session; show full password login
//   'pin'      — access token lapsed but refresh still valid; show mini-PIN
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

export type AuthState = 'loading' | 'password' | 'pin' | 'active';

interface KdfParams {
	auth_salt: string;
	master_salt: string;
}

interface SessionResp {
	authenticated: boolean;
	needs: 'none' | 'pin' | 'password';
	username?: string;
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
	error = $state<string | null>(null);
	busy = $state(false);

	/** In-memory vault key; null unless a password login or PIN unlock happened
	 *  this session. The vault module reads this. */
	#masterKey: Uint8Array | null = null;

	get masterKey(): Uint8Array | null {
		return this.#masterKey;
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
				this.state = 'active';
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

	async login(username: string, password: string): Promise<void> {
		this.busy = true;
		this.error = null;
		try {
			const params = await this.#kdf(username);
			const authKey = await deriveAuthKey(password, params.auth_salt);
			const res = await fetch(apiUrl('/api/auth/login'), {
				method: 'POST',
				credentials: 'include',
				headers: { 'content-type': 'application/json' },
				body: JSON.stringify({ username, auth_key: authKey })
			});
			if (!res.ok) {
				this.error = res.status === 429 ? 'Too many attempts — wait and retry.' : 'Invalid credentials.';
				return;
			}
			// Derive + hold the vault master key; never sent anywhere.
			this.#masterKey = await deriveMasterKey(password, params.master_salt);
			this.username = username;
			this.state = 'active';
		} catch (e) {
			this.error = e instanceof Error ? e.message : 'Login failed.';
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
		await clearWrappedMasterKey();
		this.username = null;
		this.state = 'password';
	}

	/** Called by api.ts when a request 401s and a refresh couldn't recover. */
	onAuthLost(needs: 'pin' | 'password'): void {
		this.#masterKey = needs === 'password' ? null : this.#masterKey;
		this.state = needs;
	}

	async #kdf(username: string): Promise<KdfParams> {
		const res = await fetch(apiUrl(`/api/auth/kdf/${encodeURIComponent(username)}`), {
			headers: { accept: 'application/json' }
		});
		if (!res.ok) throw new Error('could not fetch KDF params');
		return res.json();
	}
}

export const auth = new Auth();

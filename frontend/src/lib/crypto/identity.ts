// Per-account asymmetric identity — the layer that makes cross-account E2E
// messaging possible (dropbox + chat). See backend attachments/identity.
//
// The vault master key (kdf.ts) is symmetric and private to one account, so it
// can encrypt my OWN store but can never let account A send something only B can
// read. For that each account gets an X25519 keypair:
//
//   public key  — published to the Pi in the clear; anyone can seal a box to it.
//   secret key  — wrapped (crypto_secretbox) under THIS account's vault master key
//                 and stored on the Pi as opaque ciphertext. Only the owner, with
//                 the vault unlocked, can unwrap it to open boxes sealed to them.
//
// Sending = crypto_box_seal(data, recipientPublicKey)  (anonymous sealed box).
// Reading = crypto_box_seal_open(blob, myPublicKey, mySecretKey).
//
// The unwrapped secret key lives only in memory (in auth.svelte, next to the
// master key) and is dropped on lock/logout.

import { sodiumReady, b64encode, b64decode, type Sodium } from './sodium';
import { attUrl } from '$lib/api';
import { csrfToken } from '$lib/auth.svelte';

export interface Keypair {
	publicKey: Uint8Array;
	secretKey: Uint8Array;
}

interface MeResponse {
	public_key: string;
	sk_wrapped: string;
	sk_nonce: string;
}

interface WrappedSecret {
	sk_wrapped: string; // b64 crypto_secretbox(secretKey, nonce, masterKey)
	sk_nonce: string; // b64 nonce
}

function authHeaders(json = true): Record<string, string> {
	const t = csrfToken();
	return {
		...(json ? { 'content-type': 'application/json' } : {}),
		...(t ? { 'x-csrf-token': t } : {})
	};
}

/** Wrap (encrypt) a secret key under the vault master key for storage on the Pi. */
function wrapSecret(s: Sodium, secretKey: Uint8Array, masterKey: Uint8Array): WrappedSecret {
	const nonce = s.randombytes_buf(s.crypto_secretbox_NONCEBYTES);
	const ct = s.crypto_secretbox_easy(secretKey, nonce, masterKey);
	return { sk_wrapped: b64encode(s, ct), sk_nonce: b64encode(s, nonce) };
}

/** Unwrap a secret key the Pi stored for us, using the in-memory master key. */
function unwrapSecret(
	s: Sodium,
	wrapped: WrappedSecret,
	masterKey: Uint8Array
): Uint8Array | null {
	try {
		return s.crypto_secretbox_open_easy(
			b64decode(s, wrapped.sk_wrapped),
			b64decode(s, wrapped.sk_nonce),
			masterKey
		);
	} catch {
		return null; // wrong master key (MAC failed) or corrupt blob
	}
}

async function fetchMe(): Promise<MeResponse | null> {
	const res = await fetch(attUrl('identity', 'me'), { credentials: 'include' });
	if (res.status === 204) return null;
	if (!res.ok) throw new Error(`identity/me failed: ${res.status}`);
	return (await res.json()) as MeResponse;
}

async function publish(
	s: Sodium,
	keypair: Keypair,
	masterKey: Uint8Array
): Promise<void> {
	const wrapped = wrapSecret(s, keypair.secretKey, masterKey);
	const res = await fetch(attUrl('identity', 'me'), {
		method: 'PUT',
		credentials: 'include',
		headers: authHeaders(),
		body: JSON.stringify({
			public_key: b64encode(s, keypair.publicKey),
			sk_wrapped: wrapped.sk_wrapped,
			sk_nonce: wrapped.sk_nonce
		})
	});
	if (!res.ok) throw new Error(`identity publish failed: ${res.status}`);
}

/**
 * Ensure this account has a published keypair and return it, decrypted in memory.
 *
 * - First unlock ever: generate a fresh X25519 keypair, wrap the secret under the
 *   master key, publish it, and return it.
 * - Later unlocks: fetch the published material and unwrap the secret with the
 *   master key (keypair is stable across sessions and password changes).
 * - Password changed (master key changed but same keypair): if the stored wrap no
 *   longer opens, we cannot recover the old secret key, so we mint a NEW keypair
 *   and re-publish. Anything sealed to the old key before this point is lost — an
 *   acceptable, rare trade for a personal system. (Re-wrapping the same key on a
 *   *deliberate* password change is handled by rewrapForNewMaster below.)
 *
 * Must be called with the vault unlocked (master key in memory).
 */
export async function ensureIdentity(masterKey: Uint8Array): Promise<Keypair> {
	const s = await sodiumReady();
	const me = await fetchMe();
	if (me) {
		const secretKey = unwrapSecret(s, me, masterKey);
		if (secretKey) {
			return { publicKey: b64decode(s, me.public_key), secretKey };
		}
		// Stored wrap doesn't open under the current master key (password changed
		// without a re-wrap). Fall through to mint a fresh keypair.
	}
	const kp = s.crypto_box_keypair();
	const keypair: Keypair = { publicKey: kp.publicKey, secretKey: kp.privateKey };
	await publish(s, keypair, masterKey);
	return keypair;
}

/**
 * Re-wrap the SAME keypair under a new master key, so a deliberate password change
 * keeps the identity (and everything previously sealed to it) intact. Call after
 * the master key is rotated, with the still-known keypair from the old session.
 */
export async function rewrapForNewMaster(
	keypair: Keypair,
	newMasterKey: Uint8Array
): Promise<void> {
	const s = await sodiumReady();
	await publish(s, keypair, newMasterKey);
}

// --- sealing / opening (used by dropbox + chat) ------------------------------

/** Anonymously seal bytes to a recipient's public key. Only they can open it. */
export async function sealTo(recipientPublicKeyB64: string, data: Uint8Array): Promise<Uint8Array> {
	const s = await sodiumReady();
	return s.crypto_box_seal(data, b64decode(s, recipientPublicKeyB64));
}

/** Open a sealed box addressed to me. Returns null if it isn't ours / is corrupt. */
export async function sealOpen(keypair: Keypair, blob: Uint8Array): Promise<Uint8Array | null> {
	const s = await sodiumReady();
	try {
		return s.crypto_box_seal_open(blob, keypair.publicKey, keypair.secretKey);
	} catch {
		return null;
	}
}

/** Convenience: seal a short string (e.g. a chat text) to a public key, b64 out. */
export async function sealTextTo(recipientPublicKeyB64: string, text: string): Promise<string> {
	const s = await sodiumReady();
	const sealed = await sealTo(recipientPublicKeyB64, new TextEncoder().encode(text));
	return b64encode(s, sealed);
}

/** Convenience: open a b64 sealed string addressed to me back into text. */
export async function openTextFor(keypair: Keypair, sealedB64: string): Promise<string | null> {
	const s = await sodiumReady();
	const plain = await sealOpen(keypair, b64decode(s, sealedB64));
	return plain ? new TextDecoder().decode(plain) : null;
}

// --- the public-key directory (account picker source) ------------------------

export interface DirectoryEntry {
	username: string;
	/** null when the account exists but hasn't published a key yet (never unlocked). */
	public_key: string | null;
	/** Whether this account can be sent to (has a published key). */
	has_key: boolean;
	role: 'admin' | 'child';
}

/** Every account on the system (the picker source). Accounts without a published
 *  key appear with `has_key: false` so the UI can show them but block sending. */
export async function fetchDirectory(): Promise<DirectoryEntry[]> {
	const res = await fetch(attUrl('identity', 'keys'), { credentials: 'include' });
	if (!res.ok) throw new Error(`identity directory failed: ${res.status}`);
	return (await res.json()) as DirectoryEntry[];
}

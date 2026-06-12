// Local key storage for the mini-PIN flow.
//
// On a full password login the client holds the vault master_key in memory. To
// support "stale session → unlock with PIN" WITHOUT re-entering the password, we
// wrap (encrypt) the master_key under a PIN-derived key and stash that wrapped
// blob in IndexedDB. PIN unlock re-derives the PIN key and unwraps it locally.
//
// Why this is safe-enough: the PIN is low-entropy, so the wrapped blob must never
// reach the server (it doesn't — IndexedDB is local) and must be useless without
// also defeating the server-side rate-limited PIN check. An attacker with the
// device could brute the local blob offline, so we (a) keep Argon2id moderate on
// the PIN wrap and (b) the server still independently rate-limits /unlock and
// downgrades to password after a few failures. The PIN is convenience, the
// password is the real root (see plan Layer 0 / Layer 2).

import { sodiumReady, b64encode, b64decode } from './sodium';

const DB_NAME = 'raspy-keystore';
const STORE = 'keys';
const WRAP_KEY = 'master_wrap';

// Moderate Argon2 for the PIN wrap (local-only, so a bit more cost is fine).
const PIN_OPS = 3;
const PIN_MEM = 64 * 1024 * 1024;

interface WrappedMaster {
	salt: string; // b64
	nonce: string; // b64
	cipher: string; // b64
}

function idb(): Promise<IDBDatabase> {
	return new Promise((resolve, reject) => {
		const req = indexedDB.open(DB_NAME, 1);
		req.onupgradeneeded = () => req.result.createObjectStore(STORE);
		req.onsuccess = () => resolve(req.result);
		req.onerror = () => reject(req.error);
	});
}

async function idbGet<T>(key: string): Promise<T | undefined> {
	const db = await idb();
	return new Promise((resolve, reject) => {
		const tx = db.transaction(STORE, 'readonly').objectStore(STORE).get(key);
		tx.onsuccess = () => resolve(tx.result as T | undefined);
		tx.onerror = () => reject(tx.error);
	});
}

async function idbPut(key: string, value: unknown): Promise<void> {
	const db = await idb();
	return new Promise((resolve, reject) => {
		const tx = db.transaction(STORE, 'readwrite').objectStore(STORE).put(value, key);
		tx.onsuccess = () => resolve();
		tx.onerror = () => reject(tx.error);
	});
}

async function idbDel(key: string): Promise<void> {
	const db = await idb();
	return new Promise((resolve, reject) => {
		const tx = db.transaction(STORE, 'readwrite').objectStore(STORE).delete(key);
		tx.onsuccess = () => resolve();
		tx.onerror = () => reject(tx.error);
	});
}

/** Encrypt master_key under the PIN and persist it locally for PIN unlock. */
export async function wrapMasterKey(masterKey: Uint8Array, pin: string): Promise<void> {
	const s = await sodiumReady();
	const salt = s.randombytes_buf(s.crypto_pwhash_SALTBYTES);
	const pinKey = s.crypto_pwhash(
		s.crypto_secretbox_KEYBYTES,
		pin,
		salt,
		PIN_OPS,
		PIN_MEM,
		s.crypto_pwhash_ALG_ARGON2ID13
	);
	const nonce = s.randombytes_buf(s.crypto_secretbox_NONCEBYTES);
	const cipher = s.crypto_secretbox_easy(masterKey, nonce, pinKey);
	const blob: WrappedMaster = {
		salt: b64encode(s, salt),
		nonce: b64encode(s, nonce),
		cipher: b64encode(s, cipher)
	};
	await idbPut(WRAP_KEY, blob);
}

/** Try to recover master_key from the local PIN-wrapped blob. null on bad PIN. */
export async function unwrapMasterKey(pin: string): Promise<Uint8Array | null> {
	const blob = await idbGet<WrappedMaster>(WRAP_KEY);
	if (!blob) return null;
	const s = await sodiumReady();
	const salt = b64decode(s, blob.salt);
	const pinKey = s.crypto_pwhash(
		s.crypto_secretbox_KEYBYTES,
		pin,
		salt,
		PIN_OPS,
		PIN_MEM,
		s.crypto_pwhash_ALG_ARGON2ID13
	);
	try {
		return s.crypto_secretbox_open_easy(b64decode(s, blob.cipher), b64decode(s, blob.nonce), pinKey);
	} catch {
		return null; // wrong PIN (MAC failed)
	}
}

export async function hasWrappedMasterKey(): Promise<boolean> {
	return (await idbGet<WrappedMaster>(WRAP_KEY)) !== undefined;
}

export async function clearWrappedMasterKey(): Promise<void> {
	await idbDel(WRAP_KEY);
}

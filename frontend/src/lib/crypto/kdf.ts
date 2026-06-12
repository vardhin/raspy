// Password key derivation — MUST stay in lock-step with backend
// raspy/core/auth/kdf.py. Two independent keys come from the one password:
//
//   auth_key   = base64url( crypto_pwhash(32, pw, auth_salt,   OPS, MEM, ARGON2ID13) )
//   master_key =            crypto_pwhash(32, pw, master_salt, OPS, MEM, ARGON2ID13)
//
// auth_key is sent to the server at login (the server hashes it again before
// storing). master_key NEVER leaves this device — it encrypts the vault. Same
// password, different salts ⇒ the server can never derive the vault key.

import { sodiumReady, b64encode, b64decode } from './sodium';

// Interactive-tier params — identical to PWHASH_OPSLIMIT / PWHASH_MEMLIMIT_BYTES
// in kdf.py. The browser/phone bears this cost (the spine never does it).
const OPSLIMIT = 2;
const MEMLIMIT_BYTES = 64 * 1024 * 1024; // 64 MiB
const KEY_BYTES = 32;

async function deriveRaw(password: string, saltB64: string): Promise<Uint8Array> {
	const s = await sodiumReady();
	const salt = b64decode(s, saltB64); // 16 bytes
	return s.crypto_pwhash(
		KEY_BYTES,
		password,
		salt,
		OPSLIMIT,
		MEMLIMIT_BYTES,
		s.crypto_pwhash_ALG_ARGON2ID13
	);
}

/** The string sent to /api/auth/login as `auth_key`. */
export async function deriveAuthKey(password: string, authSaltB64: string): Promise<string> {
	const s = await sodiumReady();
	return b64encode(s, await deriveRaw(password, authSaltB64));
}

/** The raw 32-byte vault master key. Keep it out of logs/storage in plaintext. */
export async function deriveMasterKey(
	password: string,
	masterSaltB64: string
): Promise<Uint8Array> {
	return deriveRaw(password, masterSaltB64);
}

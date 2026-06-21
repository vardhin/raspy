// Vault recovery envelope — plan/35.
//
// The vault root is no longer the password-derived key directly; it is a random
// 32-byte Data Encryption Key (DEK) wrapped under two independent key-encryption
// keys (KEKs), either of which recovers the same DEK:
//
//   KEK_pw = Argon2id(password, master_salt)     (== the legacy master_key)
//   KEK_mn = Argon2id(mnemonic, recovery_salt)
//
//   wrap_pw = secretbox(DEK, nonce_pw, KEK_pw)
//   wrap_mn = secretbox(DEK, nonce_mn, KEK_mn)
//
// Both wraps live on the Pi as opaque ciphertext (auth account row). The server
// never sees the DEK, the password, or the mnemonic. A password change re-wraps
// wrap_pw only; the DEK (and the whole vault/identity) survives untouched.
//
// COMPATIBILITY (the load-bearing rule): for an account migrated from the legacy
// scheme, the DEK is *defined to equal* the old master_key, so no existing
// ciphertext is ever re-encrypted. `migrateLegacy()` produces wrap_pw as
// secretbox(masterKey, …, masterKey) — the key wrapped under itself — which is
// trivially producible the moment the vault is unlocked with the password.

import { generateMnemonic, validateMnemonic, mnemonicToEntropy } from '@scure/bip39';
import { wordlist } from '@scure/bip39/wordlists/english.js';
import { sodiumReady, b64encode, b64decode, type Sodium } from './sodium';

// 128 bits => 12 words. Plenty for a break-glass root the user transcribes once.
const MNEMONIC_STRENGTH = 128;

// Argon2 for the mnemonic KEK. The phrase is high-entropy, so we don't need a
// huge cost, but match the interactive vault tier so derivation is uniform.
const MN_OPS = 3;
const MN_MEM = 64 * 1024 * 1024; // 64 MiB

export interface RecoveryWraps {
	recovery_salt: string; // b64 (16B) salt for KEK_mn
	wrap_pw: string; // b64 secretbox(DEK, nonce_pw, KEK_pw)
	wrap_pw_nonce: string; // b64
	wrap_mn: string; // b64 secretbox(DEK, nonce_mn, KEK_mn)
	wrap_mn_nonce: string; // b64
}

/** A fresh BIP39 mnemonic (12 words, English). Shown to the user exactly once. */
export function newMnemonic(): string {
	return generateMnemonic(wordlist, MNEMONIC_STRENGTH);
}

/** Validate a user-entered phrase (word membership + BIP39 checksum). Normalizes
 *  whitespace/case so a slightly sloppy transcription still validates. */
export function isValidMnemonic(phrase: string): boolean {
	return validateMnemonic(normalizeMnemonic(phrase), wordlist);
}

/** Lowercase + collapse internal whitespace to single spaces, trimmed. */
export function normalizeMnemonic(phrase: string): string {
	return phrase.trim().toLowerCase().replace(/\s+/g, ' ');
}

/** Derive KEK_mn = Argon2id(mnemonic_entropy, recovery_salt). We hash the BIP39
 *  *entropy* bytes (not the raw words) so unicode/spacing can never shift the key
 *  once the phrase validates. */
async function deriveMnemonicKey(
	s: Sodium,
	mnemonic: string,
	recoverySaltB64: string
): Promise<Uint8Array> {
	const entropy = mnemonicToEntropy(normalizeMnemonic(mnemonic), wordlist); // Uint8Array
	const salt = b64decode(s, recoverySaltB64); // 16 bytes
	return s.crypto_pwhash(
		s.crypto_secretbox_KEYBYTES,
		// crypto_pwhash takes a string|Uint8Array password; pass the entropy bytes.
		entropy,
		salt,
		MN_OPS,
		MN_MEM,
		s.crypto_pwhash_ALG_ARGON2ID13
	);
}

function wrap(s: Sodium, dek: Uint8Array, kek: Uint8Array): { cipher: string; nonce: string } {
	const nonce = s.randombytes_buf(s.crypto_secretbox_NONCEBYTES);
	const cipher = s.crypto_secretbox_easy(dek, nonce, kek);
	return { cipher: b64encode(s, cipher), nonce: b64encode(s, nonce) };
}

function unwrap(s: Sodium, cipherB64: string, nonceB64: string, kek: Uint8Array): Uint8Array | null {
	try {
		return s.crypto_secretbox_open_easy(b64decode(s, cipherB64), b64decode(s, nonceB64), kek);
	} catch {
		return null; // wrong key (MAC failed) or corrupt blob
	}
}

/**
 * Migrate a legacy account to the envelope, WITHOUT touching any ciphertext.
 *
 * The DEK is set to the current `masterKey` (= KEK_pw), so every existing vault /
 * identity / media blob stays valid. We mint a mnemonic, derive KEK_mn, and
 * return both wraps to persist + the phrase to show once. The returned DEK equals
 * `masterKey`, so the caller can keep using it as the in-memory vault key with no
 * change to any consumer.
 */
export async function migrateLegacy(
	masterKey: Uint8Array
): Promise<{ dek: Uint8Array; wraps: RecoveryWraps; mnemonic: string }> {
	const s = await sodiumReady();
	const dek = masterKey; // compatibility pin: DEK == old master_key
	const mnemonic = newMnemonic();
	const recoverySalt = s.randombytes_buf(16);
	const recovery_salt = b64encode(s, recoverySalt);
	const kekMn = await deriveMnemonicKey(s, mnemonic, recovery_salt);

	const pw = wrap(s, dek, masterKey); // DEK wrapped under itself (KEK_pw)
	const mn = wrap(s, dek, kekMn);
	return {
		dek,
		mnemonic,
		wraps: {
			recovery_salt,
			wrap_pw: pw.cipher,
			wrap_pw_nonce: pw.nonce,
			wrap_mn: mn.cipher,
			wrap_mn_nonce: mn.nonce
		}
	};
}

/** Unwrap the DEK using the password-KEK (the in-memory `master_key`). null on a
 *  wrong key. Used on a normal login of a migrated account. */
export async function unwrapWithPassword(
	kekPw: Uint8Array,
	wraps: Pick<RecoveryWraps, 'wrap_pw' | 'wrap_pw_nonce'>
): Promise<Uint8Array | null> {
	const s = await sodiumReady();
	return unwrap(s, wraps.wrap_pw, wraps.wrap_pw_nonce, kekPw);
}

/** Unwrap the DEK from the mnemonic (break-glass). null on a wrong/invalid phrase. */
export async function unwrapWithMnemonic(
	mnemonic: string,
	wraps: Pick<RecoveryWraps, 'recovery_salt' | 'wrap_mn' | 'wrap_mn_nonce'>
): Promise<Uint8Array | null> {
	if (!isValidMnemonic(mnemonic) || !wraps.recovery_salt) return null;
	const s = await sodiumReady();
	const kekMn = await deriveMnemonicKey(s, mnemonic, wraps.recovery_salt);
	return unwrap(s, wraps.wrap_mn, wraps.wrap_mn_nonce, kekMn);
}

/** Re-wrap an existing DEK under a new password-KEK (after a password change or a
 *  break-glass reset). Keeps the same mnemonic wrap; pass it back through. The
 *  caller persists the full set via PUT /auth/recovery. */
export async function rewrapForPassword(
	dek: Uint8Array,
	newKekPw: Uint8Array,
	existing: RecoveryWraps
): Promise<RecoveryWraps> {
	const s = await sodiumReady();
	const pw = wrap(s, dek, newKekPw);
	return { ...existing, wrap_pw: pw.cipher, wrap_pw_nonce: pw.nonce };
}

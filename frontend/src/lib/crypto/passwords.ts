// Password-keeper crypto — all in the client; the Pi never sees plaintext.
//
// The whole keeper is ONE opaque encrypted blob (like the vault manifest): the
// entry list is JSON, encrypted under the vault master key with libsodium
// crypto_secretbox (nonce(24) || ciphertext), and stored on the server as opaque
// bytes via PUT /api/att/passwords/store. So: lose the password ⇒ lose the
// keeper; the server holds only ciphertext it can't read.
//
// There are no per-entry server endpoints — add/edit/delete/reorder mutate the
// decrypted list in memory and re-upload the whole blob. That keeps the backend
// trivial and the design auditably zero-knowledge.

import { sodiumReady } from './sodium';
import { auth } from '$lib/auth.svelte';
import { attUrl } from '$lib/api';

export interface PasswordEntry {
	id: string; // random id, plaintext only inside the encrypted blob
	title: string; // e.g. "GitHub"
	username: string;
	password: string;
	url: string;
	note: string; // a small free-text note
	created: number; // unix seconds
	updated: number;
}

export interface PasswordStore {
	version: 1;
	entries: PasswordEntry[];
}

export function emptyStore(): PasswordStore {
	return { version: 1, entries: [] };
}

// Tolerate older/looser shapes so a store always opens. Defaults every field so
// the UI never renders `undefined`.
export function normalizeStore(raw: unknown): PasswordStore {
	const m = (raw ?? {}) as Partial<PasswordStore>;
	const entries = (m.entries ?? []).map((e) => ({
		id: String(e?.id ?? crypto.randomUUID()),
		title: String(e?.title ?? ''),
		username: String(e?.username ?? ''),
		password: String(e?.password ?? ''),
		url: String(e?.url ?? ''),
		note: String(e?.note ?? ''),
		created: Number(e?.created ?? Date.now() / 1000),
		updated: Number(e?.updated ?? Date.now() / 1000)
	}));
	return { version: 1, entries };
}

function masterKey(): Uint8Array {
	const k = auth.masterKey;
	if (!k) throw new Error('keeper locked: no master key (sign in with your password)');
	return k;
}

export async function loadStore(): Promise<PasswordStore> {
	const res = await fetch(attUrl('passwords', 'store'), { credentials: 'include' });
	if (res.status === 204) return emptyStore();
	if (!res.ok) throw new Error(`store load failed: ${res.status}`);
	const blob = new Uint8Array(await res.arrayBuffer());
	const s = await sodiumReady();
	// secretbox: nonce(24) || ciphertext
	const nonce = blob.slice(0, s.crypto_secretbox_NONCEBYTES);
	const ct = blob.slice(s.crypto_secretbox_NONCEBYTES);
	const plain = s.crypto_secretbox_open_easy(ct, nonce, masterKey());
	return normalizeStore(JSON.parse(new TextDecoder().decode(plain)));
}

export async function saveStore(store: PasswordStore): Promise<void> {
	const s = await sodiumReady();
	const plain = new TextEncoder().encode(JSON.stringify(store));
	const nonce = s.randombytes_buf(s.crypto_secretbox_NONCEBYTES);
	const ct = s.crypto_secretbox_easy(plain, nonce, masterKey());
	const blob = new Uint8Array([...nonce, ...ct]);
	const res = await fetch(attUrl('passwords', 'store'), {
		method: 'PUT',
		credentials: 'include',
		headers: { 'content-type': 'application/octet-stream' },
		body: blob as BlobPart
	});
	if (!res.ok) throw new Error(`store save failed: ${res.status}`);
}

// --- a tiny, dependency-free password generator -----------------------------
// Uses crypto.getRandomValues with rejection sampling so each character is
// uniform over the alphabet (no modulo bias).
const GEN_LOWER = 'abcdefghijklmnopqrstuvwxyz';
const GEN_UPPER = 'ABCDEFGHIJKLMNOPQRSTUVWXYZ';
const GEN_DIGITS = '0123456789';
const GEN_SYMBOLS = '!@#$%^&*()-_=+[]{};:,.?';

export interface GenOptions {
	length: number;
	lower: boolean;
	upper: boolean;
	digits: boolean;
	symbols: boolean;
}

export function generatePassword(opts: GenOptions): string {
	let alphabet = '';
	if (opts.lower) alphabet += GEN_LOWER;
	if (opts.upper) alphabet += GEN_UPPER;
	if (opts.digits) alphabet += GEN_DIGITS;
	if (opts.symbols) alphabet += GEN_SYMBOLS;
	if (alphabet === '') alphabet = GEN_LOWER + GEN_UPPER + GEN_DIGITS;
	const n = Math.max(1, Math.min(256, Math.floor(opts.length)));
	const out: string[] = [];
	// Largest multiple of alphabet.length that fits in a byte — reject above it
	// so the modulo is unbiased.
	const limit = Math.floor(256 / alphabet.length) * alphabet.length;
	const buf = new Uint8Array(1);
	while (out.length < n) {
		crypto.getRandomValues(buf);
		if (buf[0] >= limit) continue;
		out.push(alphabet[buf[0] % alphabet.length]);
	}
	return out.join('');
}

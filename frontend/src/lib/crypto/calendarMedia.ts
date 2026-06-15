// Calendar photo encryption — the same zero-knowledge scheme the vault uses, but
// the per-image data key is sealed under the master key and stored *next to the
// blob on the Pi* (in the images table) instead of inside one big manifest. The
// Pi therefore holds only opaque ciphertext + a wrapped key it can't open, while
// the entry's title/description/date stay plaintext (so server-side reminders keep
// working).
//
// Per image:
//   dataKey  = random secretstream key      (encrypts the bytes, chunked AEAD)
//   header   = secretstream header           (not secret; stored plaintext b64)
//   keyWrapped = secretbox(dataKey, nonce, masterKey)   (stored b64 + its nonce)
//
// Lose the password ⇒ lose the photos; the server can never read them.

import { sodiumReady, b64encode, b64decode, type Sodium } from './sodium';
import { auth } from '$lib/auth.svelte';

const STREAM_CHUNK = 64 * 1024;

export interface EncryptedImage {
	ciphertext: Uint8Array;
	mime: string;
	keyWrapped: string; // b64 secretbox of the data key under the master key
	nonceWrapped: string; // b64 nonce for that secretbox
	header: string; // b64 secretstream header
}

function masterKey(): Uint8Array {
	const k = auth.masterKey;
	if (!k) throw new Error('calendar locked: no master key (sign in with your password)');
	return k;
}

async function sha256Hex(s: Sodium, data: Uint8Array): Promise<string> {
	const digest = s.crypto_hash_sha256(data);
	return Array.from(digest)
		.map((b) => b.toString(16).padStart(2, '0'))
		.join('');
}

// Chunk + frame the secretstream output exactly like the vault, so the same
// re-split-and-decrypt logic works on the way back.
export async function encryptImage(
	file: File,
	onProgress?: (fraction: number) => void
): Promise<EncryptedImage> {
	const s = await sodiumReady();
	const dataKey = s.crypto_secretstream_xchacha20poly1305_keygen();
	const init = s.crypto_secretstream_xchacha20poly1305_init_push(dataKey);

	const buf = new Uint8Array(await file.arrayBuffer());
	const chunks: Uint8Array[] = [];
	for (let off = 0; off < buf.length || off === 0; off += STREAM_CHUNK) {
		const end = Math.min(off + STREAM_CHUNK, buf.length);
		const isLast = end >= buf.length;
		const tag = isLast
			? s.crypto_secretstream_xchacha20poly1305_TAG_FINAL
			: s.crypto_secretstream_xchacha20poly1305_TAG_MESSAGE;
		chunks.push(
			s.crypto_secretstream_xchacha20poly1305_push(init.state, buf.slice(off, end), null, tag)
		);
		onProgress?.(buf.length === 0 ? 1 : end / buf.length);
		if (isLast) break;
	}

	let total = 0;
	for (const c of chunks) total += c.length + 4;
	const ciphertext = new Uint8Array(total);
	const dv = new DataView(ciphertext.buffer);
	let pos = 0;
	for (const c of chunks) {
		dv.setUint32(pos, c.length);
		pos += 4;
		ciphertext.set(c, pos);
		pos += c.length;
	}

	// Seal the data key under the master key.
	const nonce = s.randombytes_buf(s.crypto_secretbox_NONCEBYTES);
	const keyWrapped = s.crypto_secretbox_easy(dataKey, nonce, masterKey());

	return {
		ciphertext,
		mime: file.type || 'image/jpeg',
		keyWrapped: b64encode(s, keyWrapped),
		nonceWrapped: b64encode(s, nonce),
		header: b64encode(s, init.header)
	};
}

export async function hashCiphertext(ciphertext: Uint8Array): Promise<string> {
	const s = await sodiumReady();
	return sha256Hex(s, ciphertext);
}

// Encryption material as stored/returned by the backend for one image.
export interface ImageCrypto {
	key_wrapped: string;
	nonce_wrapped: string;
	header: string;
}

// Decrypt an already-downloaded ciphertext blob back to a typed Blob.
export async function decryptImage(
	ciphertext: Uint8Array,
	crypto_: ImageCrypto,
	mime: string
): Promise<Blob> {
	const s = await sodiumReady();
	// Unwrap the per-image data key with the master key.
	const dataKey = s.crypto_secretbox_open_easy(
		b64decode(s, crypto_.key_wrapped),
		b64decode(s, crypto_.nonce_wrapped),
		masterKey()
	);
	const state = s.crypto_secretstream_xchacha20poly1305_init_pull(
		b64decode(s, crypto_.header),
		dataKey
	);
	const dv = new DataView(ciphertext.buffer, ciphertext.byteOffset, ciphertext.byteLength);
	const out: Uint8Array[] = [];
	let pos = 0;
	while (pos < ciphertext.length) {
		const len = dv.getUint32(pos);
		pos += 4;
		const chunk = ciphertext.slice(pos, pos + len);
		pos += len;
		const r = s.crypto_secretstream_xchacha20poly1305_pull(state, chunk, null);
		if (!r) throw new Error('calendar image decrypt failed (wrong key or corrupt blob)');
		out.push(r.message);
	}
	let n = 0;
	for (const p of out) n += p.length;
	const joined = new Uint8Array(n);
	let o = 0;
	for (const p of out) {
		joined.set(p, o);
		o += p.length;
	}
	return new Blob([joined as BlobPart], { type: mime });
}

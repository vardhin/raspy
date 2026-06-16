// Reusable chunked AEAD (libsodium crypto_secretstream) for large media/files.
//
// The vault has had this inline since day one; dropbox + chat need the exact same
// thing (encrypt a file under a fresh data key → opaque ciphertext blob → content-
// addressed by SHA-256). Factored out here so all three share one implementation.
//
// Wire format: a sequence of [uint32 big-endian length][ciphertext chunk]. The
// secretstream header is returned separately (it isn't secret) and travels in the
// encrypted metadata so the reader can re-init the pull state.

import { sodiumReady, b64encode, b64decode, type Sodium } from './sodium';

const STREAM_CHUNK = 64 * 1024; // plaintext chunk size

export interface EncryptedStream {
	ciphertext: Uint8Array;
	key: string; // b64 per-blob data key
	header: string; // b64 secretstream header
}

export async function sha256Hex(data: Uint8Array): Promise<string> {
	const s = await sodiumReady();
	const digest = s.crypto_hash_sha256(data);
	return Array.from(digest)
		.map((b) => b.toString(16).padStart(2, '0'))
		.join('');
}

/** Encrypt raw bytes under a fresh random data key. Reports 0..1 progress. */
export async function encryptStream(
	plain: Uint8Array,
	onProgress?: (fraction: number) => void
): Promise<EncryptedStream> {
	const s = await sodiumReady();
	const dataKey = s.crypto_secretstream_xchacha20poly1305_keygen();
	const init = s.crypto_secretstream_xchacha20poly1305_init_push(dataKey);
	const header = init.header;
	const state = init.state;

	const chunks: Uint8Array[] = [];
	for (let off = 0; off < plain.length || off === 0; off += STREAM_CHUNK) {
		const end = Math.min(off + STREAM_CHUNK, plain.length);
		const isLast = end >= plain.length;
		const tag = isLast
			? s.crypto_secretstream_xchacha20poly1305_TAG_FINAL
			: s.crypto_secretstream_xchacha20poly1305_TAG_MESSAGE;
		chunks.push(
			s.crypto_secretstream_xchacha20poly1305_push(state, plain.slice(off, end), null, tag)
		);
		onProgress?.(plain.length === 0 ? 1 : end / plain.length);
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
	return { ciphertext, key: b64encode(s, dataKey), header: b64encode(s, header) };
}

/** Decrypt a length-framed secretstream ciphertext with its data key + header. */
export async function decryptStream(
	ciphertext: Uint8Array,
	keyB64: string,
	headerB64: string
): Promise<Uint8Array> {
	const s = await sodiumReady();
	const state = s.crypto_secretstream_xchacha20poly1305_init_pull(
		b64decode(s, headerB64),
		b64decode(s, keyB64)
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
		if (!r) throw new Error('decrypt failed (wrong key or corrupt blob)');
		out.push(r.message);
	}
	return concat(out);
}

/** Read a streamed response body into one buffer, reporting 0..1 progress. */
export async function readBody(res: Response, onProgress?: (f: number) => void): Promise<Uint8Array> {
	const total = Number(res.headers.get('content-length') || 0);
	const reader = res.body!.getReader();
	const parts: Uint8Array[] = [];
	let got = 0;
	for (;;) {
		const { done, value } = await reader.read();
		if (done) break;
		parts.push(value);
		got += value.length;
		if (total) onProgress?.(got / total);
	}
	return concat(parts);
}

export function concat(parts: Uint8Array[]): Uint8Array {
	let n = 0;
	for (const p of parts) n += p.length;
	const out = new Uint8Array(n);
	let o = 0;
	for (const p of parts) {
		out.set(p, o);
		o += p.length;
	}
	return out;
}

// Re-export for callers that just want the sodium b64 helpers alongside streams.
export { b64encode, b64decode } from './sodium';
export type { Sodium };

// Vault crypto (Layer 2) — all in the client; the Pi never sees plaintext.
//
// Key hierarchy:
//   master_key (from password, kdf.ts) ──seals──▶ per-blob data keys + manifest
//
// Each file is encrypted with a fresh random data key using libsodium
// crypto_secretstream (chunked AEAD → supports large files/video + progress). The
// resulting CIPHERTEXT is content-addressed by SHA-256 and uploaded as an opaque
// blob. The blob's data key (+ header + metadata) is recorded in the manifest,
// which is itself encrypted under the master key with crypto_secretbox and stored
// as one opaque blob. So: lose the password ⇒ lose everything; the server holds
// only ciphertext it can't read.

import { sodiumReady, b64encode, b64decode, type Sodium } from './sodium';
import { auth } from '$lib/auth.svelte';
import { attUrl } from '$lib/api';

const STREAM_CHUNK = 64 * 1024; // plaintext chunk size for secretstream

export interface VaultEntry {
	hash: string; // SHA-256 of the ciphertext blob (its storage key)
	name: string;
	type: string; // MIME
	size: number; // plaintext size
	created: number;
	key: string; // b64 per-blob data key
	header: string; // b64 secretstream header
	parentId: string | null; // folder this file lives in; null = root
}

export interface VaultFolder {
	id: string; // random id, plaintext only inside the encrypted manifest
	name: string;
	parentId: string | null; // null = root
	created: number;
}

export interface Manifest {
	version: 2;
	folders: VaultFolder[];
	entries: VaultEntry[];
}

// Upgrade any older/looser manifest shape to the current v2 in memory. A v1
// manifest has no `folders` and entries without `parentId`; we default both so
// existing vaults open unchanged and get persisted as v2 on the next save.
export function normalizeManifest(raw: unknown): Manifest {
	const m = (raw ?? {}) as Partial<Manifest> & { entries?: VaultEntry[] };
	const entries = (m.entries ?? []).map((e) => ({ ...e, parentId: e.parentId ?? null }));
	const folders = (m.folders ?? []).map((f) => ({ ...f, parentId: f.parentId ?? null }));
	return { version: 2, folders, entries };
}

// All descendant folder ids of `rootId`, inclusive — used to delete a folder
// subtree (the folder, its subfolders, and their files) in one pass.
export function descendantIds(folders: VaultFolder[], rootId: string): Set<string> {
	const ids = new Set<string>([rootId]);
	let grew = true;
	while (grew) {
		grew = false;
		for (const f of folders) {
			if (f.parentId && ids.has(f.parentId) && !ids.has(f.id)) {
				ids.add(f.id);
				grew = true;
			}
		}
	}
	return ids;
}

function masterKey(): Uint8Array {
	const k = auth.masterKey;
	if (!k) throw new Error('vault locked: no master key (sign in with your password)');
	return k;
}

async function sha256Hex(s: Sodium, data: Uint8Array): Promise<string> {
	const digest = s.crypto_hash_sha256(data);
	return Array.from(digest)
		.map((b) => b.toString(16).padStart(2, '0'))
		.join('');
}

// --- manifest (one opaque encrypted blob) ------------------------------------

export async function loadManifest(): Promise<Manifest> {
	const res = await fetch(attUrl('vault', 'manifest'), { credentials: 'include' });
	if (res.status === 204) return normalizeManifest(null);
	if (!res.ok) throw new Error(`manifest load failed: ${res.status}`);
	const blob = new Uint8Array(await res.arrayBuffer());
	const s = await sodiumReady();
	// secretbox: nonce(24) || ciphertext
	const nonce = blob.slice(0, s.crypto_secretbox_NONCEBYTES);
	const ct = blob.slice(s.crypto_secretbox_NONCEBYTES);
	const plain = s.crypto_secretbox_open_easy(ct, nonce, masterKey());
	return normalizeManifest(JSON.parse(new TextDecoder().decode(plain)));
}

export async function saveManifest(manifest: Manifest): Promise<void> {
	const s = await sodiumReady();
	const plain = new TextEncoder().encode(JSON.stringify(manifest));
	const nonce = s.randombytes_buf(s.crypto_secretbox_NONCEBYTES);
	const ct = s.crypto_secretbox_easy(plain, nonce, masterKey());
	const blob = new Uint8Array([...nonce, ...ct]);
	const res = await fetch(attUrl('vault', 'manifest'), {
		method: 'PUT',
		credentials: 'include',
		headers: { 'content-type': 'application/octet-stream' },
		body: blob as BlobPart
	});
	if (!res.ok) throw new Error(`manifest save failed: ${res.status}`);
}

// --- encrypt + upload a file -------------------------------------------------

export async function encryptFile(
	file: File,
	parentId: string | null = null,
	onProgress?: (fraction: number) => void
): Promise<{ ciphertext: Uint8Array; entry: Omit<VaultEntry, 'hash'> }> {
	const s = await sodiumReady();
	const dataKey = s.crypto_secretstream_xchacha20poly1305_keygen();
	const init = s.crypto_secretstream_xchacha20poly1305_init_push(dataKey);
	const header = init.header;
	const state = init.state;

	const buf = new Uint8Array(await file.arrayBuffer());
	const chunks: Uint8Array[] = [];
	for (let off = 0; off < buf.length || off === 0; off += STREAM_CHUNK) {
		const end = Math.min(off + STREAM_CHUNK, buf.length);
		const isLast = end >= buf.length;
		const tag = isLast
			? s.crypto_secretstream_xchacha20poly1305_TAG_FINAL
			: s.crypto_secretstream_xchacha20poly1305_TAG_MESSAGE;
		const ct = s.crypto_secretstream_xchacha20poly1305_push(
			state,
			buf.slice(off, end),
			null,
			tag
		);
		chunks.push(ct);
		onProgress?.(buf.length === 0 ? 1 : end / buf.length);
		if (isLast) break;
	}
	// Frame each chunk with a 4-byte big-endian length so decrypt can re-split.
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

	return {
		ciphertext,
		entry: {
			name: file.name,
			type: file.type || 'application/octet-stream',
			size: file.size,
			created: Date.now() / 1000,
			key: b64encode(s, dataKey),
			header: b64encode(s, header),
			parentId
		}
	};
}

export async function uploadFile(
	file: File,
	parentId: string | null = null,
	onProgress?: (fraction: number) => void
): Promise<VaultEntry> {
	const s = await sodiumReady();
	const { ciphertext, entry } = await encryptFile(file, parentId, onProgress);
	const hash = await sha256Hex(s, ciphertext);
	// Content-addressed PUT. Bypasses Layer-1 channel (already E2E-encrypted).
	const res = await fetch(attUrl('vault', `blob/${hash}`), {
		method: 'PUT',
		credentials: 'include',
		headers: { 'content-type': 'application/octet-stream' },
		body: ciphertext as BlobPart
	});
	if (!res.ok) throw new Error(`blob upload failed: ${res.status}`);
	return { ...entry, hash };
}

// --- download + decrypt ------------------------------------------------------

export async function downloadAndDecrypt(
	entry: VaultEntry,
	onProgress?: (fraction: number) => void
): Promise<Blob> {
	const s = await sodiumReady();
	const res = await fetch(attUrl('vault', `blob/${entry.hash}`), { credentials: 'include' });
	if (!res.ok) throw new Error(`blob download failed: ${res.status}`);

	const totalBytes = Number(res.headers.get('content-length') || 0);
	const reader = res.body!.getReader();
	const received: Uint8Array[] = [];
	let got = 0;
	for (;;) {
		const { done, value } = await reader.read();
		if (done) break;
		received.push(value);
		got += value.length;
		if (totalBytes) onProgress?.(got / totalBytes);
	}
	const ciphertext = concat(received);

	// Re-split the length-framed secretstream chunks and decrypt.
	const state = s.crypto_secretstream_xchacha20poly1305_init_pull(
		b64decode(s, entry.header),
		b64decode(s, entry.key)
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
		if (!r) throw new Error('vault decrypt failed (wrong key or corrupt blob)');
		out.push(r.message);
	}
	return new Blob([concat(out) as BlobPart], { type: entry.type });
}

function concat(parts: Uint8Array[]): Uint8Array {
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

export async function deleteBlob(hash: string): Promise<void> {
	await fetch(attUrl('vault', `blob/${hash}`), { method: 'DELETE', credentials: 'include' });
}

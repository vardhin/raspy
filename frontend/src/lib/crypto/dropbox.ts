// Dropbox client logic — drop E2E-encrypted files onto another account, and read
// what's been dropped to you. The cross-account sibling of vault.ts.
//
// Send: encrypt the file under a fresh data key (stream.ts) → ciphertext blob,
// build a metadata header {name,type,size,key,header}, SEAL it to the recipient's
// public key (identity.ts), and POST blob + sealed header. The server delivers
// both into the recipient's isolated dropbox.
//
// Receive: list items, open each item's sealed header with our own keypair to get
// the data key + name/type, then download + decrypt the blob on demand.

import { attUrl } from '$lib/api';
import { auth } from '$lib/auth.svelte';
import { csrfToken } from '$lib/auth.svelte';
import { sealTo, sealOpen, type Keypair } from './identity';
import { b64encode, b64decode, encryptStream, decryptStream, readBody, sha256Hex } from './stream';
import { sodiumReady } from './sodium';

export type DropSource = 'drop' | 'chat';

/** The plaintext metadata header, sealed to the recipient before upload. */
export interface DropMeta {
	name: string;
	type: string; // MIME
	size: number; // plaintext size
	key: string; // b64 stream data key
	header: string; // b64 stream header
}

/** A received item as the server lists it (sealed_meta still encrypted). */
export interface DropItem {
	id: number;
	from: string;
	source: DropSource;
	hash: string;
	size: number;
	sealed_meta: string;
	created: number;
}

/** A received item after we open its sealed header with our keypair. */
export interface OpenedDrop extends DropItem {
	meta: DropMeta | null; // null if we can't open it (not sealed to us)
}

function headers(json = true): Record<string, string> {
	const t = csrfToken();
	return {
		...(json ? { 'content-type': 'application/json' } : {}),
		...(t ? { 'x-csrf-token': t } : {})
	};
}

/**
 * Encrypt a file and drop it onto ``to``. Returns the created item.
 * ``recipientPublicKey`` is the recipient's b64 X25519 public key (from the
 * directory). The blob is content-addressed; the metadata (incl. the data key) is
 * sealed so only the recipient can decrypt.
 */
export async function sendFile(
	to: string,
	recipientPublicKey: string,
	file: File,
	source: DropSource = 'drop',
	onProgress?: (fraction: number) => void
): Promise<DropItem> {
	const s = await sodiumReady();
	const plain = new Uint8Array(await file.arrayBuffer());
	const enc = await encryptStream(plain, onProgress);
	const meta: DropMeta = {
		name: file.name,
		type: file.type || 'application/octet-stream',
		size: file.size,
		key: enc.key,
		header: enc.header
	};
	const sealed = await sealTo(
		recipientPublicKey,
		new TextEncoder().encode(JSON.stringify(meta))
	);
	const form = new FormData();
	form.append('to', to);
	form.append('source', source);
	form.append('sealed_meta', b64encode(s, sealed));
	form.append('file', new Blob([enc.ciphertext as BlobPart]), 'blob');

	const res = await fetch(attUrl('dropbox', 'send'), {
		method: 'POST',
		credentials: 'include',
		headers: headers(false),
		body: form
	});
	if (!res.ok) throw new Error(`drop failed: ${res.status}`);
	return (await res.json()) as DropItem;
}

/**
 * Lower-level: drop an already-encrypted stream. Used by chat so it can reuse the
 * SAME ciphertext (one encryption) when delivering media to several scopes.
 */
export async function sendEncrypted(
	to: string,
	recipientPublicKey: string,
	ciphertext: Uint8Array,
	meta: DropMeta,
	source: DropSource = 'drop'
): Promise<DropItem> {
	const s = await sodiumReady();
	const sealed = await sealTo(
		recipientPublicKey,
		new TextEncoder().encode(JSON.stringify(meta))
	);
	const form = new FormData();
	form.append('to', to);
	form.append('source', source);
	form.append('sealed_meta', b64encode(s, sealed));
	form.append('file', new Blob([ciphertext as BlobPart]), 'blob');
	const res = await fetch(attUrl('dropbox', 'send'), {
		method: 'POST',
		credentials: 'include',
		headers: headers(false),
		body: form
	});
	if (!res.ok) throw new Error(`drop failed: ${res.status}`);
	return (await res.json()) as DropItem;
}

function keypair(): Keypair {
	const kp = auth.keypair;
	if (!kp) throw new Error('identity not ready (unlock the vault)');
	return kp;
}

/** Open an item's sealed metadata with our keypair. null if not addressed to us. */
export async function openMeta(item: DropItem): Promise<DropMeta | null> {
	const s = await sodiumReady();
	const plain = await sealOpen(keypair(), b64decode(s, item.sealed_meta));
	if (!plain) return null;
	try {
		return JSON.parse(new TextDecoder().decode(plain)) as DropMeta;
	} catch {
		return null;
	}
}

/** My inbox, paginated (newest first). Optional ``from`` filters to one sender.
 *  Each returned item is opened (sealed metadata decrypted) so the caller can
 *  search by filename / show name + type. */
export async function listItems(
	from?: string,
	limit = 50,
	offset = 0
): Promise<OpenedDrop[]> {
	const params = new URLSearchParams({ limit: String(limit), offset: String(offset) });
	if (from) params.set('from', from);
	const res = await fetch(attUrl('dropbox', `items?${params}`), { credentials: 'include' });
	if (!res.ok) throw new Error(`dropbox list failed: ${res.status}`);
	const items = (await res.json()) as DropItem[];
	return Promise.all(items.map(async (it) => ({ ...it, meta: await openMeta(it) })));
}

export interface Sender {
	from: string;
	count: number;
	last: number;
}

/** Distinct accounts that have dropped to me, for the filter bar. */
export async function listSenders(): Promise<Sender[]> {
	const res = await fetch(attUrl('dropbox', 'senders'), { credentials: 'include' });
	if (!res.ok) throw new Error(`dropbox senders failed: ${res.status}`);
	return (await res.json()) as Sender[];
}

/** Download + decrypt one received item into a Blob (for preview/download). */
export async function downloadAndDecrypt(
	item: OpenedDrop | DropItem,
	meta: DropMeta,
	onProgress?: (fraction: number) => void
): Promise<Blob> {
	const res = await fetch(attUrl('dropbox', `blob/${item.hash}`), { credentials: 'include' });
	if (!res.ok) throw new Error(`blob download failed: ${res.status}`);
	const ciphertext = await readBody(res, onProgress);
	const plain = await decryptStream(ciphertext, meta.key, meta.header);
	return new Blob([plain as BlobPart], { type: meta.type });
}

export async function deleteItem(id: number): Promise<void> {
	await fetch(attUrl('dropbox', `item/${id}`), {
		method: 'DELETE',
		credentials: 'include',
		headers: headers()
	});
}

/** Encrypt a file once and return the reusable ciphertext + meta (no upload). */
export async function encryptForDrop(
	file: File,
	onProgress?: (fraction: number) => void
): Promise<{ ciphertext: Uint8Array; hash: string; meta: DropMeta }> {
	const plain = new Uint8Array(await file.arrayBuffer());
	const enc = await encryptStream(plain, onProgress);
	const hash = await sha256Hex(enc.ciphertext);
	return {
		ciphertext: enc.ciphertext,
		hash,
		meta: {
			name: file.name,
			type: file.type || 'application/octet-stream',
			size: file.size,
			key: enc.key,
			header: enc.header
		}
	};
}

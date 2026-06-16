// Chat client logic — E2E messages + media between two accounts.
//
// A message payload is a small JSON object:
//   { text?: string, media?: MediaRef[] }
// sealed TWICE by the sender: once to the recipient's public key and once to the
// sender's own, so each side stores a copy it can open. The Pi never sees text.
//
// Media bytes are NOT carried in the message: each image is encrypted once and
// delivered through the dropbox (source='chat') to BOTH the recipient and the
// sender, so the media also lands in each one's drop box (your requirement). The
// MediaRef in the payload records {hash,key,header,...} so the conversation view
// can pull the ciphertext from the dropbox blob endpoint and decrypt it inline.

import { attUrl } from '$lib/api';
import { auth } from '$lib/auth.svelte';
import { csrfToken } from '$lib/auth.svelte';
import { sealTo, sealOpen, type Keypair } from './identity';
import { b64encode, b64decode, decryptStream, readBody } from './stream';
import { sodiumReady } from './sodium';
import { encryptForDrop, sendEncrypted, type DropMeta } from './dropbox';

/** A reference to one encrypted media blob delivered via the dropbox. */
export interface MediaRef {
	hash: string; // dropbox blob hash (content-addressed ciphertext)
	name: string;
	type: string; // MIME
	size: number; // plaintext size
	key: string; // b64 stream data key
	header: string; // b64 stream header
}

export interface MessagePayload {
	text?: string;
	media?: MediaRef[];
}

/** A message row as the server returns it (sealed still encrypted). */
export interface ChatMessage {
	id: number;
	kind: 'text' | 'media';
	sealed: string;
	from: string;
	mine: boolean;
	created: number;
}

/** A message after we open its sealed payload with our keypair. */
export interface OpenedMessage extends ChatMessage {
	payload: MessagePayload | null;
}

export interface Thread {
	peer: string;
	last: { kind: string; sealed: string; mine: boolean; created: number };
}

export interface OpenedThread extends Thread {
	preview: string; // decrypted one-line preview
}

function headers(): Record<string, string> {
	const t = csrfToken();
	return { 'content-type': 'application/json', ...(t ? { 'x-csrf-token': t } : {}) };
}

function keypair(): Keypair {
	const kp = auth.keypair;
	if (!kp) throw new Error('identity not ready (unlock the vault)');
	return kp;
}

function myPublicKeyB64(s: import('./sodium').Sodium): string {
	return b64encode(s, keypair().publicKey);
}

async function sealPayload(payload: MessagePayload, recipientPublicKey: string): Promise<string> {
	const s = await sodiumReady();
	const bytes = new TextEncoder().encode(JSON.stringify(payload));
	return b64encode(s, await sealTo(recipientPublicKey, bytes));
}

/**
 * Send a message to ``to``. ``files`` are encrypted, delivered to both parties'
 * dropboxes (source='chat'), and referenced in the sealed payload. Returns my own
 * opened copy for an immediate optimistic render.
 */
export async function sendMessage(
	to: string,
	recipientPublicKey: string,
	text: string,
	files: File[] = [],
	onProgress?: (fraction: number) => void
): Promise<OpenedMessage> {
	const s = await sodiumReady();
	const myPk = myPublicKeyB64(s);

	const media: MediaRef[] = [];
	for (let i = 0; i < files.length; i++) {
		const file = files[i];
		// Encrypt once; reuse the SAME ciphertext for both deliveries.
		const { ciphertext, hash, meta } = await encryptForDrop(file, (f) =>
			onProgress?.((i + f) / Math.max(files.length, 1))
		);
		const dropMeta: DropMeta = meta;
		// Deliver to the recipient's dropbox (sealed to them)...
		await sendEncrypted(to, recipientPublicKey, ciphertext, dropMeta, 'chat');
		// ...and to my own dropbox (sealed to me), so my drop box shows it too.
		await sendEncrypted(auth.username!, myPk, ciphertext, dropMeta, 'chat');
		media.push({
			hash,
			name: meta.name,
			type: meta.type,
			size: meta.size,
			key: meta.key,
			header: meta.header
		});
	}

	const payload: MessagePayload = {};
	if (text.trim()) payload.text = text;
	if (media.length) payload.media = media;
	const kind = media.length ? 'media' : 'text';

	const res = await fetch(attUrl('chat', 'send'), {
		method: 'POST',
		credentials: 'include',
		headers: headers(),
		body: JSON.stringify({
			to,
			kind,
			sealed_for_recipient: await sealPayload(payload, recipientPublicKey),
			sealed_for_self: await sealPayload(payload, myPk)
		})
	});
	if (!res.ok) throw new Error(`chat send failed: ${res.status}`);
	const row = (await res.json()) as ChatMessage;
	return { ...row, payload };
}

async function openMessage(msg: ChatMessage): Promise<OpenedMessage> {
	const s = await sodiumReady();
	const plain = await sealOpen(keypair(), b64decode(s, msg.sealed));
	let payload: MessagePayload | null = null;
	if (plain) {
		try {
			payload = JSON.parse(new TextDecoder().decode(plain)) as MessagePayload;
		} catch {
			payload = null;
		}
	}
	return { ...msg, payload };
}

/** All messages with ``peer``, oldest first, decrypted. */
export async function loadConversation(peer: string): Promise<OpenedMessage[]> {
	const res = await fetch(attUrl('chat', `conversation?with=${encodeURIComponent(peer)}`), {
		credentials: 'include'
	});
	if (!res.ok) throw new Error(`conversation load failed: ${res.status}`);
	const rows = (await res.json()) as ChatMessage[];
	return Promise.all(rows.map(openMessage));
}

/** Thread list with a decrypted one-line preview each. */
export async function loadThreads(): Promise<OpenedThread[]> {
	const res = await fetch(attUrl('chat', 'threads'), { credentials: 'include' });
	if (!res.ok) throw new Error(`threads load failed: ${res.status}`);
	const threads = (await res.json()) as Thread[];
	const s = await sodiumReady();
	return Promise.all(
		threads.map(async (t) => {
			let preview = '';
			const plain = await sealOpen(keypair(), b64decode(s, t.last.sealed));
			if (plain) {
				try {
					const p = JSON.parse(new TextDecoder().decode(plain)) as MessagePayload;
					preview = p.text ?? (p.media?.length ? `📎 ${p.media.length} photo(s)` : '');
				} catch {
					preview = '';
				}
			}
			return { ...t, preview };
		})
	);
}

/** Download + decrypt one media ref (from the dropbox blob store) into a Blob. */
export async function loadMedia(ref: MediaRef, onProgress?: (f: number) => void): Promise<Blob> {
	const res = await fetch(attUrl('dropbox', `blob/${ref.hash}`), { credentials: 'include' });
	if (!res.ok) throw new Error(`media download failed: ${res.status}`);
	const ciphertext = await readBody(res, onProgress);
	const plain = await decryptStream(ciphertext, ref.key, ref.header);
	return new Blob([plain as BlobPart], { type: ref.type });
}

export async function clearConversation(peer: string): Promise<void> {
	await fetch(attUrl('chat', `conversation?with=${encodeURIComponent(peer)}`), {
		method: 'DELETE',
		credentials: 'include',
		headers: headers()
	});
}

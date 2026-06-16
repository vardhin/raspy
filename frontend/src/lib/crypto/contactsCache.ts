// Decrypted-blob cache for contact photos. Same scheme as the calendar's cache
// (keyed by ciphertext hash, bounded LRU of object URLs) but pointed at the
// contacts attachment's image endpoint. The encryption itself is shared with the
// calendar via `calendarMedia` (the zero-knowledge vault scheme) — only the
// attachment id and its own cache instance differ.

import { attResourceUrl } from '$lib/api';
import { decryptImage, type ImageCrypto } from './calendarMedia';

const ID = 'contacts';
const MAX_ENTRIES = 24;

// One image to decrypt: its blob hash, mime, and the wrapped-key material.
export interface EncImage extends ImageCrypto {
	hash: string;
	mime: string;
}

interface CacheItem {
	url: string;
	used: number;
}

const cache = new Map<string, CacheItem>();
const inflight = new Map<string, Promise<string>>();
let tick = 0;

function evictIfNeeded(): void {
	while (cache.size > MAX_ENTRIES) {
		let oldestHash: string | null = null;
		let oldestUsed = Infinity;
		for (const [hash, item] of cache) {
			if (item.used < oldestUsed) {
				oldestUsed = item.used;
				oldestHash = hash;
			}
		}
		if (oldestHash === null) break;
		URL.revokeObjectURL(cache.get(oldestHash)!.url);
		cache.delete(oldestHash);
	}
}

async function fetchAndDecrypt(img: EncImage): Promise<string> {
	const res = await fetch(attResourceUrl(ID, `image/${img.hash}`, {}), {
		credentials: 'include'
	});
	if (!res.ok) throw new Error(`image fetch failed: ${res.status}`);
	const ciphertext = new Uint8Array(await res.arrayBuffer());
	const blob = await decryptImage(ciphertext, img, img.mime);
	return URL.createObjectURL(blob);
}

// Return a (cached) object URL for the decrypted image, decrypting on demand.
// Concurrent calls for the same hash share one in-flight decrypt.
export function get(img: EncImage): Promise<string> {
	const hit = cache.get(img.hash);
	if (hit) {
		hit.used = ++tick;
		return Promise.resolve(hit.url);
	}
	const pending = inflight.get(img.hash);
	if (pending) return pending;

	const p = fetchAndDecrypt(img)
		.then((url) => {
			cache.set(img.hash, { url, used: ++tick });
			evictIfNeeded();
			return url;
		})
		.finally(() => inflight.delete(img.hash));
	inflight.set(img.hash, p);
	return p;
}

// Revoke everything (vault lock / teardown).
export function clear(): void {
	for (const item of cache.values()) URL.revokeObjectURL(item.url);
	cache.clear();
	inflight.clear();
}

// Decrypted-blob cache for the vault carousel/preview. Keyed by ciphertext hash,
// it holds object URLs for already-decrypted blobs so flipping back to a media
// item (or revisiting it) is instant, and lets us prefetch+decrypt neighbours
// in the background. Bounded LRU so memory (and live object URLs) can't grow
// without limit.

import { downloadAndDecrypt, type VaultEntry } from './vault';

const MAX_ENTRIES = 15;

interface CacheItem {
	url: string;
	used: number; // monotonic tick for LRU eviction
}

const cache = new Map<string, CacheItem>();
const inflight = new Map<string, Promise<string>>();
let tick = 0;

function touch(item: CacheItem): void {
	item.used = ++tick;
}

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
		const victim = cache.get(oldestHash)!;
		URL.revokeObjectURL(victim.url);
		cache.delete(oldestHash);
	}
}

// Return a (cached) object URL for the decrypted blob, decrypting on demand.
// Concurrent calls for the same hash share one in-flight decrypt.
export function get(entry: VaultEntry, onProgress?: (f: number) => void): Promise<string> {
	const hit = cache.get(entry.hash);
	if (hit) {
		touch(hit);
		return Promise.resolve(hit.url);
	}
	const pending = inflight.get(entry.hash);
	if (pending) return pending;

	const p = downloadAndDecrypt(entry, onProgress)
		.then((blob) => {
			const url = URL.createObjectURL(blob);
			const item: CacheItem = { url, used: ++tick };
			cache.set(entry.hash, item);
			evictIfNeeded();
			return url;
		})
		.finally(() => {
			inflight.delete(entry.hash);
		});
	inflight.set(entry.hash, p);
	return p;
}

// Fire-and-forget decrypt of neighbours so navigation is seamless. Errors are
// swallowed — a failed prefetch just means that item decrypts on demand later.
export function prefetch(entries: VaultEntry[]): void {
	for (const e of entries) {
		if (cache.has(e.hash) || inflight.has(e.hash)) continue;
		void get(e).catch(() => {});
	}
}

// Revoke everything (vault lock / component teardown).
export function clear(): void {
	for (const item of cache.values()) URL.revokeObjectURL(item.url);
	cache.clear();
	inflight.clear();
}

// App-scoped decrypted-media cache.
//
// Decrypting media (download ciphertext + secretstream decrypt) is expensive, and
// Svelte re-renders a conversation/inbox list on every change (e.g. sending a new
// message reassigns the array), which would otherwise re-decrypt every visible
// image again and again — the flicker you saw in chat.
//
// This cache memoizes the decrypted result as an object URL keyed by the blob hash
// (content-addressed, so the key is stable and collision-free). A coalescing
// in-flight map ensures concurrent requests for the same blob decrypt only once.
//
// Lifetime: as long as the owning app (Chat or Dropbox) is mounted. The app calls
// clear() in onDestroy when you switch away, which revokes every object URL and
// frees the memory. So the cache lives exactly while the app is active.

type Loader = () => Promise<Blob>;

const urls = new Map<string, string>(); // hash -> object URL (decrypted)
const inflight = new Map<string, Promise<string>>(); // hash -> in-progress decrypt

/**
 * Return a ready-to-use object URL for the blob identified by `hash`, decrypting
 * via `load` only on the first request. Subsequent calls (including across
 * re-renders) return the cached URL instantly — no re-decrypt, no flicker.
 */
export async function getMediaUrl(hash: string, load: Loader): Promise<string> {
	const hit = urls.get(hash);
	if (hit) return hit;
	const pending = inflight.get(hash);
	if (pending) return pending;

	const p = (async () => {
		const blob = await load();
		const url = URL.createObjectURL(blob);
		urls.set(hash, url);
		inflight.delete(hash);
		return url;
	})().catch((e) => {
		inflight.delete(hash);
		throw e;
	});
	inflight.set(hash, p);
	return p;
}

/** Whether a decrypted URL is already cached (lets callers render instantly). */
export function peekMediaUrl(hash: string): string | undefined {
	return urls.get(hash);
}

/** Free everything — revokes all object URLs. Call from the app's onDestroy. */
export function clearMediaCache(): void {
	for (const url of urls.values()) URL.revokeObjectURL(url);
	urls.clear();
	inflight.clear();
}

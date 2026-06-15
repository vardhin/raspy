// Persists the UI manifest (app list + structure) across reloads via the shared
// IndexedDB kv store. On boot we render the cached copy instantly, then revalidate
// with If-None-Match: a 304 keeps the cache, a 200 swaps in the new structure.

import { kvGet, kvSet } from '$lib/kv';
import type { Manifest } from './types';

function keyFor(accountKey: string): string {
	return `manifest:${accountKey}`;
}

export interface CachedManifest {
	etag: string | null;
	manifest: Manifest;
}

export function readManifest(accountKey: string): Promise<CachedManifest | null> {
	return kvGet<CachedManifest>(keyFor(accountKey));
}

export function writeManifest(accountKey: string, entry: CachedManifest): Promise<void> {
	return kvSet(keyFor(accountKey), entry);
}

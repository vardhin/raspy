// Persists the UI manifest (app list + structure) across reloads via the shared
// IndexedDB kv store. On boot we render the cached copy instantly, then revalidate
// with If-None-Match: a 304 keeps the cache, a 200 swaps in the new structure.

import { kvGet, kvSet } from '$lib/kv';
import type { Manifest } from './types';

const KEY = 'manifest';

export interface CachedManifest {
	etag: string | null;
	manifest: Manifest;
}

export function readManifest(): Promise<CachedManifest | null> {
	return kvGet<CachedManifest>(KEY);
}

export function writeManifest(entry: CachedManifest): Promise<void> {
	return kvSet(KEY, entry);
}

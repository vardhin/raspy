// Reactive manifest: the list of apps + their UI structure, fetched once.
//
// Boot sequence:
//   1. load the IndexedDB-cached manifest (instant, no skeleton on repeat visits)
//   2. revalidate GET /api/manifest with If-None-Match (the ETag)
//      - 304: cache is current, nothing to do
//      - 200: replace cache + state with the fresh structure
// The whole thing is one small JSON, so this is cheap.

import { apiUrl } from '$lib/api';
import { readManifest, writeManifest } from './cache';
import type { AttachmentManifest, Manifest } from './types';

class ManifestStore {
	attachments = $state<AttachmentManifest[]>([]);
	version = $state<string | null>(null);
	/** true until the first source (cache or network) resolves. */
	loading = $state(true);
	/** set when there's no cache AND the network fetch failed. */
	error = $state<string | null>(null);

	#etag: string | null = null;
	#started = false;
	#accountKey = '';

	byId(id: string): AttachmentManifest | undefined {
		return this.attachments.find((a) => a.id === id);
	}

	#apply(manifest: Manifest): void {
		this.attachments = manifest.attachments;
		this.version = manifest.version;
	}

	async load(accountKey = 'default'): Promise<void> {
		if (this.#started && this.#accountKey === accountKey) return;
		this.#accountKey = accountKey;
		this.#started = true;
		this.#etag = null;
		this.attachments = [];
		this.version = null;
		this.loading = true;
		this.error = null;

		const cached = await readManifest(accountKey);
		if (cached) {
			this.#apply(cached.manifest);
			this.#etag = cached.etag;
			this.loading = false;
		}

		await this.revalidate();
		this.loading = false;
	}

	/** Re-fetch with the stored ETag; cheap no-op when unchanged. */
	async revalidate(): Promise<void> {
		try {
			const headers: Record<string, string> = { accept: 'application/json' };
			if (this.#etag) headers['if-none-match'] = this.#etag;

			const res = await fetch(apiUrl('/api/manifest'), { credentials: 'include', headers });
			if (res.status === 304) {
				this.error = null;
				return;
			}
			if (!res.ok) throw new Error(`HTTP ${res.status}`);

			const manifest: Manifest = await res.json();
			this.#etag = res.headers.get('etag');
			this.#apply(manifest);
			this.error = null;
			await writeManifest(this.#accountKey, { etag: this.#etag, manifest });
		} catch (e) {
			// Keep showing cache if we have one; only surface a hard error when empty.
			if (this.attachments.length === 0) {
				this.error = e instanceof Error ? e.message : 'failed to load apps';
			}
		}
	}
}

export const manifest = new ManifestStore();

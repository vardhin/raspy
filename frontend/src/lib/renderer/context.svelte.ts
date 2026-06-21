// Per-view render context: form input values, loaded list/table data sources,
// and the action runner. One instance lives per mounted app view and is passed
// down through Svelte context so any node can read inputs / trigger actions.

import { attAction, attGet } from '$lib/api';
import { connection } from '$lib/connection.svelte';
import { kvGet, kvSet } from '$lib/kv';
import type { Action } from '$lib/manifest/types';

export class RenderContext {
	readonly attachmentId: string;

	/** Form field values keyed by input `name`. */
	fields = $state<Record<string, unknown>>({});
	/** Loaded collections keyed by `source` path. */
	sources = $state<Record<string, unknown[]>>({});
	/** Per-source: true while the *first* load (with no cached rows) is in flight. */
	sourceLoading = $state<Record<string, boolean>>({});
	/** Per-source: true when showing cached rows because a refresh failed. */
	sourceStale = $state<Record<string, boolean>>({});

	#unsubEvent: (() => void) | null = null;
	#sourcePaths = new Set<string>();

	constructor(attachmentId: string) {
		this.attachmentId = attachmentId;
		// Live refresh: any backend event whose topic starts with this app's id
		// (e.g. "todo.updated") re-pulls every data source in the view.
		this.#unsubEvent = connection.onEvent((topic) => {
			if (topic.startsWith(`${attachmentId}.`)) this.refreshAll();
		});
	}

	destroy(): void {
		this.#unsubEvent?.();
		this.#unsubEvent = null;
	}

	setField(name: string, value: unknown): void {
		this.fields[name] = value;
	}

	/** True when any visible source is showing cached (possibly out-of-date) rows. */
	get stale(): boolean {
		return Object.values(this.sourceStale).some(Boolean);
	}

	#cacheKey(path: string): string {
		return `data:${this.attachmentId}:${path}`;
	}

	/**
	 * Register a data source (called by List/Table on mount). Cache-first: paint
	 * last-known rows from IndexedDB immediately, then refresh in the background.
	 */
	async registerSource(path: string): Promise<void> {
		this.#sourcePaths.add(path);

		const cached = await kvGet<unknown[]>(this.#cacheKey(path));
		const hasCache = Array.isArray(cached);
		if (hasCache && this.sources[path] === undefined) {
			this.sources[path] = cached;
		}
		// Only show a spinner when there's nothing cached to paint.
		await this.loadSource(path, { silent: hasCache });
	}

	async loadSource(path: string, opts: { silent?: boolean } = {}): Promise<void> {
		const hadRows = Array.isArray(this.sources[path]);
		if (!opts.silent && !hadRows) this.sourceLoading[path] = true;
		try {
			const rows = await attGet<unknown[]>(this.attachmentId, path);
			const list = Array.isArray(rows) ? rows : [];
			this.sources[path] = list;
			this.sourceStale[path] = false;
			void kvSet(this.#cacheKey(path), list);
		} catch {
			// Keep whatever we have (cached rows); mark stale if we're showing them.
			this.sources[path] = this.sources[path] ?? [];
			this.sourceStale[path] = Array.isArray(this.sources[path]);
		} finally {
			this.sourceLoading[path] = false;
		}
	}

	refreshAll(): void {
		for (const path of this.#sourcePaths) void this.loadSource(path, { silent: true });
	}

	/**
	 * Resolve a `$field` placeholder or `{id}` row token in an action body/path.
	 * - "$title" -> current value of the `title` input
	 * - "{id}" in a path -> the row's id (passed via `row`)
	 */
	#resolveValue(v: unknown): unknown {
		if (typeof v === 'string' && v.startsWith('$')) {
			return this.fields[v.slice(1)] ?? '';
		}
		return v;
	}

	#resolveBody(body?: Record<string, unknown>): Record<string, unknown> | undefined {
		if (!body) return undefined;
		const out: Record<string, unknown> = {};
		for (const [k, v] of Object.entries(body)) out[k] = this.#resolveValue(v);
		return out;
	}

	#resolvePath(path: string, row?: Record<string, unknown>): string {
		return path.replace(/\{(\w+)\}/g, (_, k) => String(row?.[k] ?? ''));
	}

	/** Run a declarative action, then refresh sources (event will also fire). */
	async runAction(action: Action, row?: Record<string, unknown>): Promise<void> {
		const path = this.#resolvePath(action.path, row);
		const body = this.#resolveBody(action.body);
		await attAction(this.attachmentId, action.method, path, body);
		// Clear inputs referenced by the action body (typical create-form UX).
		if (action.body) {
			for (const v of Object.values(action.body)) {
				if (typeof v === 'string' && v.startsWith('$')) this.fields[v.slice(1)] = '';
			}
		}
		this.refreshAll();
	}

	/**
	 * Apply a drag-reorder of `source` to the given top-to-bottom order of row
	 * keys. Optimistic: reorder the local rows immediately (so the UI doesn't
	 * snap back while the request is in flight), then POST/PATCH the action with
	 * `{ order: [...] }`. On failure, reload from the server to resync.
	 */
	async runReorder(
		source: string,
		key: string,
		orderedKeys: unknown[],
		action: Action
	): Promise<void> {
		const rows = (this.sources[source] ?? []) as Record<string, unknown>[];
		const byKey = new Map(rows.map((r) => [String(r[key]), r]));
		const reordered = orderedKeys
			.map((k) => byKey.get(String(k)))
			.filter((r): r is Record<string, unknown> => r !== undefined);
		// Keep any rows not named in `orderedKeys` (e.g. a different visual band)
		// in their existing relative position, appended after the moved set.
		const moved = new Set(orderedKeys.map((k) => String(k)));
		for (const r of rows) if (!moved.has(String(r[key]))) reordered.push(r);
		this.sources[source] = reordered;
		void kvSet(this.#cacheKey(source), reordered);
		try {
			await attAction(this.attachmentId, action.method, action.path, {
				order: orderedKeys
			});
		} catch {
			// Server rejected the order — pull the truth back.
			await this.loadSource(source, { silent: true });
		}
	}
}

// (refreshAll already loads silently — actions never flash a spinner.)

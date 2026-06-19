// Self-update store. Mirrors the backend core/updater.py:
//   - listens for the live "update.available" WS event (instant banner),
//   - and can poll GET /api/update/status on demand,
//   - drives POST /api/update/apply when the user clicks "Update now".
//
// Admin-only on the backend; for a non-admin the status call 403s and we simply
// stay silent (available=false), so the banner never shows for them.

import { apiGet, apiPost } from '$lib/api';
import { connection } from '$lib/connection.svelte';

export interface UpdateStatus {
	current: string;
	current_tag?: string | null;
	latest: string | null;
	available: boolean;
	updatable: boolean;
	asset: string | null;
	reason?: string | null;
}

type Phase = 'idle' | 'checking' | 'applying' | 'restarting' | 'error';

/** Backend apply stages (update.progress events), in order. */
export type Step =
	| 'downloading'
	| 'downloaded'
	| 'verifying'
	| 'caching'
	| 'verified'
	| 'cached_hit'
	| 'swapping'
	| 'restarting'
	| 'error';

/** Human label per step, shown so the user sees exactly what's happening. */
export const STEP_LABEL: Record<Step, string> = {
	downloading: 'Downloading binary…',
	downloaded: 'Binary downloaded',
	verifying: 'Verifying checksum…',
	caching: 'Saving to cache…',
	verified: 'Verified & cached',
	cached_hit: 'Using cached binary',
	swapping: 'Swapping in new binary…',
	restarting: 'Restarting into new version…',
	error: 'Update failed'
};

/** Ordered steps for rendering a checklist (cached_hit collapses download+verify). */
export const STEP_ORDER: Step[] = [
	'downloading',
	'downloaded',
	'verifying',
	'caching',
	'verified',
	'swapping',
	'restarting'
];

class UpdateStore {
	current = $state<string | null>(null);
	currentTag = $state<string | null>(null);
	latest = $state<string | null>(null);
	available = $state(false);
	updatable = $state(false);
	phase = $state<Phase>('idle');
	error = $state<string | null>(null);
	/** The live apply step from update.progress, or null when not applying. */
	step = $state<Step | null>(null);
	/** The tag currently being applied (for the banner/progress label). */
	applyingTag = $state<string | null>(null);
	/** All steps seen during the current apply, so we can render a checklist. */
	stepsSeen = $state<Step[]>([]);
	/** User dismissed the banner for this version; don't re-show until a newer one. */
	#dismissed = $state<string | null>(null);

	#offEvent: (() => void) | null = null;
	#offProgress: (() => void) | null = null;
	#started = false;

	/** Show the banner only when there's an update the user hasn't dismissed. */
	get showBanner(): boolean {
		return this.available && !!this.latest && this.latest !== this.#dismissed;
	}

	start(): void {
		if (this.#started) return;
		this.#started = true;
		// Live push: the backend announces newer releases as they're noticed.
		this.#offEvent = connection.onEvent((topic, payload) => {
			if (topic !== 'update.available') return;
			const p = (payload ?? {}) as Partial<UpdateStatus>;
			this.current = p.current ?? this.current;
			this.currentTag = p.current_tag ?? this.currentTag;
			this.latest = p.latest ?? this.latest;
			this.available = true;
			this.updatable = p.updatable ?? this.updatable;
		});
		// Live step-by-step progress during an apply (downloading → verifying →
		// caching → swapping → restarting). Lets the UI show exactly what's
		// happening in the backend, on this tab or any other.
		this.#offProgress = connection.onEvent((topic, payload) => {
			if (topic !== 'update.progress') return;
			const p = (payload ?? {}) as { stage?: Step; tag?: string; error?: string };
			if (!p.stage) return;
			this.step = p.stage;
			if (p.tag) this.applyingTag = p.tag;
			if (p.stage !== 'error' && !this.stepsSeen.includes(p.stage)) {
				this.stepsSeen = [...this.stepsSeen, p.stage];
			}
			if (p.stage === 'error') {
				this.phase = 'error';
				this.error = p.error ?? 'update failed';
			} else if (p.stage === 'restarting') {
				this.phase = 'restarting';
			} else {
				this.phase = 'applying';
			}
		});
		// One status fetch on start so a banner appears even if the WS event fired
		// before this tab connected.
		void this.refresh();
	}

	stop(): void {
		this.#offEvent?.();
		this.#offEvent = null;
		this.#offProgress?.();
		this.#offProgress = null;
		this.#started = false;
	}

	async refresh(): Promise<void> {
		this.phase = 'checking';
		try {
			const s = await apiGet<UpdateStatus>('/api/update/status');
			this.#apply(s);
			this.phase = 'idle';
		} catch {
			// Non-admin (403) or offline — keep quiet.
			this.phase = 'idle';
		}
	}

	#apply(s: UpdateStatus): void {
		this.current = s.current;
		this.currentTag = s.current_tag ?? this.currentTag;
		this.latest = s.latest;
		this.available = s.available;
		this.updatable = s.updatable;
	}

	/** Best label for what's installed: the recorded tag (truth) over the binary's
	 *  baked-in version, which can be stale if a release forgot to bump it. */
	get currentLabel(): string {
		if (this.currentTag) return this.currentTag.replace(/^v/, '');
		return this.current ?? '—';
	}

	dismiss(): void {
		this.#dismissed = this.latest;
	}

	/** Download + verify + swap + restart. On success the spine restarts; we show
	 *  a "restarting" state and let connection.svelte flip offline→online.
	 *  `target` is an optional release tag to install a specific version (rollback
	 *  or any version); omit it to install the latest available update. */
	async apply(target?: string): Promise<void> {
		if (this.phase === 'applying' || this.phase === 'restarting') return;
		this.phase = 'applying';
		this.error = null;
		this.step = null;
		this.stepsSeen = [];
		this.applyingTag = target ?? this.latest ?? null;
		try {
			const res = await apiPost<{ ok: boolean; error?: string; restarting?: boolean }>(
				'/api/update/apply',
				target ? { target } : undefined
			);
			if (res.ok) {
				this.phase = 'restarting';
				// The backend goes down ~now; the connection store will show offline
				// and reconnect when the new binary is up.
			} else {
				this.error = res.error ?? 'update failed';
				this.phase = 'error';
			}
		} catch (e) {
			// A dropped connection mid-apply is EXPECTED (the server restarted), so
			// treat a network error after the request as "restarting", not failure.
			this.error = (e as Error)?.message ?? 'update failed';
			this.phase = 'restarting';
		}
	}
}

export const update = new UpdateStore();

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
	latest: string | null;
	available: boolean;
	updatable: boolean;
	asset: string | null;
	reason?: string | null;
}

type Phase = 'idle' | 'checking' | 'applying' | 'restarting' | 'error';

class UpdateStore {
	current = $state<string | null>(null);
	latest = $state<string | null>(null);
	available = $state(false);
	updatable = $state(false);
	phase = $state<Phase>('idle');
	error = $state<string | null>(null);
	/** User dismissed the banner for this version; don't re-show until a newer one. */
	#dismissed = $state<string | null>(null);

	#offEvent: (() => void) | null = null;
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
			this.latest = p.latest ?? this.latest;
			this.available = true;
			this.updatable = p.updatable ?? this.updatable;
		});
		// One status fetch on start so a banner appears even if the WS event fired
		// before this tab connected.
		void this.refresh();
	}

	stop(): void {
		this.#offEvent?.();
		this.#offEvent = null;
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
		this.latest = s.latest;
		this.available = s.available;
		this.updatable = s.updatable;
	}

	dismiss(): void {
		this.#dismissed = this.latest;
	}

	/** Download + verify + swap + restart. On success the spine restarts; we show
	 *  a "restarting" state and let connection.svelte flip offline→online. */
	async apply(): Promise<void> {
		if (this.phase === 'applying' || this.phase === 'restarting') return;
		this.phase = 'applying';
		this.error = null;
		try {
			const res = await apiPost<{ ok: boolean; error?: string; restarting?: boolean }>(
				'/api/update/apply'
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

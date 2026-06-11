// Shared live system-stats store. Subscribes once to `stats.tick` WebSocket
// events and holds the latest Pi snapshot, so both the dashboard summary strip
// and the full System page read the same reactive source.
//
// The stats attachment's id is "stats"; if it isn't installed, `latest` stays
// null and consumers simply render nothing.

import { connection } from '$lib/connection.svelte';
import { attGet } from '$lib/api';

export interface Throttle {
	raw: string;
	ok: boolean;
	flags: Record<string, boolean>;
	active: string[];
	occurred: string[];
}
export interface Mem {
	total: number;
	available: number;
	used: number;
	percent: number;
	swap_total: number;
	swap_used: number;
}
export interface Disk {
	mount: string;
	total: number;
	used: number;
	free: number;
	percent: number;
}
export interface Snapshot {
	time: number;
	model: string | null;
	uptime: number | null;
	temp_c: number | null;
	voltage_v: number | null;
	arm_hz: number | null;
	throttle: Throttle | null;
	cpu_percent: number | null;
	cpu_count: number;
	load: number[] | null;
	memory: Mem | null;
	storage: Disk[];
}

const ATT_ID = 'stats';

class StatsStore {
	latest = $state<Snapshot | null>(null);
	#started = false;
	#off: (() => void) | null = null;

	/** Begin listening for live ticks (idempotent). Optionally fetch one now. */
	start(fetchNow = false): void {
		if (this.#started) {
			if (fetchNow) void this.refresh();
			return;
		}
		this.#started = true;
		this.#off = connection.onEvent((topic, payload) => {
			if (topic === 'stats.tick' && payload) this.latest = payload as Snapshot;
		});
		if (fetchNow) void this.refresh();
	}

	stop(): void {
		this.#off?.();
		this.#off = null;
		this.#started = false;
	}

	async refresh(): Promise<void> {
		try {
			this.latest = await attGet<Snapshot>(ATT_ID, 'snapshot');
		} catch {
			// Stats attachment may be absent or backend down; leave latest as-is.
		}
	}
}

export const stats = new StatsStore();

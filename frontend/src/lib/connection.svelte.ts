// Live connection signals to the spine backend.
//
// Two independent channels are tracked so the UI can show *which* part of the
// link is up:
//   - HTTP: periodic GET /api/healthz (gives version + attachment counts)
//   - WS:   the /api/ws event hub (gives a live push channel + event count)
//
// Base URL: same-origin in production (the spine serves this bundle), but in dev
// the Vite server (5173) and the spine (49317) are different origins, so allow an
// override via PUBLIC_API_BASE. See plan/40-frontend.md.

import { browser } from '$app/environment';
import { apiUrl, wsUrl } from '$lib/api';
import { channel } from '$lib/crypto/channel';

export type LinkState = 'connecting' | 'online' | 'offline';

/** Optional callback fired each time the WS (re)connects — used to revalidate. */
export type ReconnectHook = () => void;

interface HealthPayload {
	ok: boolean;
	version: string;
	attachments: {
		loaded?: Array<{ id: string; version: string; source: string }>;
		errored?: Array<{ id: string; error?: string }>;
	};
	events: { subscribers: number };
}

const POLL_MS = 5000;
const WS_RETRY_MS = 3000;

class Connection {
	/** HTTP health channel. */
	http = $state<LinkState>('connecting');
	/** WebSocket event-hub channel. */
	ws = $state<LinkState>('connecting');

	version = $state<string | null>(null);
	attachmentCount = $state(0);
	erroredCount = $state(0);
	/** Events received over the WS since connect. */
	eventCount = $state(0);
	lastPingAt = $state<number | null>(null);

	#pollTimer: ReturnType<typeof setInterval> | null = null;
	#wsRetryTimer: ReturnType<typeof setTimeout> | null = null;
	#socket: WebSocket | null = null;
	#started = false;
	#hadConnection = false;
	#reconnectHooks = new Set<ReconnectHook>();
	#eventHooks = new Set<(topic: string, payload: unknown) => void>();

	/** True only when both channels are up. */
	get online(): boolean {
		return this.http === 'online' && this.ws === 'online';
	}

	/** Subscribe to WS reconnects (after a prior drop). Returns an unsubscribe fn. */
	onReconnect(fn: ReconnectHook): () => void {
		this.#reconnectHooks.add(fn);
		return () => this.#reconnectHooks.delete(fn);
	}

	/** Subscribe to backend events pushed over the WS. Returns an unsubscribe fn. */
	onEvent(fn: (topic: string, payload: unknown) => void): () => void {
		this.#eventHooks.add(fn);
		return () => this.#eventHooks.delete(fn);
	}

	start(): void {
		if (!browser || this.#started) return;
		this.#started = true;
		this.#poll();
		this.#pollTimer = setInterval(() => this.#poll(), POLL_MS);
		this.#openSocket();
		// Re-check immediately when the tab regains focus / network returns.
		window.addEventListener('online', this.#onNetUp);
		document.addEventListener('visibilitychange', this.#onVisible);
	}

	stop(): void {
		if (this.#pollTimer) clearInterval(this.#pollTimer);
		if (this.#wsRetryTimer) clearTimeout(this.#wsRetryTimer);
		this.#pollTimer = null;
		this.#wsRetryTimer = null;
		this.#socket?.close();
		this.#socket = null;
		this.#started = false;
		if (browser) {
			window.removeEventListener('online', this.#onNetUp);
			document.removeEventListener('visibilitychange', this.#onVisible);
		}
	}

	#onNetUp = () => this.#poll();
	#onVisible = () => {
		if (document.visibilityState === 'visible') this.#poll();
	};

	async #poll(): Promise<void> {
		try {
			const res = await fetch(apiUrl('/api/healthz'), {
				credentials: 'include',
				headers: { accept: 'application/json' }
			});
			if (!res.ok) throw new Error(`HTTP ${res.status}`);
			const data: HealthPayload = await res.json();
			this.http = 'online';
			this.version = data.version;
			this.attachmentCount = data.attachments?.loaded?.length ?? 0;
			this.erroredCount = data.attachments?.errored?.length ?? 0;
			this.lastPingAt = Date.now();
		} catch {
			this.http = 'offline';
			this.version = null;
		}
	}

	#openSocket(): void {
		if (!browser || !this.#started) return;
		// Never run two sockets at once — a leftover one would keep flipping state.
		if (this.#socket && this.#socket.readyState <= WebSocket.OPEN) return;
		this.ws = 'connecting';
		// Establish the Layer-1 channel first so we can pass its session id and
		// receive sealed frames. If it fails (no key on the Pi), connect plainly.
		void channel
			.ensure()
			.catch(() => {})
			.then(() => this.#connectSocket());
	}

	#connectSocket(): void {
		if (!browser || !this.#started) return;
		if (this.#socket && this.#socket.readyState <= WebSocket.OPEN) return;
		const sid = channel.sessionId;
		const path = sid ? `/api/ws?channel=${encodeURIComponent(sid)}` : '/api/ws';
		let socket: WebSocket;
		try {
			socket = new WebSocket(wsUrl(path));
		} catch {
			this.ws = 'offline';
			this.#scheduleWsRetry();
			return;
		}
		this.#socket = socket;

		socket.addEventListener('open', () => {
			this.ws = 'online';
			// Fire reconnect hooks only on a *re*connect, not the first connect —
			// the initial load already fetched fresh data.
			if (this.#hadConnection) {
				for (const fn of this.#reconnectHooks) fn();
			}
			this.#hadConnection = true;
		});
		socket.addEventListener('message', (ev) => {
			this.eventCount += 1;
			void this.#handleFrame(ev.data);
		});
		socket.addEventListener('close', () => {
			if (this.#socket === socket) {
				this.ws = 'offline';
				this.#socket = null;
				this.#scheduleWsRetry();
			}
		});
		socket.addEventListener('error', () => {
			// 'close' fires after 'error'; let it handle retry.
			socket.close();
		});
	}

	/** Parse an inbound WS frame, transparently opening sealed (Layer-1) frames. */
	async #handleFrame(data: string): Promise<void> {
		let msg: { type?: string; topic?: string; payload?: unknown };
		try {
			msg = JSON.parse(data);
		} catch {
			return;
		}
		if (msg.type === 'sealed' && typeof msg.payload === 'string') {
			try {
				const plain = await channel.open(msg.payload);
				msg = JSON.parse(new TextDecoder().decode(plain));
			} catch {
				return; // can't open — drop
			}
		}
		if (msg.type === 'event' && typeof msg.topic === 'string') {
			for (const fn of this.#eventHooks) fn(msg.topic, msg.payload);
		}
	}

	#scheduleWsRetry(): void {
		if (this.#wsRetryTimer || !this.#started) return;
		this.#wsRetryTimer = setTimeout(() => {
			this.#wsRetryTimer = null;
			this.#openSocket();
		}, WS_RETRY_MS);
	}
}

export const connection = new Connection();

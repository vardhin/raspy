// Notifications client. Two delivery paths, one store:
//
//   Foreground — while a tab is open & connected, the spine pushes a
//     `notification.new` event over the existing WebSocket (connection.onEvent).
//     We show it with the Notification API and keep an in-memory list.
//   Background — a service worker (static/sw.js) subscribed to Web Push shows
//     notifications even when no tab is open. Enabling that is opt-in: the user
//     grants permission, we register the SW and POST the push subscription to
//     /api/notifications/subscribe.
//
// History lives on the spine (SQLite); we fetch it for the bell panel and keep
// the unread count reactive. A future Flutter APK reuses the same /subscribe
// endpoint with kind="fcm" — none of the history/foreground code changes.

import { browser } from '$app/environment';
import { apiUrl } from '$lib/api';
import { connection } from '$lib/connection.svelte';

export interface Notification {
	id: number;
	source: string;
	title: string;
	body: string;
	icon: string | null;
	url: string | null;
	data: Record<string, unknown> | null;
	read: boolean;
	created: number;
}

export type PermissionState = 'default' | 'granted' | 'denied' | 'unsupported';

function urlBase64ToBuffer(base64: string): ArrayBuffer {
	const padding = '='.repeat((4 - (base64.length % 4)) % 4);
	const b64 = (base64 + padding).replace(/-/g, '+').replace(/_/g, '/');
	const raw = atob(b64);
	const buf = new ArrayBuffer(raw.length);
	const view = new Uint8Array(buf);
	for (let i = 0; i < raw.length; i++) view[i] = raw.charCodeAt(i);
	return buf;
}

class Notifications {
	items = $state<Notification[]>([]);
	unread = $state(0);
	/** OS-level Notification permission. */
	permission = $state<PermissionState>('default');
	/** True once a push subscription is active on this device. */
	pushEnabled = $state(false);

	#offEvent: (() => void) | null = null;
	#started = false;

	// --- cross-tab leader election -------------------------------------------
	// With the app open in several tabs, all of them receive the WS event. Only
	// ONE may raise an OS popup, or a hidden tab would notify while another is
	// focused. Tabs gossip over a BroadcastChannel and elect a leader (lowest id
	// wins); only the leader shows popups. Election re-runs when peers join/leave.
	readonly #tabId = Math.random().toString(36).slice(2) + Date.now().toString(36);
	#channel: BroadcastChannel | null = null;
	#peers = new Map<string, number>(); // peer id -> last-seen timestamp (ms)
	#heartbeat: ReturnType<typeof setInterval> | null = null;
	static readonly #PEER_TTL_MS = 8000;
	static readonly #HEARTBEAT_MS = 3000;

	start(): void {
		if (!browser || this.#started) return;
		this.#started = true;

		this.permission =
			'Notification' in window
				? (window.Notification.permission as PermissionState)
				: 'unsupported';

		// Foreground path + badge sync.
		//  - "notification.new": a brand-new notification — show the OS popup and
		//    bump the count.
		//  - "notifications.changed": any mutation (read/delete/clear), including
		//    actions taken on the /a/notifications page in another tab — re-pull
		//    the unread count so the sidebar badge stays correct.
		this.#offEvent = connection.onEvent((topic, payload) => {
			if (topic === 'notification.new') {
				const note = payload as Notification;
				this.#prepend(note);
				this.#showForeground(note);
			} else if (topic === 'notifications.changed') {
				void this.refreshUnread();
			}
		});

		this.#startElection();
		this.refresh();
		this.#syncPushState();
	}

	stop(): void {
		this.#offEvent?.();
		this.#offEvent = null;
		this.#stopElection();
		this.#started = false;
	}

	// --- leader election ------------------------------------------------------

	#startElection(): void {
		if (typeof BroadcastChannel === 'undefined') return; // single-tab fallback
		this.#channel = new BroadcastChannel('raspy-notify');
		this.#peers.set(this.#tabId, Date.now());

		this.#channel.onmessage = (ev: MessageEvent) => {
			const { type, id } = ev.data ?? {};
			if (!id || id === this.#tabId) return;
			if (type === 'hello' || type === 'ping') {
				this.#peers.set(id, Date.now());
				// A newcomer doesn't know about us yet — announce back so it can
				// elect correctly.
				if (type === 'hello') this.#post('ping');
			} else if (type === 'bye') {
				this.#peers.delete(id);
			}
		};

		// Leave cleanly so survivors re-elect without waiting for the TTL.
		window.addEventListener('pagehide', this.#onPageHide);

		this.#post('hello');
		this.#heartbeat = setInterval(() => {
			this.#post('ping');
			this.#prunePeers();
		}, Notifications.#HEARTBEAT_MS);
	}

	#stopElection(): void {
		this.#post('bye');
		if (this.#heartbeat) clearInterval(this.#heartbeat);
		this.#heartbeat = null;
		this.#channel?.close();
		this.#channel = null;
		this.#peers.clear();
		if (browser) window.removeEventListener('pagehide', this.#onPageHide);
	}

	#onPageHide = () => this.#post('bye');

	#post(type: 'hello' | 'ping' | 'bye'): void {
		this.#channel?.postMessage({ type, id: this.#tabId });
	}

	#prunePeers(): void {
		const cutoff = Date.now() - Notifications.#PEER_TTL_MS;
		for (const [id, seen] of this.#peers) {
			if (id !== this.#tabId && seen < cutoff) this.#peers.delete(id);
		}
	}

	/** This tab leads if it has the lowest id among live peers. */
	get #isLeader(): boolean {
		if (!this.#channel) return true; // no BroadcastChannel → we're the only tab
		this.#prunePeers();
		let min = this.#tabId;
		for (const id of this.#peers.keys()) if (id < min) min = id;
		return min === this.#tabId;
	}

	// --- badge state ----------------------------------------------------------
	// History display, mark-read, delete, clear and send-test all live on the
	// server-driven /a/notifications page (the notifications attachment). The
	// store only owns what the *shell chrome* needs: the unread count for the
	// sidebar badge, and a small recent set so we don't re-popup the same id.

	/** Full pull at boot / after reconnect: seeds the dedup set + unread count. */
	async refresh(): Promise<void> {
		try {
			const res = await fetch(apiUrl('/api/notifications?limit=50'), {
				headers: { accept: 'application/json' }
			});
			if (!res.ok) return;
			const data: { items: Notification[]; unread: number } = await res.json();
			this.items = data.items;
			this.unread = data.unread;
		} catch {
			// offline — keep whatever we have
		}
	}

	/** Lightweight: re-fetch just the unread count (on any mutation event). */
	async refreshUnread(): Promise<void> {
		try {
			const res = await fetch(apiUrl('/api/notifications?limit=1'), {
				headers: { accept: 'application/json' }
			});
			if (!res.ok) return;
			const data: { unread: number } = await res.json();
			this.unread = data.unread;
		} catch {
			// offline — leave the badge as-is
		}
	}

	#prepend(note: Notification): void {
		// Dedupe: the foreground event may arrive for a note we already have.
		if (this.items.some((n) => n.id === note.id)) return;
		this.items = [note, ...this.items].slice(0, 50);
		if (!note.read) this.unread += 1;
	}

	#showForeground(note: Notification): void {
		if (this.permission !== 'granted' || document.visibilityState === 'visible') return;
		// Only the elected leader tab raises the OS popup, so multiple open tabs
		// can't each notify. A focused tab elsewhere stays quiet either way (it's
		// `visible`), and non-leader hidden tabs defer to the leader.
		if (!this.#isLeader) return;
		// When the tab is hidden, surface an OS notification directly. (When it's
		// visible, the in-app bell is enough; avoid double-notifying.)
		try {
			new window.Notification(note.title, {
				body: note.body,
				icon: '/favicon.svg',
				tag: `raspy-${note.id}`
			});
		} catch {
			// some browsers require the SW path; ignore.
		}
	}

	// --- background push (opt-in) -------------------------------------------

	/** Request permission + register the service worker + subscribe to push. */
	async enablePush(): Promise<void> {
		if (!browser) return;
		if (!('Notification' in window) || !('serviceWorker' in navigator) || !('PushManager' in window)) {
			this.permission = 'unsupported';
			return;
		}

		const perm = await window.Notification.requestPermission();
		this.permission = perm as PermissionState;
		if (perm !== 'granted') return;

		const reg = await navigator.serviceWorker.register('/sw.js');
		await navigator.serviceWorker.ready;

		// Fetch the server's VAPID public key.
		const keyRes = await fetch(apiUrl('/api/notifications/vapid-key'));
		const { key } = (await keyRes.json()) as { key: string | null };
		if (!key) {
			// No VAPID configured on the spine — foreground still works.
			console.warn('Web Push unavailable: spine has no VAPID key configured.');
			return;
		}

		const sub = await reg.pushManager.subscribe({
			userVisibleOnly: true,
			applicationServerKey: urlBase64ToBuffer(key)
		});

		const json = sub.toJSON();
		await fetch(apiUrl('/api/notifications/subscribe'), {
			method: 'POST',
			headers: { 'content-type': 'application/json' },
			body: JSON.stringify({
				kind: 'webpush',
				endpoint: json.endpoint,
				keys: json.keys ?? {}
			})
		});
		this.pushEnabled = true;
	}

	async disablePush(): Promise<void> {
		if (!browser || !('serviceWorker' in navigator)) return;
		const reg = await navigator.serviceWorker.getRegistration();
		const sub = await reg?.pushManager.getSubscription();
		if (sub) {
			await fetch(apiUrl('/api/notifications/unsubscribe'), {
				method: 'POST',
				headers: { 'content-type': 'application/json' },
				body: JSON.stringify({ endpoint: sub.endpoint })
			}).catch(() => {});
			await sub.unsubscribe().catch(() => {});
		}
		this.pushEnabled = false;
	}

	async #syncPushState(): Promise<void> {
		if (!browser || !('serviceWorker' in navigator)) return;
		try {
			const reg = await navigator.serviceWorker.getRegistration();
			const sub = await reg?.pushManager.getSubscription();
			this.pushEnabled = !!sub;
		} catch {
			this.pushEnabled = false;
		}
	}
}

export const notifications = new Notifications();

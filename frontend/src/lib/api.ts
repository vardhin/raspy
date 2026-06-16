// Single source of truth for talking to the spine backend.
//
// Base URL: same-origin in production (the spine serves this bundle), overridable
// via PUBLIC_API_BASE for dev (Vite :5173) or a Capacitor APK. See .env.example.

import { browser } from '$app/environment';
import { env } from '$env/dynamic/public';
import { channel } from '$lib/crypto/channel';

// Layer-1 channel toggle. On by default in the browser; the handshake endpoints
// and any same-origin static assets bypass it. If the channel can't establish
// (e.g. no key on the Pi) we fall back to cleartext so the app still works.
const CHANNEL_ENABLED = browser;

export function apiBase(): string {
	return (env.PUBLIC_API_BASE ?? '').replace(/\/$/, '');
}

export function apiUrl(path: string): string {
	const p = path.startsWith('/') ? path : `/${path}`;
	return `${apiBase()}${p}`;
}

export function wsUrl(path: string): string {
	const base = apiBase();
	if (base) return base.replace(/^http/, 'ws') + path;
	if (!browser) return path;
	const proto = location.protocol === 'https:' ? 'wss:' : 'ws:';
	return `${proto}//${location.host}${path}`;
}

/** A relative attachment path -> absolute spine URL: "items" -> /api/att/<id>/items */
export function attUrl(attachmentId: string, path: string): string {
	const clean = path.replace(/^\//, '');
	return apiUrl(`/api/att/${attachmentId}/${clean}`);
}

export interface ApiError extends Error {
	status?: number;
	/** The server's response body (FastAPI `detail`, or raw text) — lets callers
	 *  react to a specific failure, e.g. the connectivity sudo-password flow. */
	detail?: string;
}

/** Read the readable CSRF cookie to echo on mutating cookie-auth requests. */
function csrfCookie(): string | null {
	if (typeof document === 'undefined') return null;
	const m = document.cookie.match(/(?:^|;\s*)raspy_csrf=([^;]+)/);
	return m ? decodeURIComponent(m[1]) : null;
}

const MUTATING = new Set(['POST', 'PUT', 'PATCH', 'DELETE']);

/** Hook the auth store calls when a request can't be authenticated even after a
 *  refresh. Set by auth.svelte to avoid an import cycle. */
let onAuthLost: ((needs: 'pin' | 'password') => void) | null = null;
export function setAuthLostHandler(fn: (needs: 'pin' | 'password') => void): void {
	onAuthLost = fn;
}

let refreshing: Promise<boolean> | null = null;

/** Try one cookie refresh; collapse concurrent callers onto one in-flight call. */
async function tryRefresh(): Promise<boolean> {
	if (!refreshing) {
		refreshing = fetch(apiUrl('/api/auth/refresh'), {
			method: 'POST',
			credentials: 'include',
			headers: { ...(csrfCookie() ? { 'x-csrf-token': csrfCookie()! } : {}) }
		})
			.then((r) => r.ok)
			.catch(() => false)
			.finally(() => {
				refreshing = null;
			});
	}
	return refreshing;
}

/** Paths that must NOT go through the channel: the handshake itself, and the
 *  vault blob/manifest endpoints — those payloads are ALREADY E2E-encrypted by
 *  the vault layer (so double-wrapping is wasted) and need to stream, which the
 *  body-buffering channel middleware would break. */
function bypassChannel(url: string): boolean {
	return (
		url.includes('/api/channel/') ||
		url.includes('/api/att/vault/') ||
		// Calendar photo blobs are E2E-encrypted ciphertext that streams — same as
		// the vault, no point double-wrapping them through the channel.
		url.includes('/api/att/calendar/image/') ||
		// Contact photo blobs are E2E-encrypted ciphertext too — same as the above.
		url.includes('/api/att/contacts/image/')
	);
}

async function rawFetch(url: string, init?: RequestInit): Promise<Response> {
	const method = (init?.method ?? 'GET').toUpperCase();
	const headers: Record<string, string> = {
		accept: 'application/json',
		...((init?.headers as Record<string, string>) ?? {})
	};
	// Double-submit CSRF on mutating cookie-auth requests.
	if (MUTATING.has(method)) {
		const csrf = csrfCookie();
		if (csrf) headers['x-csrf-token'] = csrf;
	}

	if (CHANNEL_ENABLED && !bypassChannel(url)) {
		try {
			return await channelFetch(url, method, headers, init);
		} catch (e) {
			// Channel unavailable (no key on the Pi, handshake failed) → cleartext.
			if ((e as Error)?.message?.includes('MITM')) throw e; // never downgrade on MITM
			// fall through to plain fetch
		}
	}
	return fetch(url, { ...init, credentials: 'include', headers });
}

/** Seal the request body + headers, send with the channel session header, and
 *  unseal the response into a normal Response the rest of api.ts can consume. */
async function channelFetch(
	url: string,
	method: string,
	headers: Record<string, string>,
	init?: RequestInit
): Promise<Response> {
	await channel.ensure();
	const sid = channel.sessionId;
	if (!sid) throw new Error('no channel session');

	// Seal the original body (if any) and preserve its content-type so the server
	// restores it after decrypt.
	const origCt = headers['content-type'] ?? headers['Content-Type'] ?? 'application/json';
	let sealedBody: string | undefined;
	if (init?.body != null) {
		const bytes =
			typeof init.body === 'string'
				? new TextEncoder().encode(init.body)
				: new Uint8Array(await new Response(init.body as BodyInit).arrayBuffer());
		sealedBody = await channel.seal(bytes);
	}

	const chHeaders: Record<string, string> = {
		...headers,
		'x-channel-session': sid,
		'x-channel-ct': origCt,
		'content-type': 'text/plain'
	};
	delete chHeaders['Content-Type'];

	let res = await fetch(url, {
		...init,
		method,
		credentials: 'include',
		headers: chHeaders,
		body: sealedBody
	});

	// Channel session expired server-side → re-handshake once and retry.
	if (res.status === 409) {
		channel.reset();
		await channel.ensure();
		return channelFetch(url, method, headers, init);
	}

	if (res.headers.get('x-channel-enc') === '1') {
		const plain = await channel.open(await res.text());
		const realCt = res.headers.get('x-channel-ct') ?? 'application/json';
		const out = new Headers(res.headers);
		out.set('content-type', realCt);
		out.delete('x-channel-enc');
		out.delete('x-channel-ct');
		return new Response(new Blob([plain as BlobPart]), {
			status: res.status,
			statusText: res.statusText,
			headers: out
		});
	}
	return res;
}

async function request<T>(url: string, init?: RequestInit): Promise<T> {
	let res = await rawFetch(url, init);
	// On 401, attempt exactly one silent refresh, then retry once. Auth endpoints
	// themselves are excluded (they manage their own flow).
	if (res.status === 401 && !url.includes('/api/auth/')) {
		if (await tryRefresh()) {
			res = await rawFetch(url, init);
		}
		if (res.status === 401) {
			// Still unauthenticated — ask the server what screen to show next.
			const needs = await sessionNeeds();
			onAuthLost?.(needs === 'pin' ? 'pin' : 'password');
		}
	}
	if (!res.ok) {
		const err: ApiError = new Error(`${init?.method ?? 'GET'} ${url} -> ${res.status}`);
		err.status = res.status;
		// Surface the body so callers can branch on the reason (e.g. needs-root).
		// FastAPI errors are {"detail": "..."}; fall back to the raw text.
		try {
			const body = await res.text();
			if (body) {
				try {
					err.detail = JSON.parse(body)?.detail ?? body;
				} catch {
					err.detail = body;
				}
			}
		} catch {
			/* body already consumed / unreadable — leave detail unset */
		}
		throw err;
	}
	if (res.status === 204) return undefined as T;
	const text = await res.text();
	return (text ? JSON.parse(text) : undefined) as T;
}

async function sessionNeeds(): Promise<string> {
	try {
		const r = await fetch(apiUrl('/api/auth/session'), { credentials: 'include' });
		return (await r.json()).needs ?? 'password';
	} catch {
		return 'password';
	}
}

/** GET a core (non-attachment) spine endpoint, e.g. "/api/update/status". */
export function apiGet<T = unknown>(path: string): Promise<T> {
	return request<T>(apiUrl(path));
}

/** POST to a core (non-attachment) spine endpoint with the usual auth/CSRF/channel. */
export function apiPost<T = unknown>(path: string, body?: unknown): Promise<T> {
	return request<T>(apiUrl(path), {
		method: 'POST',
		...(body !== undefined
			? { headers: { 'content-type': 'application/json' }, body: JSON.stringify(body) }
			: {})
	});
}

/** GET a list/object from an attachment's API (relative path). */
export function attGet<T = unknown>(attachmentId: string, path: string): Promise<T> {
	return request<T>(attUrl(attachmentId, path));
}

/** Run a declarative action (POST/DELETE/PATCH/GET) against an attachment. */
export function attAction<T = unknown>(
	attachmentId: string,
	method: string,
	path: string,
	body?: Record<string, unknown>
): Promise<T> {
	const init: RequestInit = { method: method.toUpperCase() };
	if (body !== undefined && method.toUpperCase() !== 'GET') {
		init.body = JSON.stringify(body);
		init.headers = { 'content-type': 'application/json' };
	}
	return request<T>(attUrl(attachmentId, path), init);
}

// --- query-string + binary helpers (used by the file manager) ---------------

function withQuery(url: string, params: Record<string, string>): string {
	const qs = new URLSearchParams(params).toString();
	return qs ? `${url}?${qs}` : url;
}

/** GET JSON from an attachment endpoint with query params. */
export function attGetQuery<T = unknown>(
	attachmentId: string,
	path: string,
	params: Record<string, string>
): Promise<T> {
	return request<T>(withQuery(attUrl(attachmentId, path), params));
}

/** POST JSON to an attachment endpoint with query params (returns JSON). */
export function attPostQuery<T = unknown>(
	attachmentId: string,
	path: string,
	params: Record<string, string>,
	body?: Record<string, unknown>
): Promise<T> {
	return request<T>(withQuery(attUrl(attachmentId, path), params), {
		method: 'POST',
		body: body ? JSON.stringify(body) : undefined,
		headers: body ? { 'content-type': 'application/json' } : undefined
	});
}

/** DELETE an attachment endpoint with query params. */
export function attDeleteQuery(
	attachmentId: string,
	path: string,
	params: Record<string, string>
): Promise<void> {
	return request<void>(withQuery(attUrl(attachmentId, path), params), { method: 'DELETE' });
}

/** Upload a single file via multipart/form-data to an attachment endpoint.
 *
 *  We build the multipart body ourselves with an explicit boundary and set the
 *  content-type, rather than handing a `FormData` to fetch. Reason: when the
 *  Layer-1 channel is active it seals the body and restores the content-type from
 *  the header we pass — but a browser-built `FormData` only attaches its boundary
 *  to the request content-type lazily, which the channel never sees, so the server
 *  would restore `application/json` and fail to parse the form (HTTP 422). An
 *  explicit boundary makes the content-type survive sealing. */
export async function attUpload(
	attachmentId: string,
	path: string,
	params: Record<string, string>,
	file: File
): Promise<unknown> {
	const boundary = `----raspy${crypto.randomUUID().replace(/-/g, '')}`;
	const enc = new TextEncoder();
	const name = file.name || 'upload.bin';
	const head = enc.encode(
		`--${boundary}\r\n` +
			`Content-Disposition: form-data; name="file"; filename="${name.replace(/"/g, '')}"\r\n` +
			`Content-Type: ${file.type || 'application/octet-stream'}\r\n\r\n`
	);
	const tail = enc.encode(`\r\n--${boundary}--\r\n`);
	const body = new Blob([head, await file.arrayBuffer(), tail]);
	return request<unknown>(withQuery(attUrl(attachmentId, path), params), {
		method: 'POST',
		body,
		headers: { 'content-type': `multipart/form-data; boundary=${boundary}` }
	});
}

/** Absolute URL for a GET endpoint with query params (download links, previews). */
export function attResourceUrl(
	attachmentId: string,
	path: string,
	params: Record<string, string>
): string {
	return withQuery(attUrl(attachmentId, path), params);
}

/** Fetch preview content; returns text and the content-type. */
export async function attPreview(
	attachmentId: string,
	path: string
): Promise<{ contentType: string; text: string; status: number }> {
	const res = await fetch(attResourceUrl(attachmentId, 'preview', { path }), {
		credentials: 'include'
	});
	const contentType = res.headers.get('content-type') ?? '';
	const text = res.ok && contentType.startsWith('text/') ? await res.text() : '';
	return { contentType, text, status: res.status };
}

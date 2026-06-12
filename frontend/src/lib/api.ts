// Single source of truth for talking to the spine backend.
//
// Base URL: same-origin in production (the spine serves this bundle), overridable
// via PUBLIC_API_BASE for dev (Vite :5173) or a Capacitor APK. See .env.example.

import { browser } from '$app/environment';
import { env } from '$env/dynamic/public';

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
	return fetch(url, { ...init, credentials: 'include', headers });
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

/** Upload a single file via multipart/form-data to an attachment endpoint. */
export async function attUpload(
	attachmentId: string,
	path: string,
	params: Record<string, string>,
	file: File
): Promise<unknown> {
	const fd = new FormData();
	fd.append('file', file, file.name);
	return request<unknown>(withQuery(attUrl(attachmentId, path), params), {
		method: 'POST',
		body: fd
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

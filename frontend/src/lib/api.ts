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

async function request<T>(url: string, init?: RequestInit): Promise<T> {
	const res = await fetch(url, {
		...init,
		headers: { accept: 'application/json', ...(init?.headers ?? {}) }
	});
	if (!res.ok) {
		const err: ApiError = new Error(`${init?.method ?? 'GET'} ${url} -> ${res.status}`);
		err.status = res.status;
		throw err;
	}
	if (res.status === 204) return undefined as T;
	const text = await res.text();
	return (text ? JSON.parse(text) : undefined) as T;
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

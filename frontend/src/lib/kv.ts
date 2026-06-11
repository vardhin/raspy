// Tiny promise-based IndexedDB key/value store, shared by the manifest cache and
// per-app data caches.
//
// IndexedDB (not localStorage) because it's larger, async, and not wiped by
// ordinary cookie/site-data resets. Everything stored here is a copy of
// server-owned data, so eviction only ever costs a refetch — never data loss.

import { browser } from '$app/environment';

const DB_NAME = 'raspy';
const STORE = 'kv';

let dbPromise: Promise<IDBDatabase> | null = null;

function openDB(): Promise<IDBDatabase> {
	if (dbPromise) return dbPromise;
	dbPromise = new Promise((resolve, reject) => {
		const req = indexedDB.open(DB_NAME, 1);
		req.onupgradeneeded = () => {
			const db = req.result;
			if (!db.objectStoreNames.contains(STORE)) db.createObjectStore(STORE);
		};
		req.onsuccess = () => resolve(req.result);
		req.onerror = () => reject(req.error);
	});
	return dbPromise;
}

function available(): boolean {
	return browser && typeof indexedDB !== 'undefined';
}

export async function kvGet<T>(key: string): Promise<T | null> {
	if (!available()) return null;
	try {
		const db = await openDB();
		return await new Promise<T | null>((resolve, reject) => {
			const req = db.transaction(STORE, 'readonly').objectStore(STORE).get(key);
			req.onsuccess = () => resolve((req.result as T) ?? null);
			req.onerror = () => reject(req.error);
		});
	} catch {
		return null;
	}
}

export async function kvSet<T>(key: string, value: T): Promise<void> {
	if (!available()) return;
	try {
		const db = await openDB();
		await new Promise<void>((resolve, reject) => {
			const tx = db.transaction(STORE, 'readwrite');
			tx.objectStore(STORE).put(value, key);
			tx.oncomplete = () => resolve();
			tx.onerror = () => reject(tx.error);
		});
	} catch {
		// Best-effort cache; ignore quota / private-mode failures.
	}
}

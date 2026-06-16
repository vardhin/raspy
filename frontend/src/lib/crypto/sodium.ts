// Lazy libsodium initializer. We use the *sumo* build because it includes
// crypto_pwhash (Argon2id), which the standard build omits and which we need for
// the password KDF. All crypto in the app funnels through this single ready()
// so we initialize the WASM exactly once.
//
// The library is ~500 kB, so we pull it in via a dynamic import(): it lands in
// its own chunk that the bundler loads only on first crypto use, keeping it out
// of the initial page payload. The default import is type-only (erased at build).

import type _sodium from 'libsodium-wrappers-sumo';

export type Sodium = typeof _sodium;

let ready: Promise<Sodium> | null = null;

export function sodiumReady(): Promise<Sodium> {
	if (!ready) {
		ready = import('libsodium-wrappers-sumo').then((m) => {
			const s = m.default;
			return s.ready.then(() => s);
		});
	}
	return ready;
}

// --- small base64url helpers (URL-safe, unpadded — matches the backend) ------

export function b64encode(s: Sodium, raw: Uint8Array): string {
	return s.to_base64(raw, s.base64_variants.URLSAFE_NO_PADDING);
}

export function b64decode(s: Sodium, str: string): Uint8Array {
	return s.from_base64(str, s.base64_variants.URLSAFE_NO_PADDING);
}

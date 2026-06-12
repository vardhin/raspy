// Lazy libsodium initializer. We use the *sumo* build because it includes
// crypto_pwhash (Argon2id), which the standard build omits and which we need for
// the password KDF. All crypto in the app funnels through this single ready()
// so we initialize the WASM exactly once.

import _sodium from 'libsodium-wrappers-sumo';

let ready: Promise<typeof _sodium> | null = null;

export function sodiumReady(): Promise<typeof _sodium> {
	if (!ready) {
		ready = _sodium.ready.then(() => _sodium);
	}
	return ready;
}

export type Sodium = typeof _sodium;

// --- small base64url helpers (URL-safe, unpadded — matches the backend) ------

export function b64encode(s: Sodium, raw: Uint8Array): string {
	return s.to_base64(raw, s.base64_variants.URLSAFE_NO_PADDING);
}

export function b64decode(s: Sodium, str: string): Uint8Array {
	return s.from_base64(str, s.base64_variants.URLSAFE_NO_PADDING);
}

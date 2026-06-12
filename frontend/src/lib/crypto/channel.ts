// Layer-1 channel client. Establishes a forward-secret session with the Pi and
// seals/opens payloads so Cloudflare (the tunnel) only relays ciphertext.
//
// Scheme — byte-for-byte interoperable with the backend (verified):
//   * ephemeral X25519 (crypto_scalarmult); server uses an ephemeral key too
//   * HKDF-SHA256 (RFC 5869) via HMAC-SHA256, salt = client_pub||server_pub,
//     info = "raspy-channel-v1"
//   * ChaCha20-Poly1305 IETF (12-byte nonce) AEAD, payload = base64(nonce||ct)
//   * handshake response signed by the Pi's pinned Ed25519 key (MITM detection)
//
// The Pi's static identity is pinned in localStorage on first contact; a later
// mismatch aborts (possible MITM / key rotation needs an explicit reset).

import { browser } from '$app/environment';
import { apiUrl } from '$lib/api';
import { sodiumReady, b64encode, b64decode, type Sodium } from './sodium';

const INFO = 'raspy-channel-v1';
const PIN_KEY = 'raspy-channel-pin'; // localStorage key for the pinned identity

interface PubKeyResp {
	x25519: string;
	ed25519: string;
	alg: string;
	version: string;
}

interface HandshakeResp {
	session_id: string;
	server_pub: string;
	signature: string;
}

// RFC 5869 HKDF-SHA256 using libsodium's incremental HMAC (the wrappers build
// doesn't expose crypto_kdf_hkdf_*). Single 32-byte output is all we need.
function hkdf32(s: Sodium, salt: Uint8Array, ikm: Uint8Array, info: Uint8Array): Uint8Array {
	const ext = s.crypto_auth_hmacsha256_init(salt);
	s.crypto_auth_hmacsha256_update(ext, ikm);
	const prk = s.crypto_auth_hmacsha256_final(ext);
	const exp = s.crypto_auth_hmacsha256_init(prk);
	const t = new Uint8Array(info.length + 1);
	t.set(info);
	t[info.length] = 1;
	s.crypto_auth_hmacsha256_update(exp, t);
	return s.crypto_auth_hmacsha256_final(exp).slice(0, 32);
}

class Channel {
	#sid: string | null = null;
	#key: Uint8Array | null = null;
	#establishing: Promise<void> | null = null;

	get sessionId(): string | null {
		return this.#sid;
	}

	get ready(): boolean {
		return this.#sid !== null && this.#key !== null;
	}

	/** Establish (or reuse) a channel session. Safe to call concurrently. */
	async ensure(): Promise<void> {
		if (this.ready) return;
		if (!this.#establishing) {
			this.#establishing = this.#handshake().finally(() => {
				this.#establishing = null;
			});
		}
		return this.#establishing;
	}

	/** Force a fresh handshake (e.g. after a 409 channel-expired). */
	reset(): void {
		this.#sid = null;
		this.#key = null;
	}

	async #handshake(): Promise<void> {
		const s = await sodiumReady();
		const info: PubKeyResp = await (await fetch(apiUrl('/api/channel/pubkey'))).json();
		this.#pinOrVerify(info);

		const ephPriv = s.randombytes_buf(s.crypto_scalarmult_SCALARBYTES);
		const ephPub = s.crypto_scalarmult_base(ephPriv);
		const res = await fetch(apiUrl('/api/channel/handshake'), {
			method: 'POST',
			headers: { 'content-type': 'application/json' },
			body: JSON.stringify({ client_pub: b64encode(s, ephPub) })
		});
		const hs: HandshakeResp = await res.json();
		const serverPub = b64decode(s, hs.server_pub);

		// Verify the server signed (client_pub || server_pub) with its pinned key.
		const signed = new Uint8Array([...ephPub, ...serverPub]);
		const ok = s.crypto_sign_verify_detached(
			b64decode(s, hs.signature),
			signed,
			b64decode(s, info.ed25519)
		);
		if (!ok) throw new Error('channel handshake signature invalid (possible MITM)');

		const shared = s.crypto_scalarmult(ephPriv, serverPub);
		this.#key = hkdf32(
			s,
			new Uint8Array([...ephPub, ...serverPub]),
			shared,
			new TextEncoder().encode(INFO)
		);
		this.#sid = hs.session_id;
	}

	#pinOrVerify(info: PubKeyResp): void {
		if (!browser) return;
		const pinned = localStorage.getItem(PIN_KEY);
		const fingerprint = `${info.x25519}|${info.ed25519}`;
		if (pinned === null) {
			localStorage.setItem(PIN_KEY, fingerprint);
		} else if (pinned !== fingerprint) {
			throw new Error(
				'channel identity changed — refusing to connect (possible MITM). ' +
					'If you intentionally rotated the Pi key, clear site data to re-pin.'
			);
		}
	}

	async seal(plaintext: Uint8Array): Promise<string> {
		const s = await sodiumReady();
		if (!this.#key) throw new Error('channel not established');
		const nonce = s.randombytes_buf(s.crypto_aead_chacha20poly1305_ietf_NPUBBYTES);
		const ct = s.crypto_aead_chacha20poly1305_ietf_encrypt(plaintext, null, null, nonce, this.#key);
		return b64encode(s, new Uint8Array([...nonce, ...ct]));
	}

	async open(payloadB64: string): Promise<Uint8Array> {
		const s = await sodiumReady();
		if (!this.#key) throw new Error('channel not established');
		const blob = b64decode(s, payloadB64);
		const n = s.crypto_aead_chacha20poly1305_ietf_NPUBBYTES;
		return s.crypto_aead_chacha20poly1305_ietf_decrypt(
			null,
			blob.slice(n),
			null,
			blob.slice(0, n),
			this.#key
		);
	}
}

export const channel = new Channel();

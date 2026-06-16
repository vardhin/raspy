<script lang="ts">
	// Shell-level unlock gate, shown when the server session is still valid but the
	// vault master key is missing (e.g. after a page reload). The session survives
	// in the cookie; the in-memory key does not — so the apps that need it (vault,
	// calendar) are locked until the user re-establishes it here.
	//
	// PIN-first: if a PIN-wrapped key exists locally we offer the fast PIN unlock,
	// with a link to fall back to the full password. If there is no local wrapped
	// key, we go straight to the password form. Token-only styling.
	import { Surface, Stack, Text, Field, Button } from '$lib/components';
	import { auth } from '$lib/auth.svelte';

	// Start on the PIN screen when a local wrapped key exists to unwrap. The check
	// (hasWrappedMasterKey) is async, so auth.hasLocalPin can still be false at
	// mount and flip to true a tick later — if we snapshot it once we'd wrongly
	// stick on the password form. Track whether the user has explicitly chosen a
	// mode; until they do, follow auth.hasLocalPin reactively.
	let chosen = $state<'pin' | 'password' | null>(null);
	const mode = $derived(chosen ?? (auth.hasLocalPin ? 'pin' : 'password'));

	let pin = $state('');
	let password = $state('');
	let newPin = $state('');

	async function submitPin(e: Event) {
		e.preventDefault();
		await auth.unlockWithPin(pin);
		pin = '';
	}

	async function submitPassword(e: Event) {
		e.preventDefault();
		await auth.unlockWithPassword(password, newPin || undefined);
		password = '';
		newPin = '';
	}

	function toPassword() {
		auth.error = null;
		chosen = 'password';
	}
	function toPin() {
		auth.error = null;
		chosen = 'pin';
	}
</script>

<div class="gate">
	<Surface level={2}>
		{#if mode === 'pin'}
			<form onsubmit={submitPin}>
				<Stack gap={4}>
					<Text role="title">Locked</Text>
					<Text role="muted">Enter your PIN to unlock the vault and calendar.</Text>

					<Field
						type="password"
						label="PIN"
						bind:value={pin}
						inputmode="numeric"
						autocomplete="off"
						required
					/>

					{#if auth.error}
						<span class="err">{auth.error}</span>
					{/if}

					<Button type="submit" disabled={auth.busy}>
						{auth.busy ? 'Unlocking…' : 'Unlock'}
					</Button>
					<button type="button" class="link" onclick={toPassword}>
						Use password instead
					</button>
				</Stack>
			</form>
		{:else}
			<form onsubmit={submitPassword}>
				<Stack gap={4}>
					<Text role="title">Locked</Text>
					<Text role="muted">Enter your password to unlock the vault and calendar.</Text>

					<Field
						type="password"
						label="Password"
						bind:value={password}
						autocomplete="current-password"
						required
					/>
					<Field
						type="password"
						label="PIN"
						bind:value={newPin}
						inputmode="numeric"
						autocomplete="off"
					/>

					{#if auth.error}
						<span class="err">{auth.error}</span>
					{/if}

					<Button type="submit" disabled={auth.busy}>
						{auth.busy ? 'Unlocking…' : 'Unlock'}
					</Button>
					{#if auth.hasLocalPin}
						<button type="button" class="link" onclick={toPin}>Use PIN instead</button>
					{/if}
				</Stack>
			</form>
		{/if}
	</Surface>
</div>

<style>
	.gate {
		min-height: 100dvh;
		display: grid;
		place-items: center;
		padding: var(--space-5);
	}
	form {
		width: min(360px, 90vw);
	}
	.err {
		color: var(--danger);
		font-size: 0.9rem;
	}
	.link {
		background: none;
		border: none;
		color: var(--muted);
		font-size: 0.9rem;
		text-decoration: underline;
		cursor: pointer;
		padding: 0;
	}
	.link:hover {
		color: var(--fg);
	}
</style>

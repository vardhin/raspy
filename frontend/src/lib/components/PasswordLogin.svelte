<script lang="ts">
	// Full password login. Also collects the mini-PIN so the stale-session unlock
	// works afterwards: on success we derive the vault master key and PIN-wrap it
	// locally. Token-only styling — re-skins with any theme.
	//
	// A "Forgot password?" link swaps to the break-glass recovery form (plan/35):
	// enter the recovery phrase + a new password to recover the vault via the
	// mnemonic-wrapped DEK.
	import { Surface, Stack, Text, Field, Button } from '$lib/components';
	import { auth } from '$lib/auth.svelte';
	import { isValidMnemonic } from '$lib/crypto/recovery';

	let mode = $state<'login' | 'recover'>('login');

	let username = $state('');
	let password = $state('');
	let pin = $state('');

	// Recovery form fields.
	let phrase = $state('');
	let newPassword = $state('');
	let newPin = $state('');

	let phraseLooksValid = $derived(phrase.trim() === '' || isValidMnemonic(phrase));

	async function submit(e: Event) {
		e.preventDefault();
		await auth.login(username, password, pin || undefined);
		if (auth.state === 'active' && pin) {
			// Wrap the in-memory master key under the PIN for future quick unlocks.
			try {
				await auth.setLocalPin(pin);
			} catch {
				/* non-fatal: user can still re-login with the password */
			}
		}
	}

	async function submitRecovery(e: Event) {
		e.preventDefault();
		await auth.recoverWithMnemonic(username, phrase, newPassword, newPin || undefined);
		// On success auth.state flips to 'active' (login() inside the flow); the
		// shell takes over. On failure auth.error is shown below.
	}

	function toggle(next: 'login' | 'recover') {
		auth.error = null;
		mode = next;
	}
</script>

<div class="gate">
	<Surface level={2}>
		{#if mode === 'login'}
			<form onsubmit={submit}>
				<Stack gap={4}>
					<Text role="title">Raspy</Text>
					<Text role="muted">Sign in to your Pi.</Text>

					<Field label="Username" bind:value={username} autocomplete="username" required />
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
						bind:value={pin}
						inputmode="numeric"
						autocomplete="off"
					/>

					{#if auth.error}
						<span class="err">{auth.error}</span>
					{/if}

					<Button type="submit" disabled={auth.busy}>
						{auth.busy ? 'Signing in…' : 'Sign in'}
					</Button>

					<button type="button" class="link" onclick={() => toggle('recover')}>
						Forgot password?
					</button>
				</Stack>
			</form>
		{:else}
			<form onsubmit={submitRecovery}>
				<Stack gap={4}>
					<Text role="title">Recover access</Text>
					<Text role="muted">
						Enter your recovery phrase and choose a new password. Your vault data is
						preserved.
					</Text>

					<Field label="Username" bind:value={username} autocomplete="username" required />
					<Field
						type="textarea"
						label="Recovery phrase"
						bind:value={phrase}
						placeholder="twelve words separated by spaces"
						autocomplete="off"
						required
					/>
					{#if !phraseLooksValid}
						<span class="warn">That doesn't look like a valid recovery phrase.</span>
					{/if}
					<Field
						type="password"
						label="New password"
						bind:value={newPassword}
						autocomplete="new-password"
						required
					/>
					<Field
						type="password"
						label="New PIN"
						bind:value={newPin}
						inputmode="numeric"
						autocomplete="off"
					/>

					{#if auth.error}
						<span class="err">{auth.error}</span>
					{/if}

					<Button
						type="submit"
						disabled={auth.busy || !isValidMnemonic(phrase) || !newPassword}
					>
						{auth.busy ? 'Recovering…' : 'Recover account'}
					</Button>

					<button type="button" class="link" onclick={() => toggle('login')}>
						Back to sign in
					</button>
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
	.warn {
		color: var(--warn, var(--muted));
		font-size: 0.85rem;
	}
	.link {
		background: none;
		border: none;
		color: var(--muted);
		font-size: 0.85rem;
		text-align: center;
		cursor: pointer;
		padding: 0;
	}
	.link:hover {
		color: var(--fg);
		text-decoration: underline;
	}
</style>

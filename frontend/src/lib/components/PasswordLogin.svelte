<script lang="ts">
	// Full password login. Also collects the mini-PIN so the stale-session unlock
	// works afterwards: on success we derive the vault master key and PIN-wrap it
	// locally. Token-only styling — re-skins with any theme.
	import { Surface, Stack, Text, Field, Button } from '$lib/components';
	import { auth } from '$lib/auth.svelte';

	let username = $state('');
	let password = $state('');
	let pin = $state('');

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
</script>

<div class="gate">
	<Surface level={2}>
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
			</Stack>
		</form>
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
</style>

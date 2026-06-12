<script lang="ts">
	// Mini-PIN unlock for a stale (but not expired) session. Shown when the access
	// token lapsed while the 7-day refresh is still valid. A "Use password instead"
	// link drops to the full login (and clears the local wrapped key).
	import { Surface, Stack, Text, Field, Button } from '$lib/components';
	import { auth } from '$lib/auth.svelte';
	import { clearWrappedMasterKey } from '$lib/crypto/keystore';

	let pin = $state('');

	async function submit(e: Event) {
		e.preventDefault();
		await auth.unlock(pin);
		pin = '';
	}

	async function usePassword() {
		await clearWrappedMasterKey();
		auth.error = null;
		auth.state = 'password';
	}
</script>

<div class="gate">
	<Surface level={2}>
		<form onsubmit={submit}>
			<Stack gap={4}>
				<Text role="title">Welcome back{auth.username ? `, ${auth.username}` : ''}</Text>
				<Text role="muted">Enter your PIN to unlock.</Text>

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
				<Button variant="ghost" size="sm" onclick={usePassword}>Use password instead</Button>
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
		width: min(340px, 90vw);
	}
	.err {
		color: var(--danger);
		font-size: 0.9rem;
	}
</style>

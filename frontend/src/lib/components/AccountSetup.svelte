<script lang="ts">
	import { Surface, Stack, Text, Field, Button } from '$lib/components';
	import { auth } from '$lib/auth.svelte';

	let password = $state('');
	let confirmPassword = $state('');
	let pin = $state('');
	let confirmPin = $state('');
	let localError = $state<string | null>(null);

	async function submit(e: Event) {
		e.preventDefault();
		localError = null;
		if (password !== confirmPassword) {
			localError = 'Passwords do not match.';
			return;
		}
		if (pin !== confirmPin) {
			localError = 'PINs do not match.';
			return;
		}
		await auth.completeSetup(password, pin);
	}
</script>

<div class="gate">
	<Surface level={2}>
		<form onsubmit={submit}>
			<Stack gap={4}>
				<Text role="title">Finish account setup</Text>
				<Text role="muted">Choose your new password and PIN.</Text>

				<Field
					type="password"
					label="New password"
					bind:value={password}
					autocomplete="new-password"
					required
				/>
				<Field
					type="password"
					label="Confirm password"
					bind:value={confirmPassword}
					autocomplete="new-password"
					required
				/>
				<Field
					type="password"
					label="New PIN"
					bind:value={pin}
					inputmode="numeric"
					autocomplete="off"
					required
				/>
				<Field
					type="password"
					label="Confirm PIN"
					bind:value={confirmPin}
					inputmode="numeric"
					autocomplete="off"
					required
				/>

				{#if localError || auth.error}
					<span class="err">{localError ?? auth.error}</span>
				{/if}

				<Button type="submit" disabled={auth.busy}>
					{auth.busy ? 'Saving...' : 'Save and continue'}
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
		width: min(380px, 90vw);
	}
	.err {
		color: var(--danger);
		font-size: 0.9rem;
	}
</style>

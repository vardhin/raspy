<script lang="ts">
	// One-time display of the vault recovery phrase (plan/35). Shown when
	// `auth.pendingMnemonic` is set — right after a legacy account migrates or a
	// new account is set up. The phrase is the break-glass root for a forgotten
	// password; it is never stored in plaintext and never shown again, so the user
	// must confirm they've written it down before it's cleared from memory.
	import { Modal, Stack, Text, Button, Checkbox } from '$lib/components';
	import { auth } from '$lib/auth.svelte';

	let confirmed = $state(false);
	let copied = $state(false);

	let words = $derived((auth.pendingMnemonic ?? '').split(' '));

	async function copy() {
		if (!auth.pendingMnemonic) return;
		try {
			await navigator.clipboard.writeText(auth.pendingMnemonic);
			copied = true;
			setTimeout(() => (copied = false), 1500);
		} catch {
			/* clipboard blocked — the user can still transcribe it */
		}
	}

	function done() {
		confirmed = false;
		auth.acknowledgeMnemonic();
	}
</script>

<Modal open={auth.pendingMnemonic !== null} title="Save your recovery phrase" size="md">
	<Stack gap={4}>
		<Text role="muted">
			These {words.length} words are the only way to recover your vault if you forget your
			password. Write them down and keep them somewhere safe — they are shown once and never
			again. Anyone with this phrase can unlock your data.
		</Text>

		<ol class="grid">
			{#each words as word, i (i)}
				<li><span class="n">{i + 1}</span><span class="w">{word}</span></li>
			{/each}
		</ol>

		<Button variant="ghost" onclick={copy}>{copied ? 'Copied' : 'Copy phrase'}</Button>

		<Checkbox bind:checked={confirmed} label="I have written down my recovery phrase" />

		<Button disabled={!confirmed} onclick={done}>Continue</Button>
	</Stack>
</Modal>

<style>
	.grid {
		display: grid;
		grid-template-columns: repeat(3, 1fr);
		gap: var(--space-2);
		margin: 0;
		padding: 0;
		list-style: none;
	}
	.grid li {
		display: flex;
		align-items: baseline;
		gap: var(--space-2);
		padding: var(--space-2) var(--space-3);
		background: var(--surface);
		border: var(--border-width) solid var(--border-color);
		border-radius: var(--radius-md);
		font-variant-numeric: tabular-nums;
	}
	.n {
		color: var(--muted);
		font-size: 0.75rem;
		min-width: 1.2em;
		text-align: right;
	}
	.w {
		font-weight: 600;
		word-break: break-all;
	}
	@media (max-width: 420px) {
		.grid {
			grid-template-columns: repeat(2, 1fr);
		}
	}
</style>

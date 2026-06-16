<script lang="ts">
	// Reusable "ask for sudo password" dialog. A privileged action that fails with
	// the backend's needs-root signal pops this; on submit it re-runs the action
	// with the password. Token-only (plan/45 §6), built on the Modal primitive.
	//
	// The password is held only in this component's local state for the lifetime of
	// the dialog and cleared on close — it is never persisted, logged, or lifted
	// into a store. It travels to the server over the encrypted channel
	// (core/channel) like any other request body.
	import { Modal, Field, Button, Stack, Text, Icon } from '$lib/components';

	let {
		open = false,
		title = 'Administrator password required',
		// Optional context line, e.g. the command that needs root.
		detail = '',
		busy = false,
		error = null,
		onsubmit,
		oncancel
	}: {
		open?: boolean;
		title?: string;
		detail?: string;
		busy?: boolean;
		error?: string | null;
		onsubmit: (password: string) => void;
		oncancel: () => void;
	} = $props();

	let password = $state('');

	// Clear the field whenever the dialog closes so a password never lingers.
	$effect(() => {
		if (!open) password = '';
	});

	function submit() {
		if (!password || busy) return;
		onsubmit(password);
	}

	function onKey(e: KeyboardEvent) {
		if (e.key === 'Enter') {
			e.preventDefault();
			submit();
		}
	}
</script>

<Modal {open} {title} size="sm" onclose={oncancel}>
	<Stack gap={3}>
		<div class="lead">
			<Icon name="lock" size={18} />
			<Text role="muted">
				This action needs root on this machine. Your password is sent over the
				encrypted channel, used once, and never stored.
			</Text>
		</div>

		{#if detail}
			<code class="cmd">{detail}</code>
		{/if}

		<!-- svelte-ignore a11y_autofocus -->
		<Field
			type="password"
			label="sudo password"
			placeholder="••••••••"
			bind:value={password}
			autocomplete="current-password"
			autofocus
			disabled={busy}
			onkeydown={onKey}
		/>

		{#if error}<span class="err">{error}</span>{/if}

		<div class="row">
			<Button variant="ghost" disabled={busy} onclick={oncancel}>Cancel</Button>
			<Button variant="accent" disabled={!password || busy} onclick={submit}>
				{busy ? 'Authorizing…' : 'Authorize'}
			</Button>
		</div>
	</Stack>
</Modal>

<style>
	.lead {
		display: flex;
		align-items: flex-start;
		gap: var(--space-2);
	}
	.cmd {
		font-family: var(--font-mono, monospace);
		font-size: 0.85rem;
		padding: var(--space-2) var(--space-3);
		background: color-mix(in srgb, var(--surface-2) calc(var(--surface-alpha) * 100%), transparent);
		border: var(--border-width) solid var(--border-color);
		border-radius: var(--radius-md);
		overflow-wrap: anywhere;
	}
	.row {
		display: flex;
		justify-content: flex-end;
		gap: var(--space-2);
	}
	.err {
		color: var(--danger, crimson);
		font-size: 0.85rem;
	}
</style>

<script lang="ts">
	// "Update available" banner. Renders only when the backend reports a newer,
	// applicable release (admin only — see update store). One click downloads,
	// verifies, swaps and restarts the spine; we keep the human in the loop, the
	// server never restarts silently.
	import { update } from '$lib/update/store.svelte';
	import Button from './Button.svelte';
	import Icon from './Icon.svelte';
</script>

{#if update.showBanner}
	<div class="update-banner" role="status" aria-live="polite">
		<Icon name="download" size={18} />
		<span class="msg">
			{#if update.phase === 'restarting'}
				Updating to <b>{update.latest}</b> — the server is restarting…
			{:else if update.phase === 'error'}
				Update failed: {update.error}
			{:else}
				Raspy <b>{update.latest}</b> is available (you're on {update.current}).
			{/if}
		</span>

		<div class="actions">
			{#if update.phase === 'restarting'}
				<span class="spin" aria-hidden="true"></span>
			{:else}
				<Button
					size="sm"
					variant="accent"
					disabled={update.phase === 'applying'}
					onclick={() => update.apply()}
				>
					{update.phase === 'applying' ? 'Updating…' : 'Update now'}
				</Button>
				<button class="dismiss" aria-label="Dismiss" onclick={() => update.dismiss()}>
					<Icon name="x" size={16} />
				</button>
			{/if}
		</div>
	</div>
{/if}

<style>
	.update-banner {
		display: flex;
		align-items: center;
		gap: var(--space-3);
		padding: var(--space-2) var(--space-4);
		background: color-mix(in srgb, var(--accent) 14%, var(--surface-2));
		color: var(--fg);
		border-bottom: var(--border-width) solid var(--border-color);
	}
	.msg {
		flex: 1;
		min-width: 0;
		font-size: 0.9rem;
	}
	.actions {
		display: flex;
		align-items: center;
		gap: var(--space-2);
	}
	.dismiss {
		display: inline-flex;
		align-items: center;
		justify-content: center;
		padding: var(--space-1);
		background: transparent;
		color: var(--fg-muted, var(--fg));
		border: none;
		border-radius: var(--radius-md);
		cursor: pointer;
	}
	.dismiss:hover {
		background: var(--surface);
	}
	.spin {
		width: 1rem;
		height: 1rem;
		border: 2px solid var(--border-color);
		border-top-color: var(--accent);
		border-radius: var(--radius-full);
		animation: spin 0.8s linear infinite;
	}
	@keyframes spin {
		to {
			transform: rotate(360deg);
		}
	}
</style>

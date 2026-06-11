<script lang="ts">
	// Token-only dialog primitive (plan/45 §6). Scrim via --overlay, panel via the
	// same surface tokens as Surface so it re-skins with any color × concept.
	import type { Snippet } from 'svelte';
	import Text from './Text.svelte';
	import Icon from './Icon.svelte';

	let {
		open = false,
		title = '',
		size = 'md',
		onclose,
		children
	}: {
		open?: boolean;
		title?: string;
		size?: 'sm' | 'md' | 'lg';
		onclose?: () => void;
		children: Snippet;
	} = $props();

	function onKey(e: KeyboardEvent) {
		if (e.key === 'Escape') onclose?.();
	}
</script>

<svelte:window onkeydown={open ? onKey : undefined} />

{#if open}
	<div
		class="scrim"
		role="presentation"
		onclick={(e) => {
			if (e.target === e.currentTarget) onclose?.();
		}}
	>
		<div class="panel {size}" role="dialog" aria-modal="true">
			<div class="head">
				<Text role="heading">{title}</Text>
				<button class="close" aria-label="Close" onclick={() => onclose?.()}>
					<Icon name="x" size={18} />
				</button>
			</div>
			<div class="body">
				{@render children()}
			</div>
		</div>
	</div>
{/if}

<style>
	.scrim {
		position: fixed;
		inset: 0;
		z-index: 100;
		display: flex;
		align-items: center;
		justify-content: center;
		padding: var(--space-4);
		background: var(--overlay, rgba(0, 0, 0, 0.5));
		backdrop-filter: blur(calc(var(--blur) / 2));
		-webkit-backdrop-filter: blur(calc(var(--blur) / 2));
	}
	.panel {
		display: flex;
		flex-direction: column;
		width: 100%;
		max-height: 85dvh;
		background: color-mix(
			in srgb,
			var(--surface-2) calc(var(--surface-alpha, 1) * 100%),
			transparent
		);
		backdrop-filter: blur(var(--blur));
		-webkit-backdrop-filter: blur(var(--blur));
		border: var(--border-width) solid var(--border-color);
		border-radius: var(--radius-lg);
		box-shadow: var(--shadow-lg);
		color: var(--fg);
	}
	.panel.sm {
		max-width: 360px;
	}
	.panel.md {
		max-width: 560px;
	}
	.panel.lg {
		max-width: 880px;
	}
	.head {
		display: flex;
		align-items: center;
		justify-content: space-between;
		gap: var(--space-3);
		padding: var(--space-3) var(--space-4);
		border-bottom: var(--border-width) solid var(--border-color);
	}
	.close {
		display: inline-flex;
		align-items: center;
		justify-content: center;
		padding: var(--space-1);
		background: transparent;
		color: var(--muted);
		border: none;
		border-radius: var(--radius-md);
		cursor: pointer;
	}
	.close:hover {
		color: var(--fg);
		background: var(--surface);
	}
	.body {
		padding: var(--space-4);
		overflow: auto;
	}
</style>

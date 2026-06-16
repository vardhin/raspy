<script lang="ts">
	// Token-only hover/focus tooltip. Wraps arbitrary trigger content (children)
	// and shows `text` on hover or keyboard focus. CSS-only visibility so it works
	// without JS state; positioned around the trigger via `placement`.
	import type { Snippet } from 'svelte';

	let {
		text,
		placement = 'top',
		children
	}: {
		text: string;
		placement?: 'top' | 'bottom' | 'left' | 'right';
		children: Snippet;
	} = $props();
</script>

<span class="tip-wrap">
	<span class="trigger">{@render children()}</span>
	<span class="bubble {placement}" role="tooltip">{text}</span>
</span>

<style>
	.tip-wrap {
		position: relative;
		display: inline-flex;
	}
	.trigger {
		display: inline-flex;
		outline: none;
	}
	.bubble {
		position: absolute;
		z-index: 60;
		max-width: 16rem;
		width: max-content;
		padding: var(--space-1) var(--space-2);
		font-size: 0.78rem;
		font-weight: var(--font-weight-bold);
		line-height: 1.3;
		color: var(--fg);
		background: color-mix(
			in srgb,
			var(--surface-2) calc(var(--surface-alpha) * 100%),
			transparent
		);
		backdrop-filter: blur(var(--blur));
		-webkit-backdrop-filter: blur(var(--blur));
		border: var(--border-width) solid var(--border-color);
		border-radius: var(--radius-sm);
		box-shadow: var(--shadow-md);
		opacity: 0;
		pointer-events: none;
		transition: opacity var(--motion-fast) var(--motion-ease);
	}
	.tip-wrap:hover .bubble,
	.tip-wrap:focus-within .bubble {
		opacity: 1;
	}
	.bubble.top {
		bottom: calc(100% + var(--space-1));
		left: 50%;
		transform: translateX(-50%);
	}
	.bubble.bottom {
		top: calc(100% + var(--space-1));
		left: 50%;
		transform: translateX(-50%);
	}
	.bubble.left {
		right: calc(100% + var(--space-1));
		top: 50%;
		transform: translateY(-50%);
	}
	.bubble.right {
		left: calc(100% + var(--space-1));
		top: 50%;
		transform: translateY(-50%);
	}
</style>

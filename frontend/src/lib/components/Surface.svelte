<script lang="ts">
	// The universal container: card, panel, row, sheet — all the same primitive.
	// Composes BOTH theme axes: color (--surface hue) and concept (radius, shadow,
	// blur, border, alpha). Reads ONLY tokens, so any color × concept works.
	import type { Snippet } from 'svelte';

	let {
		level = 1,
		interactive = false,
		padded = true,
		as = 'div',
		children,
		onclick,
		...rest
	}: {
		level?: 1 | 2;
		interactive?: boolean;
		padded?: boolean;
		as?: 'div' | 'section' | 'article' | 'button';
		children: Snippet;
		onclick?: (e: MouseEvent) => void;
		[key: string]: unknown;
	} = $props();

	const shadow = $derived(level === 2 ? 'var(--shadow-lg)' : 'var(--shadow-md)');
	const baseColor = $derived(level === 2 ? 'var(--surface-2)' : 'var(--surface)');
</script>

<svelte:element
	this={as}
	class="surface"
	class:interactive
	class:padded
	style:--_surface-color={baseColor}
	style:--_surface-shadow={shadow}
	{onclick}
	{...rest}
>
	{@render children()}
</svelte:element>

<style>
	.surface {
		/* alpha lets concepts (glass/frosted) bleed the bg through; opaque concepts
		   set --surface-alpha: 1 so this is a no-op for them. */
		background: color-mix(
			in srgb,
			var(--_surface-color) calc(var(--surface-alpha) * 100%),
			transparent
		);
		backdrop-filter: blur(var(--blur));
		-webkit-backdrop-filter: blur(var(--blur));
		border: var(--border-width) solid var(--border-color);
		border-radius: var(--radius-lg);
		box-shadow: var(--_surface-shadow);
		color: var(--fg);
		transition: var(--transition);
	}

	.padded {
		padding: var(--space-4);
	}

	.interactive {
		cursor: pointer;
	}
	.interactive:hover {
		transform: translateY(var(--hover-lift));
		box-shadow: var(--shadow-hover), var(--hover-glow);
	}
	.interactive:active {
		transform: scale(var(--press-scale));
	}
	.interactive:focus-visible {
		outline: none;
		box-shadow: var(--focus-ring);
	}
</style>

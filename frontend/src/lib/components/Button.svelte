<script lang="ts">
	// Semantic variants map to color tokens (never literal colors), so a "danger"
	// button is correct in every palette, and concept tokens give it its form.
	import type { Snippet } from 'svelte';

	type Variant = 'accent' | 'neutral' | 'ghost' | 'success' | 'warn' | 'danger';
	type Size = 'sm' | 'md' | 'lg';

	let {
		variant = 'accent',
		size = 'md',
		type = 'button',
		disabled = false,
		children,
		onclick,
		...rest
	}: {
		variant?: Variant;
		size?: Size;
		type?: 'button' | 'submit' | 'reset';
		disabled?: boolean;
		children: Snippet;
		onclick?: (e: MouseEvent) => void;
		[key: string]: unknown;
	} = $props();

	// Map semantic variant → (background token, foreground token).
	const fills: Record<Variant, { bg: string; fg: string }> = {
		accent: { bg: 'var(--accent)', fg: 'var(--accent-fg)' },
		neutral: { bg: 'var(--surface-2)', fg: 'var(--fg)' },
		ghost: { bg: 'transparent', fg: 'var(--fg)' },
		success: { bg: 'var(--success)', fg: 'var(--success-fg)' },
		warn: { bg: 'var(--warn)', fg: 'var(--warn-fg)' },
		danger: { bg: 'var(--danger)', fg: 'var(--danger-fg)' }
	};
	const pad: Record<Size, string> = {
		sm: 'var(--space-1) var(--space-3)',
		md: 'var(--space-2) var(--space-4)',
		lg: 'var(--space-3) var(--space-5)'
	};

	const fill = $derived(fills[variant]);
</script>

<button
	class="btn"
	class:ghost={variant === 'ghost'}
	{type}
	{disabled}
	style:--_bg={fill.bg}
	style:--_fg={fill.fg}
	style:--_pad={pad[size]}
	{onclick}
	{...rest}
>
	{@render children()}
</button>

<style>
	.btn {
		display: inline-flex;
		align-items: center;
		justify-content: center;
		gap: var(--space-2);
		padding: var(--_pad);
		background: var(--_bg);
		color: var(--_fg);
		font: inherit;
		font-weight: var(--font-weight-bold);
		border: var(--border-width) solid var(--border-color);
		border-radius: var(--radius-md);
		box-shadow: var(--shadow-sm);
		cursor: pointer;
		transition: var(--transition);
	}

	.ghost {
		box-shadow: none;
		border-color: transparent;
	}

	.btn:hover:not(:disabled) {
		filter: brightness(1.08);
		transform: translateY(var(--hover-lift));
		box-shadow: var(--shadow-hover), var(--hover-glow);
	}
	.btn:active:not(:disabled) {
		transform: scale(var(--press-scale));
		filter: brightness(0.96);
	}
	.btn:focus-visible {
		outline: none;
		box-shadow: var(--focus-ring);
	}
	.btn:disabled {
		opacity: 0.5;
		cursor: not-allowed;
	}
</style>

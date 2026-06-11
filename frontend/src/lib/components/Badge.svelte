<script lang="ts">
	import type { Snippet } from 'svelte';

	type Variant = 'neutral' | 'accent' | 'success' | 'warn' | 'danger' | 'info';

	let {
		variant = 'neutral',
		children,
		...rest
	}: { variant?: Variant; children: Snippet; [key: string]: unknown } = $props();

	const bg: Record<Variant, string> = {
		neutral: 'var(--surface-2)',
		accent: 'var(--accent)',
		success: 'var(--success)',
		warn: 'var(--warn)',
		danger: 'var(--danger)',
		info: 'var(--info)'
	};
	const fg: Record<Variant, string> = {
		neutral: 'var(--fg)',
		accent: 'var(--accent-fg)',
		success: 'var(--success-fg)',
		warn: 'var(--warn-fg)',
		danger: 'var(--danger-fg)',
		info: 'var(--info-fg)'
	};
</script>

<span class="badge" style:--_bg={bg[variant]} style:--_fg={fg[variant]} {...rest}>
	{@render children()}
</span>

<style>
	.badge {
		display: inline-flex;
		align-items: center;
		padding: 0 var(--space-2);
		min-height: 1.4rem;
		font-size: 0.78rem;
		font-weight: var(--font-weight-bold);
		background: var(--_bg);
		color: var(--_fg);
		border: var(--border-width) solid var(--border-color);
		border-radius: var(--radius-full);
		white-space: nowrap;
	}
</style>

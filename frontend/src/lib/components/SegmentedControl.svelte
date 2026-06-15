<script lang="ts">
	// A small exclusive-choice toggle (like iOS segmented control). Generic and
	// token-only — reusable anywhere a handful of mutually-exclusive options are
	// picked (range mode, view switch, filters). Reads only design tokens.
	type Option = { value: string; label: string };

	let {
		options,
		value = $bindable(''),
		onchange
	}: {
		options: Option[];
		value?: string;
		onchange?: (value: string) => void;
	} = $props();

	function pick(v: string) {
		value = v;
		onchange?.(v);
	}
</script>

<div class="seg" role="tablist">
	{#each options as opt (opt.value)}
		<button
			class="item"
			class:active={value === opt.value}
			role="tab"
			aria-selected={value === opt.value}
			onclick={() => pick(opt.value)}
		>
			{opt.label}
		</button>
	{/each}
</div>

<style>
	.seg {
		display: inline-flex;
		gap: var(--space-1);
		padding: var(--space-1);
		background: color-mix(
			in srgb,
			var(--surface-2) calc(var(--surface-alpha) * 100%),
			transparent
		);
		border: var(--border-width) solid var(--border-color);
		border-radius: var(--radius-full);
	}
	.item {
		appearance: none;
		border: none;
		background: transparent;
		color: var(--muted);
		font: inherit;
		font-weight: var(--font-weight-bold);
		padding: var(--space-1) var(--space-3);
		border-radius: var(--radius-full);
		cursor: pointer;
		white-space: nowrap;
		transition:
			background var(--motion-fast) var(--motion-ease),
			color var(--motion-fast) var(--motion-ease);
	}
	.item:hover {
		color: var(--fg);
	}
	.item.active {
		background: var(--accent);
		color: var(--accent-fg);
		box-shadow: var(--shadow-sm);
	}
	.item:focus-visible {
		outline: 2px solid var(--accent);
		outline-offset: 2px;
	}
</style>

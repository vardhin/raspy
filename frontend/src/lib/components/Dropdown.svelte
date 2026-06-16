<script lang="ts">
	// Token-only dropdown menu, usable anywhere. Provide `items` (each with a
	// label, optional icon, optional `danger` tone, and an `onselect`), or a
	// `menu` snippet for fully custom content. The trigger is a `trigger` snippet
	// if given, else a labelled button. Opens a popover anchored to the trigger;
	// closes on selection, outside click, or Escape.
	import type { Snippet } from 'svelte';
	import Icon from './Icon.svelte';

	type Item = {
		label: string;
		icon?: string;
		danger?: boolean;
		disabled?: boolean;
		onselect?: () => void;
	};

	let {
		items = [],
		label = 'Menu',
		align = 'start',
		open = $bindable(false),
		trigger,
		menu
	}: {
		items?: Item[];
		label?: string;
		align?: 'start' | 'end';
		open?: boolean;
		trigger?: Snippet<[{ toggle: () => void; open: boolean }]>;
		menu?: Snippet<[{ close: () => void }]>;
	} = $props();

	let root: HTMLElement;

	function toggle() {
		open = !open;
	}
	function close() {
		open = false;
	}
	function choose(item: Item) {
		if (item.disabled) return;
		item.onselect?.();
		close();
	}

	function onWindowDown(e: MouseEvent) {
		if (open && root && !root.contains(e.target as Node)) close();
	}
	function onKey(e: KeyboardEvent) {
		if (e.key === 'Escape' && open) close();
	}
</script>

<svelte:window onmousedown={onWindowDown} onkeydown={onKey} />

<div class="dropdown" bind:this={root}>
	{#if trigger}
		{@render trigger({ toggle, open })}
	{:else}
		<button class="trigger" aria-haspopup="menu" aria-expanded={open} onclick={toggle}>
			<span>{label}</span>
			<span class="caret" class:open><Icon name="chevron-down" size={16} /></span>
		</button>
	{/if}

	{#if open}
		<div class="menu {align}" role="menu">
			{#if menu}
				{@render menu({ close })}
			{:else}
				{#each items as item (item.label)}
					<button
						class="item"
						class:danger={item.danger}
						role="menuitem"
						disabled={item.disabled}
						onclick={() => choose(item)}
					>
						{#if item.icon}<Icon name={item.icon} size={16} />{/if}
						<span>{item.label}</span>
					</button>
				{/each}
			{/if}
		</div>
	{/if}
</div>

<style>
	.dropdown {
		position: relative;
		display: inline-flex;
	}
	.trigger {
		display: inline-flex;
		align-items: center;
		gap: var(--space-2);
		font: inherit;
		font-weight: var(--font-weight-bold);
		color: var(--fg);
		background: color-mix(
			in srgb,
			var(--surface-2) calc(var(--surface-alpha) * 100%),
			transparent
		);
		border: var(--border-width) solid var(--border-color);
		border-radius: var(--radius-md);
		box-shadow: var(--shadow-sm);
		padding: var(--space-2) var(--space-3);
		cursor: pointer;
		transition: border-color var(--motion-fast) var(--motion-ease);
	}
	.trigger:hover {
		border-color: var(--accent);
	}
	.caret {
		display: inline-flex;
		color: var(--muted);
		transition: transform var(--motion-fast) var(--motion-ease);
	}
	.caret.open {
		transform: rotate(180deg);
	}
	.menu {
		position: absolute;
		top: calc(100% + var(--space-1));
		z-index: 70;
		min-width: 11rem;
		display: flex;
		flex-direction: column;
		gap: 2px;
		padding: var(--space-1);
		background: color-mix(
			in srgb,
			var(--surface-2) calc(var(--surface-alpha) * 100%),
			transparent
		);
		backdrop-filter: blur(var(--blur));
		-webkit-backdrop-filter: blur(var(--blur));
		border: var(--border-width) solid var(--border-color);
		border-radius: var(--radius-md);
		box-shadow: var(--shadow-lg);
	}
	.menu.start {
		left: 0;
	}
	.menu.end {
		right: 0;
	}
	.item {
		display: flex;
		align-items: center;
		gap: var(--space-2);
		width: 100%;
		text-align: left;
		font: inherit;
		font-weight: var(--font-weight-normal);
		color: var(--fg);
		background: transparent;
		border: none;
		border-radius: var(--radius-sm);
		padding: var(--space-2) var(--space-2);
		cursor: pointer;
		white-space: nowrap;
		transition: background var(--motion-fast) var(--motion-ease);
	}
	.item:hover:not(:disabled) {
		background: var(--surface);
	}
	.item.danger {
		color: var(--danger);
	}
	.item:disabled {
		opacity: 0.5;
		cursor: not-allowed;
	}
	.item:focus-visible {
		outline: 2px solid var(--accent);
		outline-offset: -2px;
	}
</style>

<script lang="ts">
	// Standalone token-only checkbox. A custom-drawn box (so it themes with any
	// color × concept — native checkboxes can't be fully styled) wrapping a real
	// <input> for accessibility & form semantics. `checked` is bindable.
	import Icon from './Icon.svelte';

	let {
		checked = $bindable(false),
		label = '',
		disabled = false,
		onchange,
		...rest
	}: {
		checked?: boolean;
		label?: string;
		disabled?: boolean;
		onchange?: (checked: boolean) => void;
		[key: string]: unknown;
	} = $props();

	function onInput(e: Event) {
		checked = (e.target as HTMLInputElement).checked;
		onchange?.(checked);
	}
</script>

<label class="checkbox" class:disabled>
	<input type="checkbox" bind:checked {disabled} onchange={onInput} {...rest} />
	<span class="box" aria-hidden="true">
		{#if checked}<Icon name="check" size={14} />{/if}
	</span>
	{#if label}<span class="label">{label}</span>{/if}
</label>

<style>
	.checkbox {
		display: inline-flex;
		align-items: center;
		gap: var(--space-2);
		cursor: pointer;
		color: var(--fg);
		user-select: none;
	}
	.checkbox.disabled {
		cursor: not-allowed;
		opacity: 0.55;
	}
	/* Visually hidden but still focusable/accessible. */
	input {
		position: absolute;
		width: 1px;
		height: 1px;
		opacity: 0;
		margin: 0;
		pointer-events: none;
	}
	.box {
		display: inline-flex;
		align-items: center;
		justify-content: center;
		width: 1.2rem;
		height: 1.2rem;
		flex: none;
		color: var(--accent-fg);
		background: color-mix(
			in srgb,
			var(--surface-2) calc(var(--surface-alpha) * 100%),
			transparent
		);
		border: var(--border-width) solid var(--border-color);
		border-radius: var(--radius-sm);
		box-shadow: var(--shadow-sm);
		transition:
			background var(--motion-fast) var(--motion-ease),
			border-color var(--motion-fast) var(--motion-ease);
	}
	input:checked + .box {
		background: var(--accent);
		border-color: var(--accent);
	}
	input:focus-visible + .box {
		outline: 2px solid var(--accent);
		outline-offset: 2px;
	}
	.label {
		font-weight: var(--font-weight-normal);
	}
</style>

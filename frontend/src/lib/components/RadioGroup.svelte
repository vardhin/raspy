<script lang="ts">
	// Token-only single-choice radio group. Pass `options` and bind `value`. Each
	// option is a custom-drawn dot (native radios can't be fully themed) over a
	// real radio input for a11y & keyboard arrow navigation (same `name`).
	type Option = { value: string; label: string; disabled?: boolean };

	let {
		options,
		value = $bindable(''),
		name = `radio-${Math.random().toString(36).slice(2, 9)}`,
		direction = 'column',
		onchange
	}: {
		options: Option[];
		value?: string;
		name?: string;
		direction?: 'row' | 'column';
		onchange?: (value: string) => void;
	} = $props();

	function pick(v: string) {
		value = v;
		onchange?.(v);
	}
</script>

<div class="group" style:flex-direction={direction} role="radiogroup">
	{#each options as opt (opt.value)}
		<label class="opt" class:disabled={opt.disabled}>
			<input
				type="radio"
				{name}
				value={opt.value}
				checked={value === opt.value}
				disabled={opt.disabled}
				onchange={() => pick(opt.value)}
			/>
			<span class="dot" aria-hidden="true"></span>
			<span class="label">{opt.label}</span>
		</label>
	{/each}
</div>

<style>
	.group {
		display: flex;
		gap: var(--space-2);
		flex-wrap: wrap;
	}
	.opt {
		display: inline-flex;
		align-items: center;
		gap: var(--space-2);
		cursor: pointer;
		color: var(--fg);
		user-select: none;
	}
	.opt.disabled {
		cursor: not-allowed;
		opacity: 0.55;
	}
	input {
		position: absolute;
		width: 1px;
		height: 1px;
		opacity: 0;
		margin: 0;
		pointer-events: none;
	}
	.dot {
		position: relative;
		display: inline-flex;
		width: 1.2rem;
		height: 1.2rem;
		flex: none;
		background: color-mix(
			in srgb,
			var(--surface-2) calc(var(--surface-alpha) * 100%),
			transparent
		);
		border: var(--border-width) solid var(--border-color);
		border-radius: var(--radius-full);
		box-shadow: var(--shadow-sm);
		transition: border-color var(--motion-fast) var(--motion-ease);
	}
	.dot::after {
		content: '';
		position: absolute;
		inset: 0;
		margin: auto;
		width: 0.6rem;
		height: 0.6rem;
		border-radius: var(--radius-full);
		background: var(--accent);
		transform: scale(0);
		transition: transform var(--motion-fast) var(--motion-ease);
	}
	input:checked + .dot {
		border-color: var(--accent);
	}
	input:checked + .dot::after {
		transform: scale(1);
	}
	input:focus-visible + .dot {
		outline: 2px solid var(--accent);
		outline-offset: 2px;
	}
	.label {
		font-weight: var(--font-weight-normal);
	}
</style>

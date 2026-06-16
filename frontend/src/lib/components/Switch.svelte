<script lang="ts">
	// Token-only on/off toggle. A real checkbox input (a11y + forms) drawn as a
	// sliding track + knob. `checked` is bindable. Reads only design tokens, so the
	// track/knob re-skin with any color × concept.
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

<label class="switch" class:disabled>
	<input type="checkbox" role="switch" bind:checked {disabled} onchange={onInput} {...rest} />
	<span class="track" aria-hidden="true"><span class="knob"></span></span>
	{#if label}<span class="label">{label}</span>{/if}
</label>

<style>
	.switch {
		display: inline-flex;
		align-items: center;
		gap: var(--space-2);
		cursor: pointer;
		color: var(--fg);
		user-select: none;
	}
	.switch.disabled {
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
	.track {
		position: relative;
		display: inline-flex;
		align-items: center;
		width: 2.6rem;
		height: 1.45rem;
		flex: none;
		padding: 2px;
		background: color-mix(
			in srgb,
			var(--surface-2) calc(var(--surface-alpha) * 100%),
			transparent
		);
		border: var(--border-width) solid var(--border-color);
		border-radius: var(--radius-full);
		box-shadow: var(--shadow-sm);
		transition: background var(--motion-base) var(--motion-ease);
	}
	.knob {
		width: 1.05rem;
		height: 1.05rem;
		background: var(--muted);
		border-radius: var(--radius-full);
		box-shadow: var(--shadow-sm);
		transition:
			transform var(--motion-base) var(--motion-ease),
			background var(--motion-base) var(--motion-ease);
	}
	input:checked + .track {
		background: var(--accent);
		border-color: var(--accent);
	}
	input:checked + .track .knob {
		transform: translateX(1.15rem);
		background: var(--accent-fg);
	}
	input:focus-visible + .track {
		outline: 2px solid var(--accent);
		outline-offset: 2px;
	}
	.label {
		font-weight: var(--font-weight-normal);
	}
</style>

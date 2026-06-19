<script lang="ts">
	// One form primitive covering text/number/textarea/select/checkbox. Label +
	// control, all token-styled. `value` is bindable.
	import Icon from './Icon.svelte';

	type FieldType =
		| 'text'
		| 'number'
		| 'password'
		| 'email'
		| 'date'
		| 'datetime-local'
		| 'time'
		| 'textarea'
		| 'select'
		| 'checkbox';

	let {
		type = 'text',
		label = '',
		placeholder = '',
		options = [],
		value = $bindable(),
		...rest
	}: {
		type?: FieldType;
		label?: string;
		placeholder?: string;
		options?: { value: string; label: string }[];
		value?: string | number | boolean;
		[key: string]: unknown;
	} = $props();
</script>

<label class="field" class:inline={type === 'checkbox'}>
	{#if label}<span class="field-label">{label}</span>{/if}

	{#if type === 'textarea'}
		<textarea class="control" {placeholder} bind:value {...rest}></textarea>
	{:else if type === 'select'}
		<select class="control" bind:value {...rest}>
			{#each options as opt (opt.value)}
				<option value={opt.value}>{opt.label}</option>
			{/each}
		</select>
	{:else if type === 'checkbox'}
		<!-- Custom-drawn box (matches Checkbox.svelte) so concepts (radius/border/
		     shadow) apply — native checkboxes can't be themed past accent-color. -->
		<input class="cb-input" type="checkbox" bind:checked={value as boolean} {...rest} />
		<span class="cb-box" aria-hidden="true">
			{#if value}<Icon name="check" size={14} />{/if}
		</span>
	{:else}
		<input class="control" {type} {placeholder} bind:value {...rest} />
	{/if}
</label>

<style>
	.field {
		display: flex;
		flex-direction: column;
		gap: var(--space-1);
		min-width: 0;
	}
	.field.inline {
		flex-direction: row-reverse;
		align-items: center;
		justify-content: flex-end;
		gap: var(--space-2);
		cursor: pointer;
	}
	.field-label {
		font-size: 0.85rem;
		font-weight: var(--font-weight-bold);
		color: var(--muted);
	}
	.control {
		font: inherit;
		width: 100%;
		min-width: 0;
		color: var(--fg);
		background: color-mix(
			in srgb,
			var(--surface-2) calc(var(--surface-alpha) * 100%),
			transparent
		);
		border: var(--border-width) solid var(--border-color);
		border-radius: var(--radius-md);
		padding: var(--space-2) var(--space-3);
		box-shadow: var(--shadow-sm);
		transition: var(--transition);
	}
	.control:hover {
		border-color: color-mix(in srgb, var(--accent) 55%, var(--border-color));
	}
	.control:focus {
		outline: none;
		border-color: var(--accent);
		box-shadow: var(--focus-ring);
	}
	textarea.control {
		min-height: 5rem;
		resize: vertical;
	}
	/* Custom checkbox: hide the native input, draw a token-styled box so concepts
	   (radius/border/shadow) apply. Mirrors Checkbox.svelte. */
	.cb-input {
		position: absolute;
		width: 1px;
		height: 1px;
		opacity: 0;
		margin: 0;
		pointer-events: none;
	}
	.cb-box {
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
	.cb-input:checked + .cb-box {
		background: var(--accent);
		border-color: var(--accent);
	}
	.cb-input:focus-visible + .cb-box {
		outline: none;
		box-shadow: var(--focus-ring);
	}
</style>

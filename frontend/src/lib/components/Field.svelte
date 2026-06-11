<script lang="ts">
	// One form primitive covering text/number/textarea/select/checkbox. Label +
	// control, all token-styled. `value` is bindable.
	type FieldType = 'text' | 'number' | 'password' | 'email' | 'textarea' | 'select' | 'checkbox';

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
		<input class="checkbox" type="checkbox" bind:checked={value as boolean} {...rest} />
	{:else}
		<input class="control" {type} {placeholder} bind:value {...rest} />
	{/if}
</label>

<style>
	.field {
		display: flex;
		flex-direction: column;
		gap: var(--space-1);
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
		transition: border-color var(--motion-fast) var(--motion-ease);
	}
	.control:focus {
		outline: none;
		border-color: var(--accent);
	}
	textarea.control {
		min-height: 5rem;
		resize: vertical;
	}
	.checkbox {
		width: 1.15rem;
		height: 1.15rem;
		accent-color: var(--accent);
	}
</style>

<script lang="ts">
	// Two independent selectors — color axis and concept axis. Live + persisted
	// via the theme store. Auto-lists whatever themes exist (no hardcoding).
	import { colorThemes, conceptThemes } from '$lib/themes/registry';
	import { theme } from '$lib/themes/store.svelte';
</script>

<div class="picker">
	<label>
		<span>Color</span>
		<select value={theme.colorId} onchange={(e) => theme.setColor(e.currentTarget.value)}>
			{#each colorThemes as t (t.id)}
				<option value={t.id}>{t.name}</option>
			{/each}
		</select>
	</label>

	<label>
		<span>Concept</span>
		<select value={theme.conceptId} onchange={(e) => theme.setConcept(e.currentTarget.value)}>
			{#each conceptThemes as t (t.id)}
				<option value={t.id}>{t.name}</option>
			{/each}
		</select>
	</label>
</div>

<style>
	.picker {
		display: flex;
		gap: var(--space-3);
		flex-wrap: wrap;
	}
	label {
		display: flex;
		flex-direction: column;
		gap: var(--space-1);
		font-size: 0.8rem;
		font-weight: var(--font-weight-bold);
		color: var(--muted);
	}
	select {
		font: inherit;
		color: var(--fg);
		background: var(--surface-2);
		border: var(--border-width) solid var(--border-color);
		border-radius: var(--radius-md);
		padding: var(--space-2) var(--space-3);
		box-shadow: var(--shadow-sm);
	}
</style>

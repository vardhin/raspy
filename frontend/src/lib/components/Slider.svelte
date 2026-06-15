<script lang="ts">
	// A token-styled range slider. Generic and reusable for any numeric setting
	// (the calendar zoom bar, volumes, opacities…). Optional leading/trailing
	// icon snippets. Reads only design tokens so it re-skins with any theme.
	import type { Snippet } from 'svelte';

	let {
		value = $bindable(0),
		min = 0,
		max = 100,
		step = 1,
		label,
		lead,
		trail,
		oninput
	}: {
		value?: number;
		min?: number;
		max?: number;
		step?: number;
		label?: string;
		lead?: Snippet;
		trail?: Snippet;
		oninput?: (value: number) => void;
	} = $props();

	const pct = $derived(((value - min) / (max - min)) * 100);

	function onInput(e: Event) {
		value = Number((e.target as HTMLInputElement).value);
		oninput?.(value);
	}
</script>

<div class="slider">
	{#if lead}<span class="cap">{@render lead()}</span>{/if}
	<input
		type="range"
		{min}
		{max}
		{step}
		{value}
		aria-label={label}
		style:--_pct="{pct}%"
		oninput={onInput}
	/>
	{#if trail}<span class="cap">{@render trail()}</span>{/if}
</div>

<style>
	.slider {
		display: inline-flex;
		align-items: center;
		gap: var(--space-2);
		color: var(--muted);
	}
	.cap {
		display: inline-flex;
		align-items: center;
	}
	input[type='range'] {
		appearance: none;
		-webkit-appearance: none;
		width: 100%;
		min-width: 96px;
		height: 6px;
		border-radius: var(--radius-full);
		/* Filled portion via --accent up to the thumb, track after. */
		background: linear-gradient(
			to right,
			var(--accent) var(--_pct),
			var(--surface-2) var(--_pct)
		);
		border: var(--border-width) solid var(--border-color);
		cursor: pointer;
		outline: none;
	}
	input[type='range']::-webkit-slider-thumb {
		-webkit-appearance: none;
		width: 16px;
		height: 16px;
		border-radius: var(--radius-full);
		background: var(--accent);
		border: var(--border-width) solid var(--border-color);
		box-shadow: var(--shadow-sm);
		cursor: pointer;
	}
	input[type='range']::-moz-range-thumb {
		width: 16px;
		height: 16px;
		border-radius: var(--radius-full);
		background: var(--accent);
		border: var(--border-width) solid var(--border-color);
		box-shadow: var(--shadow-sm);
		cursor: pointer;
	}
	input[type='range']:focus-visible {
		outline: 2px solid var(--accent);
		outline-offset: 3px;
	}
</style>

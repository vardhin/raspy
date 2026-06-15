<script lang="ts">
	// A decorative sparkly star field. Pure CSS twinkle (no JS animation loop), so
	// it's cheap. Generic + reusable as a magical backdrop for any view. Stars are
	// drawn in the current text color (token) at low alpha, so they read on any
	// theme; place it behind content with `position: absolute; inset: 0`.
	import { untrack } from 'svelte';

	let {
		count = 80,
		density = 1
	}: {
		/** Number of stars. */
		count?: number;
		/** Multiplier on star size/brightness. */
		density?: number;
	} = $props();

	type Star = { x: number; y: number; size: number; delay: number; dur: number };

	// Random layout, generated once from the initial props (untracked is fine —
	// the field is decorative and doesn't need to react to prop changes).
	const initialCount = untrack(() => count);
	const initialDensity = untrack(() => density);
	const stars: Star[] = Array.from({ length: initialCount }, () => ({
		x: Math.random() * 100,
		y: Math.random() * 100,
		size: (Math.random() * 1.6 + 0.6) * initialDensity,
		delay: Math.random() * 4,
		dur: Math.random() * 3 + 2
	}));
</script>

<div class="field" aria-hidden="true">
	{#each stars as s, i (i)}
		<span
			class="star"
			style:left="{s.x}%"
			style:top="{s.y}%"
			style:--_s="{s.size}px"
			style:--_delay="{s.delay}s"
			style:--_dur="{s.dur}s"
		></span>
	{/each}
</div>

<style>
	.field {
		position: absolute;
		inset: 0;
		overflow: hidden;
		pointer-events: none;
	}
	.star {
		position: absolute;
		width: var(--_s);
		height: var(--_s);
		border-radius: 50%;
		background: var(--fg);
		box-shadow: 0 0 calc(var(--_s) * 2) var(--fg);
		opacity: 0.15;
		animation: twinkle var(--_dur) ease-in-out var(--_delay) infinite;
	}
	@keyframes twinkle {
		0%,
		100% {
			opacity: 0.1;
			transform: scale(0.8);
		}
		50% {
			opacity: 0.85;
			transform: scale(1.25);
		}
	}
	@media (prefers-reduced-motion: reduce) {
		.star {
			animation: none;
			opacity: 0.4;
		}
	}
</style>

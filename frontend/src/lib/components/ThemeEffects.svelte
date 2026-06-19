<script lang="ts">
	// Single full-viewport background effects layer for the app shell. Reads the
	// active concept's `effects` from the theme store and renders one CSS-driven
	// layer per spec, all keyed to --accent so they match the live palette.
	//
	// Fixed, behind everything, pointer-events:none. Disabled entirely when the user
	// turns animations off (theme.setAnimations) or the OS requests reduced motion.
	import { theme } from '$lib/themes/store.svelte';
	import type { EffectSpec } from '$lib/themes/types';

	// Concept effects are reactive: switching concept swaps the layers live.
	const effects = $derived<EffectSpec[]>(theme.animations ? (theme.concept.effects ?? []) : []);

	// Per-effect CSS custom props (opacity / speed) with sensible defaults.
	function vars(e: EffectSpec): string {
		const op = 'opacity' in e && e.opacity != null ? e.opacity : 0.5;
		const sp = 'speed' in e && e.speed != null ? e.speed : 1;
		// speed is a multiplier; higher = faster → shorter duration.
		return `--fx-op:${op};--fx-dur:${(20 / sp).toFixed(2)}s`;
	}
</script>

<div class="fx" aria-hidden="true">
	{#each effects as e, i (e.kind + i)}
		<div class="layer {e.kind}" style={vars(e)}></div>
	{/each}
</div>

<style>
	.fx {
		position: fixed;
		inset: 0;
		z-index: 0;
		pointer-events: none;
		overflow: hidden;
	}
	.layer {
		position: absolute;
		inset: -20%;
		opacity: var(--fx-op);
	}

	/* Aurora: layered conic/radial accent gradients drifting across the viewport. */
	.aurora {
		background:
			radial-gradient(
				40% 60% at 20% 30%,
				color-mix(in srgb, var(--accent) 70%, transparent),
				transparent 70%
			),
			radial-gradient(
				50% 50% at 80% 20%,
				color-mix(in srgb, var(--info) 60%, transparent),
				transparent 70%
			),
			radial-gradient(
				45% 55% at 60% 80%,
				color-mix(in srgb, var(--success) 55%, transparent),
				transparent 70%
			);
		filter: blur(60px) saturate(1.2);
		animation: aurora-drift var(--fx-dur) ease-in-out infinite alternate;
	}
	@keyframes aurora-drift {
		0% {
			transform: translate3d(-6%, -4%, 0) rotate(0deg) scale(1.1);
		}
		50% {
			transform: translate3d(4%, 3%, 0) rotate(8deg) scale(1.25);
		}
		100% {
			transform: translate3d(-3%, 5%, 0) rotate(-6deg) scale(1.15);
		}
	}

	/* Breathe: a soft accent vignette pulsing scale + opacity. */
	.breathe {
		background: radial-gradient(
			60% 60% at 50% 45%,
			color-mix(in srgb, var(--accent) 35%, transparent),
			transparent 75%
		);
		filter: blur(40px);
		animation: breathe var(--fx-dur) ease-in-out infinite;
	}
	@keyframes breathe {
		0%,
		100% {
			transform: scale(1);
			opacity: calc(var(--fx-op) * 0.6);
		}
		50% {
			transform: scale(1.15);
			opacity: var(--fx-op);
		}
	}

	/* Orbit: an accent glow circling the viewport. */
	.orbit {
		background: radial-gradient(
			circle at 50% 50%,
			color-mix(in srgb, var(--accent) 80%, transparent),
			transparent 60%
		);
		width: 50vmax;
		height: 50vmax;
		inset: auto;
		top: 25%;
		left: 25%;
		filter: blur(70px);
		transform-origin: 50% 50%;
		animation: orbit var(--fx-dur) linear infinite;
	}
	@keyframes orbit {
		from {
			transform: rotate(0deg) translateX(20vmax) rotate(0deg);
		}
		to {
			transform: rotate(360deg) translateX(20vmax) rotate(-360deg);
		}
	}

	/* Scanlines: CRT horizontal lines. */
	.scanlines {
		background: repeating-linear-gradient(
			to bottom,
			color-mix(in srgb, var(--fg) 12%, transparent) 0px,
			color-mix(in srgb, var(--fg) 12%, transparent) 1px,
			transparent 1px,
			transparent 4px
		);
		animation: scan var(--fx-dur) linear infinite;
	}
	@keyframes scan {
		from {
			transform: translateY(0);
		}
		to {
			transform: translateY(4px);
		}
	}

	/* Grid: retro perspective grid keyed to the accent. */
	.grid {
		background:
			linear-gradient(
					color-mix(in srgb, var(--accent) 35%, transparent) 1px,
					transparent 1px
				)
				0 0 / 48px 48px,
			linear-gradient(
					to right,
					color-mix(in srgb, var(--accent) 35%, transparent) 1px,
					transparent 1px
				)
				0 0 / 48px 48px;
		mask-image: linear-gradient(to top, black, transparent 70%);
		-webkit-mask-image: linear-gradient(to top, black, transparent 70%);
		animation: grid-scroll var(--fx-dur) linear infinite;
	}
	@keyframes grid-scroll {
		from {
			background-position:
				0 0,
				0 0;
		}
		to {
			background-position:
				0 48px,
				0 0;
		}
	}

	/* Noise: subtle animated film grain via fractal SVG. */
	.noise {
		background-image: url("data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' width='120' height='120'%3E%3Cfilter id='n'%3E%3CfeTurbulence type='fractalNoise' baseFrequency='0.8' numOctaves='2'/%3E%3C/filter%3E%3Crect width='100%25' height='100%25' filter='url(%23n)' opacity='0.5'/%3E%3C/svg%3E");
		animation: noise var(--fx-dur) steps(6) infinite;
	}
	@keyframes noise {
		0% {
			transform: translate(0, 0);
		}
		50% {
			transform: translate(-2%, 1%);
		}
		100% {
			transform: translate(1%, -2%);
		}
	}

	/* Honour the OS reduced-motion preference regardless of the app toggle. */
	@media (prefers-reduced-motion: reduce) {
		.layer {
			animation: none !important;
		}
	}
</style>

<script lang="ts">
	// One section of an `Accordion` group: a clickable header row and a collapsible
	// body. Rendered as a divider-separated row inside the group's shared container
	// (no own border/radius — the group owns the card chrome). Token-only styling.
	//
	// The expand/collapse is a real height animation (CSS can't animate to `auto`).
	// Two strategies:
	//
	//   1. measured — when `bodyText` is given, the open height is computed with
	//      @chenglou/pretext: it lays out the wrapped text purely arithmetically, with
	//      NO DOM read (no getBoundingClientRect/offsetHeight, no reflow). We then
	//      animate `height` from 0 to that exact pixel value. On width change we just
	//      re-run the cheap `layout()` — `prepare()` stays cached per text. This is what
	//      keeps long mail bodies sized correctly at every screen width.
	//
	//      Font, line-height, and the body's padding/border (the "chrome") are read
	//      once via getComputedStyle when the body mounts — a single read, never in the
	//      animation/resize hot path — so callers don't hardcode theme-dependent pixels.
	//
	//   2. fallback — with no `bodyText`, animate `grid-template-rows: 0fr → 1fr`,
	//      which collapses to content height without measuring anything. Keeps the
	//      component generic for non-text bodies.
	import type { Snippet } from 'svelte';
	import { prepare, layout, type PreparedText } from '@chenglou/pretext';

	let {
		open = false,
		ontoggle,
		header,
		children,
		// Provide the body's plain text to enable pretext-measured animation. The text
		// element inside the body must be the direct measurement target (we read its
		// computed font/line-height/padding).
		bodyText
	}: {
		open?: boolean;
		ontoggle?: () => void;
		header: Snippet;
		children: Snippet;
		bodyText?: string;
	} = $props();

	const measured = $derived(bodyText != null);

	// Computed text metrics, read once from the live text element.
	let font = $state('');
	let lineHeight = $state(0);
	let bodyExtra = $state(0); // the text element's own vertical padding + border + margin

	// One-time precompute per text/font; cheap to recompute height from it on resize.
	let prepared: PreparedText | null = $state(null);
	$effect(() => {
		if (!measured || !font || lineHeight <= 0) {
			prepared = null;
			return;
		}
		prepared = prepare(bodyText ?? '', font, { whiteSpace: 'pre-wrap' });
	});

	// The body wrapper. We measure the text element inside it — the descendant the
	// caller marks with `data-ac-text` (e.g. the <pre>), falling back to the wrapper.
	let bodyEl: HTMLElement | undefined = $state();
	let contentWidth = $state(0);
	const textEl = $derived(bodyEl?.querySelector<HTMLElement>('[data-ac-text]') ?? bodyEl);

	function readMetrics(el: HTMLElement) {
		const cs = getComputedStyle(el);
		const fontSize = parseFloat(cs.fontSize) || 16;
		font = cs.font && cs.font.trim() !== '' ? cs.font : `${cs.fontWeight} ${cs.fontSize} ${cs.fontFamily}`;
		const lh = parseFloat(cs.lineHeight);
		lineHeight = Number.isFinite(lh) ? lh : fontSize * 1.5;
		const pt = parseFloat(cs.paddingTop) || 0;
		const pb = parseFloat(cs.paddingBottom) || 0;
		const bt = parseFloat(cs.borderTopWidth) || 0;
		const bb = parseFloat(cs.borderBottomWidth) || 0;
		const mt = parseFloat(cs.marginTop) || 0;
		const mb = parseFloat(cs.marginBottom) || 0;
		bodyExtra = pt + pb + bt + bb + mt + mb;
	}

	$effect(() => {
		const el = textEl;
		if (!measured || !el) return;
		readMetrics(el);
		const ro = new ResizeObserver((entries) => {
			const w = entries[0]?.contentRect.width ?? 0;
			if (w > 0) contentWidth = w;
		});
		ro.observe(el);
		return () => ro.disconnect();
	});

	const openHeight = $derived.by(() => {
		if (!measured || !prepared || contentWidth <= 0 || lineHeight <= 0) return null;
		// contentWidth is the text element's content-box width (padding already
		// excluded by ResizeObserver) — exactly pretext's wrapping width.
		const { height } = layout(prepared, contentWidth, lineHeight);
		return height + bodyExtra;
	});

	// The style driving the animation. When measured, animate explicit pixel height;
	// otherwise fall back to the grid-rows technique.
	const regionStyle = $derived.by(() => {
		if (!measured) return '';
		if (!open) return 'height: 0px;';
		// Before the first measurement lands, allow natural height so content is never
		// clipped; once we have a number, pin it for a smooth, exact animation.
		return openHeight == null ? 'height: auto;' : `height: ${openHeight}px;`;
	});
</script>

<div class="ac-item" class:open class:measured>
	<button class="ac-header" type="button" aria-expanded={open} onclick={() => ontoggle?.()}>
		{@render header()}
	</button>

	{#if measured}
		<div class="ac-region measured-region" style={regionStyle} aria-hidden={!open}>
			<div class="ac-body" bind:this={bodyEl}>
				{@render children()}
			</div>
		</div>
	{:else}
		<div class="ac-region grid-region" aria-hidden={!open}>
			<div class="ac-body">
				{@render children()}
			</div>
		</div>
	{/if}
</div>

<style>
	.ac-item {
		/* Rows of a single group: a top divider separates each from the previous
		   one. The group's container owns the outer border/radius/background. */
		border-top: var(--border-width) solid var(--border-color);
		transition: background var(--motion-fast) var(--motion-ease);
	}
	/* First item has no top divider — the group's own border is the top edge. */
	.ac-item:first-child {
		border-top: none;
	}
	.ac-item.open {
		background: color-mix(in srgb, var(--accent) 6%, transparent);
	}
	.ac-header {
		display: block;
		width: 100%;
		text-align: left;
		background: transparent;
		border: none;
		color: var(--fg);
		font: inherit;
		cursor: pointer;
		padding: 0;
	}
	.ac-header:hover {
		background: color-mix(in srgb, var(--accent) 8%, transparent);
	}
	.ac-header:focus-visible {
		outline: 2px solid var(--accent);
		outline-offset: -2px;
	}

	/* Strategy 1: explicit-height animation (pretext-measured). */
	.measured-region {
		overflow: hidden;
		transition: height var(--motion-base, 220ms) var(--motion-ease, ease);
	}

	/* Strategy 2: grid-rows fallback (no measurement). */
	.grid-region {
		display: grid;
		grid-template-rows: 0fr;
		transition: grid-template-rows var(--motion-base, 220ms) var(--motion-ease, ease);
	}
	.ac-item.open .grid-region {
		grid-template-rows: 1fr;
	}
	.grid-region > .ac-body {
		min-height: 0;
		overflow: hidden;
	}

	@media (prefers-reduced-motion: reduce) {
		.measured-region,
		.grid-region {
			transition: none;
		}
	}
</style>

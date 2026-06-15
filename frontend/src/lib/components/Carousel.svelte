<script lang="ts">
	// A generic image carousel: prev/next, dots, keyboard arrows, and touch swipe.
	// Token-only and reusable anywhere a set of images is flipped through (the
	// calendar card thumbnail + its full-view modal; could back the vault preview
	// too). Pass `items` as {src, alt}; the parent owns loading/prefetch and is
	// notified of index changes via `onindex`.
	import Icon from './Icon.svelte';

	type Item = { src: string; alt?: string };

	let {
		items,
		index = $bindable(0),
		compact = false,
		rounded = true,
		onindex,
		onactivate
	}: {
		items: Item[];
		index?: number;
		/** Smaller controls/height for an inline (minimized-card) carousel. */
		compact?: boolean;
		rounded?: boolean;
		onindex?: (index: number) => void;
		/** Fires when the image area itself is clicked (e.g. open full view). */
		onactivate?: () => void;
	} = $props();

	const count = $derived(items.length);
	const current = $derived(items[Math.min(index, Math.max(0, count - 1))]);

	function go(delta: number, e?: Event) {
		e?.stopPropagation();
		if (count === 0) return;
		index = (index + delta + count) % count;
		onindex?.(index);
	}

	function jump(i: number, e?: Event) {
		e?.stopPropagation();
		index = i;
		onindex?.(i);
	}

	// --- swipe ---------------------------------------------------------------
	let startX = 0;
	let swiping = false;
	function onPointerDown(e: PointerEvent) {
		swiping = true;
		startX = e.clientX;
	}
	function onPointerUp(e: PointerEvent) {
		if (!swiping) return;
		swiping = false;
		const dx = e.clientX - startX;
		if (Math.abs(dx) > 40) go(dx < 0 ? 1 : -1);
	}

	function onKey(e: KeyboardEvent) {
		if (e.key === 'ArrowLeft') go(-1, e);
		else if (e.key === 'ArrowRight') go(1, e);
	}
</script>

<!-- svelte-ignore a11y_no_noninteractive_tabindex a11y_no_noninteractive_element_interactions -->
<div
	class="carousel"
	class:compact
	role="group"
	aria-roledescription="carousel"
	tabindex="0"
	onkeydown={onKey}
	onpointerdown={onPointerDown}
	onpointerup={onPointerUp}
>
	<button
		type="button"
		class="stage"
		class:rounded
		aria-label={onactivate ? 'Open' : current?.alt || 'Image'}
		onclick={() => onactivate?.()}
	>
		{#if current}
			<img src={current.src} alt={current.alt ?? ''} draggable="false" />
		{:else}
			<div class="empty"><Icon name="image-off" size={compact ? 20 : 32} /></div>
		{/if}
	</button>

	{#if count > 1}
		<button class="nav prev" aria-label="Previous" onclick={(e) => go(-1, e)}>
			<Icon name="chevron-left" size={compact ? 16 : 22} />
		</button>
		<button class="nav next" aria-label="Next" onclick={(e) => go(1, e)}>
			<Icon name="chevron-right" size={compact ? 16 : 22} />
		</button>
		<div class="dots">
			{#each items as _, i (i)}
				<button
					class="dot"
					class:on={i === index}
					aria-label={`Go to image ${i + 1}`}
					onclick={(e) => jump(i, e)}
				></button>
			{/each}
		</div>
	{/if}
</div>

<style>
	.carousel {
		position: relative;
		width: 100%;
		outline: none;
		user-select: none;
		touch-action: pan-y;
	}
	.stage {
		position: relative;
		display: flex;
		align-items: center;
		justify-content: center;
		width: 100%;
		aspect-ratio: 16 / 10;
		overflow: hidden;
		background: var(--surface-2);
		cursor: pointer;
	}
	.compact .stage {
		aspect-ratio: 4 / 3;
	}
	.stage.rounded {
		border-radius: var(--radius-md);
	}
	.stage img {
		width: 100%;
		height: 100%;
		object-fit: cover;
		display: block;
	}
	.empty {
		color: var(--muted);
	}
	.nav {
		position: absolute;
		top: 50%;
		transform: translateY(-50%);
		display: inline-flex;
		align-items: center;
		justify-content: center;
		width: 34px;
		height: 34px;
		border: var(--border-width) solid var(--border-color);
		border-radius: var(--radius-full);
		background: color-mix(in srgb, var(--surface) 70%, transparent);
		backdrop-filter: blur(var(--blur));
		-webkit-backdrop-filter: blur(var(--blur));
		color: var(--fg);
		cursor: pointer;
		opacity: 0;
		transition: opacity var(--motion-fast) var(--motion-ease);
	}
	.compact .nav {
		width: 26px;
		height: 26px;
	}
	.carousel:hover .nav,
	.carousel:focus-within .nav {
		opacity: 1;
	}
	.nav:hover {
		background: var(--surface-2);
	}
	.nav.prev {
		left: var(--space-2);
	}
	.nav.next {
		right: var(--space-2);
	}
	.dots {
		position: absolute;
		bottom: var(--space-2);
		left: 0;
		right: 0;
		display: flex;
		gap: var(--space-1);
		justify-content: center;
		pointer-events: none;
	}
	.dot {
		pointer-events: auto;
		width: 7px;
		height: 7px;
		padding: 0;
		border: none;
		border-radius: var(--radius-full);
		background: color-mix(in srgb, var(--fg) 40%, transparent);
		cursor: pointer;
		transition:
			background var(--motion-fast) var(--motion-ease),
			width var(--motion-fast) var(--motion-ease);
	}
	.dot.on {
		width: 16px;
		background: var(--accent);
	}
</style>

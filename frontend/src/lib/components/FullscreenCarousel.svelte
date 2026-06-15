<script lang="ts">
	// A dedicated fullscreen media viewer, opened by Carousel's fullscreen button.
	// Covers the whole viewport with a dark backdrop, shows each item at its natural
	// aspect ratio (best-fit, never cropped), and offers prev/next, dots, keyboard
	// (←/→/Esc, L = lights off), swipe, a "lights off" deep-dim, and exit. Shares the
	// item shape with Carousel so the same `items`/`index` flow straight through.
	import { onMount } from 'svelte';
	import Icon from './Icon.svelte';
	import { portal } from '$lib/actions/portal';

	type Item = {
		src: string;
		alt?: string;
		type?: string;
		loading?: boolean;
		progress?: number | null;
	};

	let {
		items,
		index = $bindable(0),
		onindex,
		onclose
	}: {
		items: Item[];
		index?: number;
		onindex?: (index: number) => void;
		onclose?: () => void;
	} = $props();

	const count = $derived(items.length);
	const current = $derived(items[Math.min(index, Math.max(0, count - 1))]);

	let lightsOff = $state(false);

	function isImage(t?: string) {
		return !t || t.startsWith('image/');
	}
	function isVideo(t?: string) {
		return !!t && t.startsWith('video/');
	}
	function isAudio(t?: string) {
		return !!t && t.startsWith('audio/');
	}
	function isPdf(t?: string) {
		return t === 'application/pdf';
	}

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

	function onKey(e: KeyboardEvent) {
		if (e.key === 'Escape') {
			if (lightsOff) lightsOff = false;
			else onclose?.();
		} else if (e.key === 'ArrowLeft') go(-1);
		else if (e.key === 'ArrowRight') go(1);
		else if (e.key.toLowerCase() === 'l') lightsOff = !lightsOff;
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
		if (Math.abs(dx) > 50) go(dx < 0 ? 1 : -1);
	}

	// Lock background scroll while open.
	onMount(() => {
		const prev = document.body.style.overflow;
		document.body.style.overflow = 'hidden';
		return () => {
			document.body.style.overflow = prev;
		};
	});
</script>

<svelte:window onkeydown={onKey} />

<!-- svelte-ignore a11y_no_noninteractive_element_interactions -->
<div
	use:portal
	class="fs"
	class:lights-off={lightsOff}
	role="dialog"
	aria-modal="true"
	aria-label="Fullscreen viewer"
	tabindex="-1"
	onpointerdown={onPointerDown}
	onpointerup={onPointerUp}
>
	<!-- Click the backdrop (outside the media) to close. -->
	<button class="backdrop" aria-label="Close" onclick={() => onclose?.()}></button>

	<div class="toolbar">
		{#if count > 1}
			<span class="counter">{index + 1} / {count}</span>
		{/if}
		<div class="spacer"></div>
		<button
			class="tool"
			aria-label={lightsOff ? 'Lights on' : 'Lights off'}
			title={lightsOff ? 'Lights on' : 'Lights off'}
			onclick={() => (lightsOff = !lightsOff)}
		>
			<Icon name={lightsOff ? 'sun' : 'moon'} size={20} />
		</button>
		<button class="tool" aria-label="Exit fullscreen" title="Exit fullscreen" onclick={() => onclose?.()}>
			<Icon name="minimize" size={20} />
		</button>
		<button class="tool" aria-label="Close" title="Close" onclick={() => onclose?.()}>
			<Icon name="x" size={22} />
		</button>
	</div>

	<div class="media">
		{#if current?.loading}
			<div class="loading">
				<Icon name="refresh-cw" size={32} />
				{#if current.progress != null}<span>{Math.round(current.progress * 100)}%</span>{/if}
			</div>
		{:else if current && current.src}
			{#if isImage(current.type)}
				<img src={current.src} alt={current.alt ?? ''} draggable="false" />
			{:else if isVideo(current.type)}
				<!-- svelte-ignore a11y_media_has_caption -->
				<video src={current.src} controls autoplay></video>
			{:else if isAudio(current.type)}
				<audio src={current.src} controls></audio>
			{:else if isPdf(current.type)}
				<iframe class="pdf" src={current.src} title={current.alt ?? 'PDF'}></iframe>
			{:else}
				<div class="empty"><Icon name="file" size={48} /></div>
			{/if}
		{:else}
			<div class="empty"><Icon name="image-off" size={48} /></div>
		{/if}
	</div>

	{#if count > 1}
		<button class="nav prev" aria-label="Previous" onclick={(e) => go(-1, e)}>
			<Icon name="chevron-left" size={28} />
		</button>
		<button class="nav next" aria-label="Next" onclick={(e) => go(1, e)}>
			<Icon name="chevron-right" size={28} />
		</button>
		<div class="dots">
			{#each items as _, i (i)}
				<button
					class="dot"
					class:on={i === index}
					aria-label={`Go to item ${i + 1}`}
					onclick={(e) => jump(i, e)}
				></button>
			{/each}
		</div>
	{/if}
</div>

<style>
	.fs {
		position: fixed;
		inset: 0;
		z-index: 200;
		display: flex;
		align-items: center;
		justify-content: center;
		background: rgba(0, 0, 0, 0.92);
		backdrop-filter: blur(calc(var(--blur) / 2));
		-webkit-backdrop-filter: blur(calc(var(--blur) / 2));
		animation: fade var(--motion-base) var(--motion-ease);
		touch-action: pan-y;
	}
	.fs.lights-off {
		background: #000;
	}
	@keyframes fade {
		from {
			opacity: 0;
		}
	}
	.backdrop {
		position: absolute;
		inset: 0;
		border: none;
		background: transparent;
		cursor: zoom-out;
	}

	.media {
		position: relative;
		z-index: 1;
		display: flex;
		align-items: center;
		justify-content: center;
		max-width: 94vw;
		max-height: 92vh;
		pointer-events: none;
	}
	/* Fit to the image's own aspect ratio — never crop, never upscale-distort. */
	.media img,
	.media video {
		max-width: 94vw;
		max-height: 92vh;
		width: auto;
		height: auto;
		object-fit: contain;
		display: block;
		border-radius: var(--radius-md);
		box-shadow: 0 20px 80px -10px rgba(0, 0, 0, 0.7);
		pointer-events: auto;
	}
	.media audio {
		pointer-events: auto;
	}
	.pdf {
		width: 94vw;
		height: 92vh;
		border: none;
		border-radius: var(--radius-md);
		background: var(--surface);
		pointer-events: auto;
	}
	.loading {
		display: flex;
		flex-direction: column;
		align-items: center;
		gap: var(--space-2);
		color: #fff;
	}
	.loading :global(svg) {
		animation: spin 1s linear infinite;
	}
	@keyframes spin {
		to {
			transform: rotate(360deg);
		}
	}
	.empty {
		color: rgba(255, 255, 255, 0.5);
	}

	.toolbar {
		position: absolute;
		top: 0;
		left: 0;
		right: 0;
		z-index: 3;
		display: flex;
		align-items: center;
		gap: var(--space-2);
		padding: var(--space-3) var(--space-4);
	}
	.lights-off .toolbar {
		opacity: 0.25;
		transition: opacity var(--motion-fast) var(--motion-ease);
	}
	.lights-off .toolbar:hover {
		opacity: 1;
	}
	.counter {
		color: rgba(255, 255, 255, 0.85);
		font-size: 0.9rem;
		font-variant-numeric: tabular-nums;
	}
	.spacer {
		flex: 1;
	}
	.tool {
		display: inline-flex;
		align-items: center;
		justify-content: center;
		width: 38px;
		height: 38px;
		border: none;
		border-radius: var(--radius-full);
		background: rgba(255, 255, 255, 0.1);
		color: #fff;
		cursor: pointer;
		transition: background var(--motion-fast) var(--motion-ease);
	}
	.tool:hover {
		background: rgba(255, 255, 255, 0.22);
	}

	.nav {
		position: absolute;
		top: 50%;
		transform: translateY(-50%);
		z-index: 2;
		display: inline-flex;
		align-items: center;
		justify-content: center;
		width: 52px;
		height: 52px;
		border: none;
		border-radius: var(--radius-full);
		background: rgba(255, 255, 255, 0.1);
		color: #fff;
		cursor: pointer;
		transition: background var(--motion-fast) var(--motion-ease);
	}
	.nav:hover {
		background: rgba(255, 255, 255, 0.22);
	}
	.nav.prev {
		left: var(--space-4);
	}
	.nav.next {
		right: var(--space-4);
	}
	.lights-off .nav {
		opacity: 0.25;
	}
	.lights-off .nav:hover {
		opacity: 1;
	}

	.dots {
		position: absolute;
		bottom: var(--space-4);
		left: 0;
		right: 0;
		z-index: 2;
		display: flex;
		gap: var(--space-1);
		justify-content: center;
	}
	.dot {
		width: 8px;
		height: 8px;
		padding: 0;
		border: none;
		border-radius: var(--radius-full);
		background: rgba(255, 255, 255, 0.4);
		cursor: pointer;
		transition:
			background var(--motion-fast) var(--motion-ease),
			width var(--motion-fast) var(--motion-ease);
	}
	.dot.on {
		width: 18px;
		background: #fff;
	}
	.lights-off .dots {
		opacity: 0.25;
	}
</style>

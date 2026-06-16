<script lang="ts">
	// A generic media carousel: prev/next, dots, keyboard arrows, touch swipe, an
	// optional fullscreen view, and a "lights off" dim. Token-only and reusable
	// anywhere a set of media is flipped through (calendar card thumbnail + its full
	// view, the vault preview, …).
	//
	// Each item is { src, alt?, type?, loading?, progress? }:
	//   - type     MIME; decides image/video/audio/pdf rendering (default image)
	//   - loading  show a spinner/percent instead of the media (e.g. decrypting)
	//   - progress 0..1, shown while loading
	// `src` may be empty while an item is still loading. The parent owns
	// loading/prefetch/decryption and is notified of index changes via `onindex`.
	import Icon from './Icon.svelte';
	import FullscreenCarousel from './FullscreenCarousel.svelte';

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
		compact = false,
		rounded = true,
		/** 'cover' fills the frame (may crop); 'contain' shows the whole image,
		 *  best-fit, with a blurred zoomed copy filling the letterbox bars. */
		fit = 'cover',
		/** Show the fullscreen toggle button. */
		allowFullscreen = false,
		/** Show the "lights off" toggle (dims everything around the media). */
		allowLightsOff = false,
		onindex,
		onactivate
	}: {
		items: Item[];
		index?: number;
		/** Smaller controls/height for an inline (minimized-card) carousel. */
		compact?: boolean;
		rounded?: boolean;
		fit?: 'cover' | 'contain';
		allowFullscreen?: boolean;
		allowLightsOff?: boolean;
		onindex?: (index: number) => void;
		/** Fires when the image area itself is clicked (e.g. open full view). When
		 *  omitted and fullscreen is allowed, a click opens fullscreen instead. */
		onactivate?: () => void;
	} = $props();

	const count = $derived(items.length);
	const current = $derived(items[Math.min(index, Math.max(0, count - 1))]);

	let lightsOff = $state(false);
	let fullscreen = $state(false);

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

	function activate() {
		if (onactivate) onactivate();
		else if (allowFullscreen) fullscreen = true;
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
		else if (e.key.toLowerCase() === 'f' && allowFullscreen) fullscreen = !fullscreen;
		else if (e.key.toLowerCase() === 'l' && allowLightsOff) lightsOff = !lightsOff;
	}
</script>

<!-- svelte-ignore a11y_no_noninteractive_tabindex -->
<!-- svelte-ignore a11y_no_noninteractive_element_interactions -->
<div
	class="carousel"
	class:compact
	class:lights-off={lightsOff}
	class:contain={fit === 'contain'}
	role="group"
	aria-roledescription="carousel"
	tabindex="0"
	onkeydown={onKey}
	onpointerdown={onPointerDown}
	onpointerup={onPointerUp}
>
	{#if lightsOff}
		<button class="lights-scrim" aria-label="Lights on" onclick={() => (lightsOff = false)}
		></button>
	{/if}

	<button
		type="button"
		class="stage"
		class:rounded
		aria-label={onactivate || allowFullscreen ? 'Open' : current?.alt || 'Media'}
		onclick={activate}
	>
		{#if current?.loading}
			<div class="loading">
				<Icon name="refresh-cw" size={compact ? 20 : 28} />
				{#if current.progress != null}<span>{Math.round(current.progress * 100)}%</span>{/if}
			</div>
		{:else if current && current.src}
			{#if isImage(current.type)}
				{#if fit === 'contain'}
					<!-- Blurred, zoomed copy fills the letterbox bars behind the sharp image. -->
					<div class="bg" style:background-image="url('{current.src}')"></div>
				{/if}
				<img src={current.src} alt={current.alt ?? ''} draggable="false" />
			{:else if isVideo(current.type)}
				<!-- svelte-ignore a11y_media_has_caption -->
				<video src={current.src} controls onclick={(e) => e.stopPropagation()}></video>
			{:else if isAudio(current.type)}
				<audio src={current.src} controls onclick={(e) => e.stopPropagation()}></audio>
			{:else if isPdf(current.type)}
				<iframe class="pdf" src={current.src} title={current.alt ?? 'PDF'}></iframe>
			{:else}
				<div class="empty"><Icon name="file" size={compact ? 20 : 32} /></div>
			{/if}
		{:else}
			<div class="empty"><Icon name="image-off" size={compact ? 20 : 32} /></div>
		{/if}
	</button>

	{#if allowFullscreen || allowLightsOff}
		<div class="tools">
			{#if allowLightsOff}
				<button
					class="tool"
					aria-label={lightsOff ? 'Lights on' : 'Lights off'}
					title={lightsOff ? 'Lights on' : 'Lights off'}
					onclick={(e) => {
						e.stopPropagation();
						lightsOff = !lightsOff;
					}}
				>
					<Icon name={lightsOff ? 'sun' : 'moon'} size={compact ? 15 : 18} />
				</button>
			{/if}
			{#if allowFullscreen}
				<button
					class="tool"
					aria-label="Fullscreen"
					title="Fullscreen"
					onclick={(e) => {
						e.stopPropagation();
						fullscreen = true;
					}}
				>
					<Icon name="maximize" size={compact ? 15 : 18} />
				</button>
			{/if}
		</div>
	{/if}

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
					aria-label={`Go to item ${i + 1}`}
					onclick={(e) => jump(i, e)}
				></button>
			{/each}
		</div>
	{/if}
</div>

{#if fullscreen}
	<FullscreenCarousel
		{items}
		bind:index
		onindex={(i) => onindex?.(i)}
		onclose={() => (fullscreen = false)}
	/>
{/if}

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
		border: none;
		padding: 0;
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
		position: relative;
		z-index: 1;
	}
	/* Best-fit: show the whole image, blurred zoomed copy fills the bars. */
	.contain .stage {
		background: var(--bg);
	}
	.contain .stage img {
		object-fit: contain;
	}
	.bg {
		position: absolute;
		inset: 0;
		background-size: cover;
		background-position: center;
		filter: blur(28px) saturate(1.3) brightness(0.8);
		transform: scale(1.25);
		z-index: 0;
	}
	.stage video {
		max-width: 100%;
		max-height: 100%;
		display: block;
		position: relative;
		z-index: 1;
	}
	.stage audio {
		width: 90%;
		position: relative;
		z-index: 1;
	}
	.pdf {
		width: 100%;
		height: 100%;
		border: none;
		background: var(--surface);
		position: relative;
		z-index: 1;
	}
	.loading {
		display: flex;
		flex-direction: column;
		align-items: center;
		gap: var(--space-1);
		color: var(--muted);
		font-size: 0.85rem;
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
		color: var(--muted);
	}

	/* --- lights off ---------------------------------------------------------- */
	.lights-scrim {
		position: fixed;
		inset: 0;
		z-index: 90;
		border: none;
		background: rgba(0, 0, 0, 0.86);
		cursor: pointer;
		animation: fade var(--motion-base) var(--motion-ease);
	}
	.lights-off .stage {
		position: relative;
		z-index: 91;
		box-shadow: 0 0 0 100vmax rgba(0, 0, 0, 0.86);
	}
	.lights-off .tools,
	.lights-off .nav,
	.lights-off .dots {
		z-index: 92;
	}
	@keyframes fade {
		from {
			opacity: 0;
		}
	}

	/* --- tools (fullscreen / lights off) ------------------------------------- */
	.tools {
		position: absolute;
		top: var(--space-2);
		right: var(--space-2);
		z-index: 2;
		display: flex;
		gap: var(--space-1);
		opacity: 0;
		transition: opacity var(--motion-fast) var(--motion-ease);
	}
	.carousel:hover .tools,
	.carousel:focus-within .tools,
	.lights-off .tools {
		opacity: 1;
	}
	.tool {
		display: inline-flex;
		align-items: center;
		justify-content: center;
		width: 30px;
		height: 30px;
		border: var(--border-width) solid var(--border-color);
		border-radius: var(--radius-full);
		background: color-mix(in srgb, var(--surface) 70%, transparent);
		backdrop-filter: blur(var(--blur));
		-webkit-backdrop-filter: blur(var(--blur));
		color: var(--fg);
		cursor: pointer;
	}
	.compact .tool {
		width: 24px;
		height: 24px;
	}
	.tool:hover {
		background: var(--surface-2);
	}

	.nav {
		position: absolute;
		top: 50%;
		z-index: 2;
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
	.carousel:focus-within .nav,
	.lights-off .nav {
		opacity: 1;
	}
	.nav:hover {
		background: var(--surface-2);
	}
	/* Touch devices have no hover: keep the nav arrows + tools visible (and so
	   tappable) instead of falling through to the stage, which opens full view. */
	@media (hover: none) {
		.nav,
		.tools {
			opacity: 1;
		}
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
		z-index: 2;
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

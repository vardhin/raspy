<script lang="ts">
	// A generic cluster of media (one or many) that decrypts lazily and renders via
	// the shared Carousel. Token-only and decoupled from any one app: the parent
	// passes an opaque list of items (each with a stable `hash`) and a `load(item)`
	// that returns a decrypted Blob; this component renders + flips them.
	//
	// Decryption goes through the app-scoped mediaCache (keyed by hash), so a blob
	// is decrypted at most once while the app is open — re-renders (e.g. sending a
	// new chat message) reuse the cached object URL instead of decrypting again.
	import Carousel from './Carousel.svelte';
	import { getMediaUrl, peekMediaUrl } from '$lib/crypto/mediaCache';

	type Item = { hash: string; name?: string; type?: string };

	let {
		items,
		load,
		compact = false,
		fit = 'cover',
		allowFullscreen = true
	}: {
		items: Item[];
		/** Decrypt one item to a Blob. Called at most once per hash (cache-guarded). */
		load: (item: Item, index: number) => Promise<Blob>;
		compact?: boolean;
		fit?: 'cover' | 'contain';
		allowFullscreen?: boolean;
	} = $props();

	type Slot = { src: string; alt?: string; type?: string; loading: boolean; progress: number | null };

	// A stable key for this media set: the ordered hashes. The $effect below only
	// re-seeds when this actually changes, so an unrelated parent re-render (new
	// message appended to the list) does NOT reset/redecrypt existing bubbles.
	const key = $derived(items.map((i) => i.hash).join(','));

	let slots = $state<Slot[]>([]);
	let index = $state(0);
	const requested = new Set<string>();

	$effect(() => {
		// Depend only on `key`; re-seed when the media set genuinely changes.
		key;
		requested.clear();
		slots = items.map((it) => {
			const cached = peekMediaUrl(it.hash);
			return {
				src: cached ?? '',
				alt: it.name,
				type: it.type,
				loading: !cached,
				progress: null
			};
		});
		ensure(0);
	});

	async function ensure(i: number) {
		if (i < 0 || i >= items.length) return;
		const it = items[i];
		if (requested.has(it.hash)) return;
		requested.add(it.hash);
		try {
			const url = await getMediaUrl(it.hash, () => load(it, i));
			slots[i] = { ...slots[i], src: url, loading: false };
		} catch {
			slots[i] = { ...slots[i], loading: false };
		}
	}

	function onindex(i: number) {
		index = i;
		// Prefetch neighbours for seamless flipping.
		ensure(i);
		ensure(i + 1);
		ensure(i - 1);
	}
</script>

{#if slots.length}
	<div class="media-bubble" class:compact>
		<Carousel items={slots} bind:index {compact} {fit} {allowFullscreen} {onindex} />
	</div>
{/if}

<style>
	.media-bubble {
		width: min(320px, 70vw);
		max-width: 100%;
		border-radius: var(--radius-md);
		overflow: hidden;
	}
	.media-bubble.compact {
		width: min(220px, 60vw);
	}
</style>

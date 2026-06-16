<script lang="ts">
	// A generic cluster of media (one or many) that decrypts lazily and renders via
	// the shared Carousel. Token-only and decoupled from any one app: the parent
	// passes an opaque list of items and a `load(item)` that returns a decrypted
	// Blob; this component owns object-URL lifecycle, progress, and flipping.
	//
	// Used for chat media messages (clustered photos as a swipeable carousel) and
	// reusable anywhere a set of encrypted media needs inline display.
	import { onDestroy } from 'svelte';
	import Carousel from './Carousel.svelte';

	type Item = { name?: string; type?: string };

	let {
		items,
		load,
		compact = false,
		fit = 'cover',
		allowFullscreen = true
	}: {
		items: Item[];
		/** Decrypt one item to a Blob. Called once per item, lazily on view. */
		load: (item: Item, index: number) => Promise<Blob>;
		compact?: boolean;
		fit?: 'cover' | 'contain';
		allowFullscreen?: boolean;
	} = $props();

	type Slot = { src: string; alt?: string; type?: string; loading: boolean; progress: number | null };

	// One slot per item, mirroring `items`. Object URLs are revoked on destroy.
	let slots = $state<Slot[]>([]);
	let index = $state(0);
	const urls: string[] = [];
	const requested = new Set<number>();

	$effect(() => {
		// Re-seed slots when the item set changes (new message rendered).
		slots = items.map((it) => ({
			src: '',
			alt: it.name,
			type: it.type,
			loading: true,
			progress: null
		}));
		requested.clear();
		ensure(0);
	});

	async function ensure(i: number) {
		if (i < 0 || i >= items.length || requested.has(i)) return;
		requested.add(i);
		try {
			const blob = await load(items[i], i);
			const url = URL.createObjectURL(blob);
			urls.push(url);
			slots[i] = { ...slots[i], src: url, type: blob.type || items[i].type, loading: false };
		} catch {
			slots[i] = { ...slots[i], loading: false };
		}
	}

	function onindex(i: number) {
		index = i;
		// Prefetch the neighbour for seamless flipping.
		ensure(i);
		ensure(i + 1);
		ensure(i - 1);
	}

	onDestroy(() => urls.forEach((u) => URL.revokeObjectURL(u)));
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

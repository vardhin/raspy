<script lang="ts">
	// A generic chat message bubble: left/right alignment by ownership, optional
	// text, an optional media slot (snippet) for a MediaBubble or anything else, and
	// a small timestamp. Token-only; reusable for any conversation UI.
	import type { Snippet } from 'svelte';
	import Text from './Text.svelte';

	let {
		mine = false,
		text = '',
		time,
		pending = false,
		media
	}: {
		mine?: boolean;
		text?: string;
		/** Unix seconds; rendered as a short local time. */
		time?: number;
		/** Dim slightly while a send is in flight. */
		pending?: boolean;
		/** Optional media content (e.g. a <MediaBubble/>). */
		media?: Snippet;
	} = $props();

	const stamp = $derived(
		time
			? new Date(time * 1000).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })
			: ''
	);
</script>

<div class="row" class:mine>
	<div class="bubble" class:mine class:pending>
		{#if media}
			<div class="media">{@render media()}</div>
		{/if}
		{#if text}
			<Text>{text}</Text>
		{/if}
		{#if stamp}<span class="time">{stamp}</span>{/if}
	</div>
</div>

<style>
	.row {
		display: flex;
		width: 100%;
		justify-content: flex-start;
	}
	.row.mine {
		justify-content: flex-end;
	}
	.bubble {
		max-width: min(78%, 540px);
		display: flex;
		flex-direction: column;
		gap: var(--space-1);
		padding: var(--space-2) var(--space-3);
		border-radius: var(--radius-lg);
		background: color-mix(in srgb, var(--surface-2) calc(var(--surface-alpha) * 100%), transparent);
		border: var(--border-width) solid var(--border-color);
		box-shadow: var(--shadow-md);
		/* Speech-bubble tail via differing corner radii. */
		border-bottom-left-radius: var(--radius-sm);
	}
	.bubble.mine {
		background: color-mix(in srgb, var(--accent) 22%, var(--surface-2));
		border-bottom-left-radius: var(--radius-lg);
		border-bottom-right-radius: var(--radius-sm);
	}
	.bubble.pending {
		opacity: 0.6;
	}
	.media {
		margin: calc(var(--space-1) * -1) 0;
	}
	.time {
		align-self: flex-end;
		font-size: 0.7rem;
		opacity: 0.6;
		line-height: 1;
	}
</style>

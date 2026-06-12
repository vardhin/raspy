<script lang="ts">
	// Accordion group: a single bordered container holding `AccordionItem` sections
	// as divider-separated rows. The group only provides the card chrome; each item
	// owns its header/body and (optional) pretext-measured expand animation.
	//
	// Single-open behavior is the caller's job — pass each item an `open` derived from
	// one shared "expanded id" so opening one closes the others.
	import type { Snippet } from 'svelte';

	let { children }: { children: Snippet } = $props();
</script>

<div class="accordion">
	{@render children()}
</div>

<style>
	.accordion {
		border: var(--border-width) solid var(--border-color);
		border-radius: var(--radius-lg);
		background: color-mix(in srgb, var(--surface) calc(var(--surface-alpha, 1) * 100%), transparent);
		overflow: hidden;
	}
</style>

<script lang="ts">
	// Flex layout primitive. direction + gap (via --space-*) + alignment.
	// Covers Stack (column) and Row (row) so we don't need two components.
	import type { Snippet } from 'svelte';

	type Gap = 1 | 2 | 3 | 4 | 5 | 6;

	let {
		direction = 'column',
		gap = 3,
		align = 'stretch',
		justify = 'start',
		wrap = false,
		children,
		...rest
	}: {
		direction?: 'row' | 'column';
		gap?: Gap;
		align?: 'start' | 'center' | 'end' | 'stretch';
		justify?: 'start' | 'center' | 'end' | 'between';
		wrap?: boolean;
		children: Snippet;
		[key: string]: unknown;
	} = $props();

	const alignMap = { start: 'flex-start', center: 'center', end: 'flex-end', stretch: 'stretch' };
	const justifyMap = {
		start: 'flex-start',
		center: 'center',
		end: 'flex-end',
		between: 'space-between'
	};
</script>

<div
	class="stack"
	style:flex-direction={direction}
	style:gap="var(--space-{gap})"
	style:align-items={alignMap[align]}
	style:justify-content={justifyMap[justify]}
	style:flex-wrap={wrap ? 'wrap' : 'nowrap'}
	{...rest}
>
	{@render children()}
</div>

<style>
	.stack {
		display: flex;
		min-width: 0;
	}
</style>

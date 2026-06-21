<script lang="ts">
	// A drag-reorderable declarative list. Used by Node.svelte when a `list` node
	// carries a `reorder` action. Each row is rendered by the recursive Node
	// renderer (so it stays fully data-driven); we add a drag handle and reorder
	// the rows by pointer. Reordering is optimistic (the local order updates as you
	// drag) and committed via ctx.runReorder, which sends `{order:[…]}` and rolls
	// back on failure.
	//
	// Pointer events (not HTML5 DnD) so it works on touch + desktop alike. We only
	// start a drag from the handle, so taps on row controls (checkbox, buttons)
	// still work normally.
	import { getContext, tick } from 'svelte';
	import Node from './Node.svelte';
	import { Icon } from '$lib/components';
	import type { RenderContext } from './context.svelte';
	import type { UINode } from '$lib/manifest/types';

	let { node, rows }: { node: UINode; rows: Record<string, unknown>[] } = $props();

	const ctx = getContext<RenderContext>('render');
	const key = $derived(node.key ?? 'id');

	// Local working order during a drag — a list of row keys. While dragging we
	// reorder this array; on drop we hand it to ctx.runReorder. When not dragging
	// it tracks `rows` so live updates from the server flow through.
	let order = $state<string[]>([]);
	let dragging = $state<string | null>(null);

	// Mirror the server order into `order` whenever we're not mid-drag.
	$effect(() => {
		const ids = rows.map((r) => String(r[key]));
		if (dragging === null) order = ids;
	});

	// Resolve the row object for a key (rows is the source of truth for content).
	function rowFor(k: string): Record<string, unknown> | undefined {
		return rows.find((r) => String(r[key]) === k);
	}

	let listEl: HTMLDivElement | undefined = $state();

	// Which key the pointer is currently over, by hit-testing row centers. Moving
	// the dragged key to that slot gives a live preview as you drag.
	function keyUnderPointer(clientY: number): string | null {
		if (!listEl) return null;
		const items = Array.from(listEl.querySelectorAll<HTMLElement>('[data-rkey]'));
		for (const el of items) {
			const r = el.getBoundingClientRect();
			if (clientY < r.top + r.height / 2) return el.dataset.rkey ?? null;
		}
		// Past the last row → end of list.
		return items.length ? (items[items.length - 1].dataset.rkey ?? null) : null;
	}

	function moveKey(from: string, before: string | null): void {
		const next = order.filter((k) => k !== from);
		if (before === null || before === from) {
			next.push(from);
		} else {
			const i = next.indexOf(before);
			next.splice(i < 0 ? next.length : i, 0, from);
		}
		order = next;
	}

	function onHandlePointerDown(e: PointerEvent, k: string): void {
		// Only the primary button / a touch starts a drag.
		if (e.button !== 0 && e.pointerType === 'mouse') return;
		e.preventDefault();
		dragging = k;
		const handle = e.currentTarget as HTMLElement;
		handle.setPointerCapture(e.pointerId);
	}

	function onPointerMove(e: PointerEvent): void {
		if (dragging === null) return;
		e.preventDefault();
		const overKey = keyUnderPointer(e.clientY);
		// When over the bottom half of the last row, append; else insert before.
		if (overKey && overKey !== dragging) moveKey(dragging, overKey);
	}

	async function onPointerUp(): Promise<void> {
		if (dragging === null) return;
		const finalOrder = [...order];
		dragging = null;
		const original = rows.map((r) => String(r[key]));
		// Only commit when the order actually changed; otherwise clearing
		// `dragging` re-syncs `order` to the server state via the effect.
		if (finalOrder.join(',') !== original.join(',') && node.reorder) {
			await ctx.runReorder(node.source ?? '', key, finalOrder, node.reorder);
		}
		await tick();
	}
</script>

<!-- The pointer handlers here are only a drag-capture convenience; the real
     interactive control is each row's handle <button>, so list semantics are
     correct and the static-element warning doesn't apply. -->
<!-- svelte-ignore a11y_no_static_element_interactions -->
<div
	class="rlist"
	role="list"
	bind:this={listEl}
	onpointermove={onPointerMove}
	onpointerup={onPointerUp}
	onpointercancel={onPointerUp}
>
	{#each order as k (k)}
		{@const r = rowFor(k)}
		{#if r && node.item}
			<div class="rrow" role="listitem" class:dragging={dragging === k} data-rkey={k}>
				<button
					class="handle"
					type="button"
					aria-label="Drag to reorder"
					title="Drag to reorder"
					onpointerdown={(e) => onHandlePointerDown(e, k)}
				>
					<Icon name="grip-vertical" size={16} />
				</button>
				<div class="rbody">
					<Node node={node.item} row={r} />
				</div>
			</div>
		{/if}
	{/each}
</div>

<style>
	.rlist {
		display: flex;
		flex-direction: column;
		gap: var(--space-2);
		touch-action: pan-y;
	}
	.rrow {
		display: flex;
		align-items: stretch;
		gap: var(--space-2);
		transition: opacity var(--motion-fast) var(--motion-ease);
	}
	.rrow.dragging {
		opacity: 0.6;
	}
	.rbody {
		flex: 1;
		min-width: 0;
	}
	.handle {
		flex: none;
		display: inline-flex;
		align-items: center;
		justify-content: center;
		padding: 0 var(--space-1);
		border: none;
		background: transparent;
		color: var(--muted);
		cursor: grab;
		border-radius: var(--radius-sm);
		touch-action: none; /* let the handle own the gesture */
		transition: color var(--motion-fast) var(--motion-ease);
	}
	.handle:hover {
		color: var(--fg);
	}
	.handle:active {
		cursor: grabbing;
	}
	.handle:focus-visible {
		outline: 2px solid var(--accent);
		outline-offset: 2px;
	}
</style>

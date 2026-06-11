<script lang="ts">
	// Recursive renderer: maps one backend UINode to a themed component, recursing
	// into children. `row` carries the current list-row data so `bind` props and
	// `{id}` action tokens resolve per row. The shell never hardcodes an app —
	// every screen is data from /api/manifest walked here.
	import { getContext } from 'svelte';
	import Self from './Node.svelte';
	import { Surface, Stack, Text, Badge, Button, Field } from '$lib/components';
	import FileManager from './FileManager.svelte';
	import SystemStats from './SystemStats.svelte';
	import type { RenderContext } from './context.svelte';
	import type { UINode } from '$lib/manifest/types';

	let { node, row }: { node: UINode; row?: Record<string, unknown> } = $props();

	const ctx = getContext<RenderContext>('render');

	// Read a node's display text: an explicit `text`, or a `bind` field off the row.
	function boundText(): string {
		if (node.bind && row) return String(row[node.bind] ?? '');
		return node.text ?? '';
	}

	// Map backend role/variant strings to the component's accepted unions (loose
	// cast — unknown values fall back to component defaults).
	const gap = $derived((node.gap ?? 3) as 1 | 2 | 3 | 4 | 5 | 6);
	const align = $derived(node.align as 'start' | 'center' | 'end' | 'stretch' | undefined);
	const justify = $derived(node.justify as 'start' | 'center' | 'end' | 'between' | undefined);

	async function onButton() {
		if (node.action) await ctx.runAction(node.action, row);
	}

	async function onCheckbox(e: Event) {
		// The toggle action is the source of truth; the box reflects server state.
		(e.target as HTMLInputElement).checked = !!(row && node.bind && row[node.bind]);
		if (node.action) await ctx.runAction(node.action, row);
	}
</script>

{#if node.type === 'stack'}
	<Stack
		direction={node.direction ?? 'column'}
		{gap}
		align={align ?? 'stretch'}
		justify={justify ?? 'start'}
		wrap={node.wrap ?? false}
	>
		{#each node.children ?? [] as child, i (i)}
			<Self node={child} {row} />
		{/each}
	</Stack>
{:else if node.type === 'surface'}
	<Surface level={node.level ?? 1} interactive={node.interactive ?? false}>
		<Stack gap={3}>
			{#each node.children ?? [] as child, i (i)}
				<Self node={child} {row} />
			{/each}
		</Stack>
	</Surface>
{:else if node.type === 'header'}
	<Text role="heading">{node.text}</Text>
{:else if node.type === 'text'}
	<Text role={(node.role as 'title' | 'heading' | 'body' | 'label' | 'muted') ?? 'body'}>
		{boundText()}
	</Text>
{:else if node.type === 'badge'}
	<Badge
		variant={(node.variant as 'neutral' | 'accent' | 'success' | 'warn' | 'danger' | 'info') ??
			'neutral'}
	>
		{boundText()}
	</Badge>
{:else if node.type === 'divider'}
	<hr class="divider" />
{:else if node.type === 'input'}
	<Field
		type={(node.kind as 'text' | 'number' | 'password' | 'email' | 'textarea') ?? 'text'}
		label={node.label ?? ''}
		placeholder={node.placeholder ?? ''}
		value={(ctx.fields[node.name ?? ''] as string) ?? ''}
		oninput={(e: Event) => ctx.setField(node.name ?? '', (e.target as HTMLInputElement).value)}
	/>
{:else if node.type === 'select'}
	<Field
		type="select"
		label={node.label ?? ''}
		options={node.options ?? []}
		value={(ctx.fields[node.name ?? ''] as string) ?? ''}
		onchange={(e: Event) => ctx.setField(node.name ?? '', (e.target as HTMLSelectElement).value)}
	/>
{:else if node.type === 'checkbox'}
	<input
		class="checkbox"
		type="checkbox"
		checked={!!(row && node.bind && row[node.bind])}
		onchange={onCheckbox}
	/>
{:else if node.type === 'button'}
	<Button
		variant={(node.variant as 'accent' | 'neutral' | 'ghost' | 'success' | 'warn' | 'danger') ??
			'accent'}
		onclick={onButton}
	>
		{node.text}
	</Button>
{:else if node.type === 'list'}
	{@const rows = (ctx.sources[node.source ?? ''] ?? []) as Record<string, unknown>[]}
	{#if rows.length === 0 && ctx.sourceLoading[node.source ?? '']}
		<Text role="muted">Loading…</Text>
	{:else if rows.length === 0}
		<Text role="muted">{node.empty ?? 'Nothing here yet.'}</Text>
	{:else}
		<Stack gap={2}>
			{#each rows as r (r[node.key ?? 'id'])}
				{#if node.item}
					<Self node={node.item} row={r} />
				{/if}
			{/each}
		</Stack>
	{/if}
{:else if node.type === 'table'}
	{@const rows = (ctx.sources[node.source ?? ''] ?? []) as Record<string, unknown>[]}
	<table class="table">
		<thead>
			<tr>
				{#each node.columns ?? [] as col (col.key)}
					<th>{col.label}</th>
				{/each}
			</tr>
		</thead>
		<tbody>
			{#each rows as r (r[node.key ?? 'id'])}
				<tr>
					{#each node.columns ?? [] as col (col.key)}
						<td>{String(r[col.key] ?? '')}</td>
					{/each}
				</tr>
			{/each}
		</tbody>
	</table>
{:else if node.type === 'file_manager'}
	<FileManager {node} />
{:else if node.type === 'system_stats'}
	<SystemStats {node} />
{:else}
	<Text role="muted">[unknown node: {node.type}]</Text>
{/if}

<style>
	.divider {
		border: none;
		border-top: var(--border-width) solid var(--border-color);
		margin: 0;
		width: 100%;
	}
	.checkbox {
		width: 1.15rem;
		height: 1.15rem;
		accent-color: var(--accent);
	}
	.table {
		width: 100%;
		border-collapse: collapse;
		font-size: 0.9rem;
	}
	.table th,
	.table td {
		text-align: left;
		padding: var(--space-2);
		border-bottom: var(--border-width) solid var(--border-color);
	}
	.table th {
		color: var(--muted);
		font-weight: var(--font-weight-bold);
	}
</style>

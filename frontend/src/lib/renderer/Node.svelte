<script lang="ts">
	// Recursive renderer: maps one backend UINode to a themed component, recursing
	// into children. `row` carries the current list-row data so `bind` props and
	// `{id}` action tokens resolve per row. The shell never hardcodes an app —
	// every screen is data from /api/manifest walked here.
	import { getContext } from 'svelte';
	import Self from './Node.svelte';
	import { Surface, Stack, Text, Badge, Button, Field, Icon } from '$lib/components';
	import FileManager from './FileManager.svelte';
	import MailClient from './MailClient.svelte';
	import SystemStats from './SystemStats.svelte';
	import Vault from './Vault.svelte';
	import Vibe from './Vibe.svelte';
	import Calendar from './Calendar.svelte';
	import Contacts from './Contacts.svelte';
	import Notes from './Notes.svelte';
	import Accounts from './Accounts.svelte';
	import Connectivity from './Connectivity.svelte';
	import Terminal from './Terminal.svelte';
	import Dropbox from './Dropbox.svelte';
	import Chat from './Chat.svelte';
	import Pomodoro from './Pomodoro.svelte';
	import Updates from './Updates.svelte';
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
	// Row stacks wrap by default so a too-wide row (e.g. input + button) reflows
	// on narrow screens instead of pushing a child off-screen. Columns never need
	// it. The backend can still force `wrap: false` explicitly.
	const stackWrap = $derived(node.wrap ?? node.direction === 'row');

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
		wrap={stackWrap}
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
	{@const badgeText = boundText()}
	{#if !(node.hide_when_empty && badgeText === '')}
		<Badge
			variant={((node.variant_bind && row
				? (row[node.variant_bind] as string)
				: node.variant) as
				| 'neutral'
				| 'accent'
				| 'success'
				| 'warn'
				| 'danger'
				| 'info') ?? 'neutral'}
		>
			{badgeText}
		</Badge>
	{/if}
{:else if node.type === 'divider'}
	<hr class="divider" />
{:else if node.type === 'input'}
	<Field
		type={(node.kind as 'text' | 'number' | 'password' | 'email' | 'textarea' | 'date') ??
			'text'}
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
	{@const cbChecked = !!(row && node.bind && row[node.bind])}
	<label class="checkbox">
		<input type="checkbox" checked={cbChecked} onchange={onCheckbox} />
		<span class="cb-box" aria-hidden="true">
			{#if cbChecked}<Icon name="check" size={14} />{/if}
		</span>
	</label>
{:else if node.type === 'button'}
	{@const btnLabel = node.bind && row ? String(row[node.bind] ?? '') : node.text}
	<Button
		variant={((node.variant_bind && row
			? (row[node.variant_bind] as string)
			: node.variant) as 'accent' | 'neutral' | 'ghost' | 'success' | 'warn' | 'danger') ??
			'accent'}
		size={(node.size as 'sm' | 'md' | 'lg') ?? 'md'}
		onclick={onButton}
	>
		{btnLabel || node.empty_label || node.text}
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
	<div class="table-scroll">
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
	</div>
{:else if node.type === 'file_manager'}
	<FileManager {node} />
{:else if node.type === 'mail_client'}
	<MailClient />
{:else if node.type === 'system_stats'}
	<SystemStats {node} />
{:else if node.type === 'vault'}
	<Vault />
{:else if node.type === 'vibe'}
	<Vibe />
{:else if node.type === 'calendar'}
	<Calendar />
{:else if node.type === 'contacts'}
	<Contacts />
{:else if node.type === 'notes'}
	<Notes />
{:else if node.type === 'accounts'}
	<Accounts />
{:else if node.type === 'connectivity'}
	<Connectivity {node} />
{:else if node.type === 'terminal'}
	<Terminal {node} />
{:else if node.type === 'dropbox'}
	<Dropbox />
{:else if node.type === 'chat'}
	<Chat />
{:else if node.type === 'pomodoro'}
	<Pomodoro />
{:else if node.type === 'updates'}
	<Updates />
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
		display: inline-flex;
		cursor: pointer;
	}
	.checkbox input {
		position: absolute;
		width: 1px;
		height: 1px;
		opacity: 0;
		margin: 0;
		pointer-events: none;
	}
	.cb-box {
		display: inline-flex;
		align-items: center;
		justify-content: center;
		width: 1.2rem;
		height: 1.2rem;
		flex: none;
		color: var(--accent-fg);
		background: color-mix(
			in srgb,
			var(--surface-2) calc(var(--surface-alpha) * 100%),
			transparent
		);
		border: var(--border-width) solid var(--border-color);
		border-radius: var(--radius-sm);
		box-shadow: var(--shadow-sm);
		transition:
			background var(--motion-fast) var(--motion-ease),
			border-color var(--motion-fast) var(--motion-ease);
	}
	.checkbox input:checked + .cb-box {
		background: var(--accent);
		border-color: var(--accent);
	}
	.checkbox input:focus-visible + .cb-box {
		outline: 2px solid var(--accent);
		outline-offset: 2px;
	}
	.table-scroll {
		width: 100%;
		overflow-x: auto;
		-webkit-overflow-scrolling: touch;
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

<script lang="ts">
	// File manager view for the `file_manager` Tier-1 node. Browses one attachment's
	// confined filesystem via its conventional endpoints (list/download/preview/
	// upload/mkdir/rename/move/delete). Token-only styling, so it re-skins with any
	// theme. Live: refreshes on the attachment's `files.changed` events.
	import { getContext, onMount, onDestroy } from 'svelte';
	import { Surface, Stack, Text, Button, Icon, Field, Modal } from '$lib/components';
	import { connection } from '$lib/connection.svelte';
	import {
		attGetQuery,
		attPostQuery,
		attDeleteQuery,
		attUpload,
		attResourceUrl,
		attPreview
	} from '$lib/api';
	import type { RenderContext } from './context.svelte';
	import type { UINode } from '$lib/manifest/types';

	let { node }: { node: UINode } = $props();
	const ctx = getContext<RenderContext>('render');
	const att = ctx.attachmentId;
	const listPath = node.list_source ?? 'list';

	interface Entry {
		name: string;
		path: string;
		kind: 'dir' | 'file' | 'other';
		size: number;
		modified: number;
		symlink: boolean;
	}
	interface Listing {
		path: string;
		name: string;
		segments: { name: string; path: string }[];
		entries: Entry[];
	}

	let cwd = $state('');
	let listing = $state<Listing | null>(null);
	let loading = $state(false);
	let error = $state<string | null>(null);
	let busy = $state(false); // an operation (upload/mkdir/…) in flight

	// Modals
	let preview = $state<{ entry: Entry; kind: 'image' | 'text'; text: string; url: string } | null>(
		null
	);
	let renaming = $state<Entry | null>(null);
	let renameValue = $state('');
	let confirmDelete = $state<Entry | null>(null);
	let newFolder = $state(false);
	let newFolderName = $state('');

	let fileInput: HTMLInputElement;

	async function load(path = cwd) {
		loading = !listing; // only show the spinner on first load
		error = null;
		try {
			const data = await attGetQuery<Listing>(att, listPath, { path });
			listing = data;
			cwd = data.path;
		} catch (e) {
			error = e instanceof Error ? e.message : 'failed to load directory';
		} finally {
			loading = false;
		}
	}

	function open(entry: Entry) {
		if (entry.kind === 'dir') {
			void load(entry.path);
		} else {
			void openPreview(entry);
		}
	}

	async function openPreview(entry: Entry) {
		const { contentType, text, status } = await attPreview(att, entry.path);
		if (status >= 400) {
			// No preview available — fall back to a download prompt.
			error = 'No preview for this file — use Download.';
			return;
		}
		if (contentType.startsWith('image/')) {
			preview = {
				entry,
				kind: 'image',
				text: '',
				url: attResourceUrl(att, 'preview', { path: entry.path })
			};
		} else {
			preview = { entry, kind: 'text', text, url: '' };
		}
	}

	function downloadUrl(entry: Entry): string {
		return attResourceUrl(att, 'download', { path: entry.path });
	}

	async function doUpload(files: FileList | null) {
		if (!files || files.length === 0) return;
		busy = true;
		error = null;
		try {
			for (const f of Array.from(files)) {
				await attUpload(att, 'upload', { path: cwd }, f);
			}
			await load();
		} catch (e) {
			error = e instanceof Error ? e.message : 'upload failed';
		} finally {
			busy = false;
			if (fileInput) fileInput.value = '';
		}
	}

	async function createFolder() {
		const name = newFolderName.trim();
		if (!name) return;
		busy = true;
		error = null;
		try {
			await attPostQuery(att, 'mkdir', {}, { path: cwd, name });
			newFolder = false;
			newFolderName = '';
			await load();
		} catch (e) {
			error = e instanceof Error ? e.message : 'could not create folder';
		} finally {
			busy = false;
		}
	}

	async function doRename() {
		if (!renaming) return;
		const name = renameValue.trim();
		if (!name || name === renaming.name) {
			renaming = null;
			return;
		}
		busy = true;
		error = null;
		try {
			await attPostQuery(att, 'rename', {}, { path: renaming.path, name });
			renaming = null;
			await load();
		} catch (e) {
			error = e instanceof Error ? e.message : 'rename failed';
		} finally {
			busy = false;
		}
	}

	async function doDelete() {
		if (!confirmDelete) return;
		busy = true;
		error = null;
		try {
			await attDeleteQuery(att, 'delete', { path: confirmDelete.path });
			confirmDelete = null;
			await load();
		} catch (e) {
			error = e instanceof Error ? e.message : 'delete failed';
		} finally {
			busy = false;
		}
	}

	function fmtSize(n: number): string {
		if (n < 1024) return `${n} B`;
		const u = ['KB', 'MB', 'GB', 'TB'];
		let v = n / 1024;
		let i = 0;
		while (v >= 1024 && i < u.length - 1) {
			v /= 1024;
			i++;
		}
		return `${v.toFixed(v < 10 ? 1 : 0)} ${u[i]}`;
	}

	function iconFor(entry: Entry): string {
		if (entry.kind === 'dir') return 'folder';
		const ext = entry.name.split('.').pop()?.toLowerCase() ?? '';
		if (['png', 'jpg', 'jpeg', 'gif', 'webp', 'bmp', 'svg', 'ico', 'avif'].includes(ext))
			return 'image';
		return 'file';
	}

	// Live refresh on backend changes (only re-pull if it concerns our dir).
	let offEvent: (() => void) | null = null;
	onMount(() => {
		void load('');
		offEvent = connection.onEvent((topic) => {
			if (topic === 'files.changed' || topic.startsWith(`${att}.`)) void load();
		});
	});
	onDestroy(() => offEvent?.());
</script>

<Stack gap={4}>
	<!-- Toolbar: breadcrumb + actions -->
	<Surface level={2}>
		<Stack direction="row" gap={2} align="center" justify="between" wrap>
			<nav class="crumbs" aria-label="Breadcrumb">
				{#each listing?.segments ?? [{ name: '~', path: '' }] as seg, i (seg.path)}
					{#if i > 0}<span class="sep"><Icon name="chevron-right" size={14} /></span>{/if}
					<button class="crumb" class:current={seg.path === cwd} onclick={() => load(seg.path)}>
						{seg.name}
					</button>
				{/each}
			</nav>

			<Stack direction="row" gap={2} align="center" wrap>
				<Button variant="neutral" size="sm" onclick={() => (newFolder = true)}>
					<Icon name="folder-plus" size={16} /> New folder
				</Button>
				<Button variant="accent" size="sm" onclick={() => fileInput.click()}>
					<Icon name="upload" size={16} /> Upload
				</Button>
				<input
					bind:this={fileInput}
					type="file"
					multiple
					hidden
					onchange={(e) => doUpload((e.target as HTMLInputElement).files)}
				/>
			</Stack>
		</Stack>
	</Surface>

	{#if error}
		<Surface>
			<Stack direction="row" gap={2} align="center" justify="between">
				<Text role="body">⚠ {error}</Text>
				<Button variant="ghost" size="sm" onclick={() => (error = null)}>Dismiss</Button>
			</Stack>
		</Surface>
	{/if}

	<!-- Entry grid -->
	{#if loading}
		<Text role="muted">Loading…</Text>
	{:else if listing && listing.entries.length === 0}
		<Text role="muted">This folder is empty.</Text>
	{:else if listing}
		<div class="grid" class:busy>
			{#each listing.entries as entry (entry.path)}
				<div class="cell">
					<button class="entry" ondblclick={() => open(entry)} onclick={() => open(entry)}>
						<span class="ico" class:dir={entry.kind === 'dir'}>
							<Icon name={iconFor(entry)} size={26} />
						</span>
						<span class="name" title={entry.name}>{entry.name}{entry.symlink ? ' ↗' : ''}</span>
						<span class="meta">
							{entry.kind === 'dir' ? 'folder' : fmtSize(entry.size)}
						</span>
					</button>
					<div class="row-actions">
						{#if entry.kind === 'file'}
							<a class="act" href={downloadUrl(entry)} title="Download" download>
								<Icon name="download" size={15} />
							</a>
						{/if}
						<button
							class="act"
							title="Rename"
							onclick={() => {
								renaming = entry;
								renameValue = entry.name;
							}}
						>
							<Icon name="edit" size={15} />
						</button>
						<button class="act danger" title="Delete" onclick={() => (confirmDelete = entry)}>
							<Icon name="trash" size={15} />
						</button>
					</div>
				</div>
			{/each}
		</div>
	{/if}
</Stack>

<!-- Preview -->
<Modal
	open={!!preview}
	title={preview?.entry.name ?? ''}
	size="lg"
	onclose={() => (preview = null)}
>
	{#if preview?.kind === 'image'}
		<img class="preview-img" src={preview.url} alt={preview.entry.name} />
	{:else if preview?.kind === 'text'}
		<pre class="preview-text">{preview.text}</pre>
	{/if}
	{#if preview}
		<Stack direction="row" gap={2} justify="end">
			<a class="dl-link" href={downloadUrl(preview.entry)} download>
				<Button variant="neutral" size="sm"><Icon name="download" size={15} /> Download</Button>
			</a>
		</Stack>
	{/if}
</Modal>

<!-- New folder -->
<Modal open={newFolder} title="New folder" size="sm" onclose={() => (newFolder = false)}>
	<Stack gap={3}>
		<Field label="Folder name" placeholder="untitled" bind:value={newFolderName} />
		<Stack direction="row" gap={2} justify="end">
			<Button variant="ghost" size="sm" onclick={() => (newFolder = false)}>Cancel</Button>
			<Button variant="accent" size="sm" disabled={busy} onclick={createFolder}>Create</Button>
		</Stack>
	</Stack>
</Modal>

<!-- Rename -->
<Modal open={!!renaming} title="Rename" size="sm" onclose={() => (renaming = null)}>
	<Stack gap={3}>
		<Field label="New name" bind:value={renameValue} />
		<Stack direction="row" gap={2} justify="end">
			<Button variant="ghost" size="sm" onclick={() => (renaming = null)}>Cancel</Button>
			<Button variant="accent" size="sm" disabled={busy} onclick={doRename}>Rename</Button>
		</Stack>
	</Stack>
</Modal>

<!-- Delete confirm -->
<Modal open={!!confirmDelete} title="Delete" size="sm" onclose={() => (confirmDelete = null)}>
	<Stack gap={3}>
		<Text role="body">
			Permanently delete <strong>{confirmDelete?.name}</strong>{confirmDelete?.kind === 'dir'
				? ' and everything inside it'
				: ''}? This can't be undone.
		</Text>
		<Stack direction="row" gap={2} justify="end">
			<Button variant="ghost" size="sm" onclick={() => (confirmDelete = null)}>Cancel</Button>
			<Button variant="danger" size="sm" disabled={busy} onclick={doDelete}>Delete</Button>
		</Stack>
	</Stack>
</Modal>

<style>
	.crumbs {
		display: flex;
		align-items: center;
		gap: var(--space-1);
		flex-wrap: wrap;
		min-width: 0;
	}
	.crumb {
		background: transparent;
		border: none;
		color: var(--muted);
		font: inherit;
		font-weight: var(--font-weight-bold);
		cursor: pointer;
		padding: var(--space-1) var(--space-2);
		border-radius: var(--radius-md);
	}
	.crumb:hover {
		color: var(--fg);
		background: var(--surface);
	}
	.crumb.current {
		color: var(--accent);
	}
	.sep {
		display: inline-flex;
		color: var(--muted);
		opacity: 0.6;
	}

	.grid {
		display: grid;
		grid-template-columns: repeat(auto-fill, minmax(150px, 1fr));
		gap: var(--space-2);
	}
	.grid.busy {
		opacity: 0.6;
		pointer-events: none;
	}
	.cell {
		position: relative;
	}
	.entry {
		display: flex;
		flex-direction: column;
		align-items: center;
		gap: var(--space-1);
		width: 100%;
		padding: var(--space-3) var(--space-2);
		background: color-mix(
			in srgb,
			var(--surface) calc(var(--surface-alpha, 1) * 100%),
			transparent
		);
		border: var(--border-width) solid var(--border-color);
		border-radius: var(--radius-md);
		color: var(--fg);
		cursor: pointer;
		text-align: center;
		transition:
			transform var(--motion-fast) var(--motion-ease),
			border-color var(--motion-fast) var(--motion-ease);
	}
	.entry:hover {
		border-color: var(--accent);
		transform: translateY(calc(var(--depth) * -1px));
	}
	.ico {
		color: var(--muted);
		display: inline-flex;
	}
	.ico.dir {
		color: var(--accent);
	}
	.name {
		font-size: 0.85rem;
		font-weight: var(--font-weight-bold);
		max-width: 100%;
		overflow: hidden;
		text-overflow: ellipsis;
		white-space: nowrap;
	}
	.meta {
		font-size: 0.72rem;
		color: var(--muted);
	}
	.row-actions {
		position: absolute;
		top: var(--space-1);
		right: var(--space-1);
		display: flex;
		gap: 2px;
		opacity: 0;
		transition: opacity var(--motion-fast) var(--motion-ease);
	}
	.cell:hover .row-actions,
	.cell:focus-within .row-actions {
		opacity: 1;
	}
	.act {
		display: inline-flex;
		align-items: center;
		justify-content: center;
		padding: var(--space-1);
		background: var(--surface-2);
		color: var(--muted);
		border: var(--border-width) solid var(--border-color);
		border-radius: var(--radius-sm);
		cursor: pointer;
	}
	.act:hover {
		color: var(--fg);
	}
	.act.danger:hover {
		color: var(--danger);
		border-color: var(--danger);
	}
	.preview-img {
		max-width: 100%;
		max-height: 60dvh;
		display: block;
		margin: 0 auto;
		border-radius: var(--radius-md);
	}
	.preview-text {
		margin: 0;
		max-height: 60dvh;
		overflow: auto;
		padding: var(--space-3);
		background: var(--surface);
		border: var(--border-width) solid var(--border-color);
		border-radius: var(--radius-md);
		font-family: ui-monospace, 'JetBrains Mono', monospace;
		font-size: 0.82rem;
		white-space: pre-wrap;
		word-break: break-word;
	}
	.dl-link,
	.act {
		text-decoration: none;
	}
</style>

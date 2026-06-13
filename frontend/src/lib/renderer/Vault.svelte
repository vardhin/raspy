<script lang="ts">
	// Zero-knowledge vault UI. Renders folders + files from the decrypted
	// manifest, uploads any file type (client-encrypted) into the current folder,
	// and previews on demand. Media inside a folder opens in a carousel that
	// prefetches/decrypts neighbours for seamless flipping. The Pi only ever
	// stores opaque ciphertext (and never sees folder names — they live inside the
	// encrypted manifest). Token-only styling.
	import { onMount, onDestroy } from 'svelte';
	import { Surface, Stack, Text, Button, Icon, Field, Modal } from '$lib/components';
	import { connection } from '$lib/connection.svelte';
	import { auth } from '$lib/auth.svelte';
	import {
		loadManifest,
		saveManifest,
		uploadFile,
		deleteBlob,
		descendantIds,
		type Manifest,
		type VaultEntry,
		type VaultFolder
	} from '$lib/crypto/vault';
	import * as vaultCache from '$lib/crypto/vaultCache';

	let manifest = $state<Manifest>({ version: 2, folders: [], entries: [] });
	let loading = $state(true);
	let error = $state<string | null>(null);
	let locked = $derived(auth.masterKey === null);

	// Folder navigation: null = root.
	let currentFolderId = $state<string | null>(null);

	let subFolders = $derived(
		manifest.folders
			.filter((f) => f.parentId === currentFolderId)
			.sort((a, b) => a.name.localeCompare(b.name))
	);
	let items = $derived(manifest.entries.filter((e) => e.parentId === currentFolderId));
	// Media in this folder, in display order — the carousel set.
	let mediaItems = $derived(items.filter((e) => isImage(e.type) || isVideo(e.type)));

	// Breadcrumb trail from root to the current folder.
	let trail = $derived.by(() => {
		const out: VaultFolder[] = [];
		let id = currentFolderId;
		const byId = new Map(manifest.folders.map((f) => [f.id, f]));
		while (id) {
			const f = byId.get(id);
			if (!f) break;
			out.unshift(f);
			id = f.parentId;
		}
		return out;
	});

	// Upload progress (0..1).
	let uploadPct = $state<number | null>(null);

	// New-folder modal.
	let newFolderOpen = $state(false);
	let newFolderName = $state('');

	// Preview/carousel state. `index` points into mediaItems for media; for
	// non-media (e.g. PDF) we open a single entry with index = -1.
	let preview = $state<{ entry: VaultEntry; url: string; pct: number | null; index: number } | null>(
		null
	);

	let fileInput = $state<HTMLInputElement>();

	async function refresh() {
		loading = true;
		error = null;
		try {
			manifest = await loadManifest();
		} catch (e) {
			error = e instanceof Error ? e.message : 'failed to load vault';
		} finally {
			loading = false;
		}
	}

	async function onPick(e: Event) {
		const files = (e.target as HTMLInputElement).files;
		if (!files?.length) return;
		error = null;
		try {
			for (const file of Array.from(files)) {
				uploadPct = 0;
				const entry = await uploadFile(file, currentFolderId, (f) => (uploadPct = f));
				manifest.entries = [entry, ...manifest.entries];
				await saveManifest(manifest);
			}
		} catch (err) {
			error = err instanceof Error ? err.message : 'upload failed';
		} finally {
			uploadPct = null;
			if (fileInput) fileInput.value = '';
		}
	}

	// --- folders -------------------------------------------------------------

	async function createFolder() {
		const name = newFolderName.trim();
		if (!name) return;
		const folder: VaultFolder = {
			id: crypto.randomUUID(),
			name,
			parentId: currentFolderId,
			created: Date.now() / 1000
		};
		newFolderOpen = false;
		newFolderName = '';
		try {
			manifest.folders = [...manifest.folders, folder];
			await saveManifest(manifest);
		} catch (err) {
			error = err instanceof Error ? err.message : 'failed to create folder';
		}
	}

	async function removeFolder(folder: VaultFolder) {
		if (
			!confirm(`Delete folder "${folder.name}" and everything inside? This cannot be undone.`)
		)
			return;
		try {
			const ids = descendantIds(manifest.folders, folder.id);
			const doomed = manifest.entries.filter((e) => e.parentId && ids.has(e.parentId));
			// Remove ciphertext from the Pi for every contained file.
			await Promise.all(doomed.map((e) => deleteBlob(e.hash)));
			manifest.folders = manifest.folders.filter((f) => !ids.has(f.id));
			manifest.entries = manifest.entries.filter((e) => !(e.parentId && ids.has(e.parentId)));
			await saveManifest(manifest);
		} catch (err) {
			error = err instanceof Error ? err.message : 'failed to delete folder';
		}
	}

	function openFolder(id: string | null) {
		closePreview();
		currentFolderId = id;
	}

	// --- preview + carousel --------------------------------------------------

	async function open(entry: VaultEntry) {
		const index = mediaItems.findIndex((m) => m.hash === entry.hash);
		await showAt(entry, index);
		if (index >= 0) prefetchAround(index);
	}

	// Load (or reuse from cache) the blob for `entry` into the preview.
	async function showAt(entry: VaultEntry, index: number) {
		preview = { entry, url: '', pct: 0, index };
		try {
			const url = await vaultCache.get(entry, (f) => {
				if (preview?.entry.hash === entry.hash) preview.pct = f;
			});
			if (preview?.entry.hash === entry.hash) {
				preview.url = url;
				preview.pct = null;
			}
		} catch (err) {
			error = err instanceof Error ? err.message : 'failed to open';
			closePreview();
		}
	}

	function step(delta: number) {
		if (!preview || preview.index < 0 || mediaItems.length === 0) return;
		const next = (preview.index + delta + mediaItems.length) % mediaItems.length;
		const entry = mediaItems[next];
		void showAt(entry, next);
		prefetchAround(next);
	}

	// Decrypt next 5 + previous 2 neighbours in the background.
	function prefetchAround(index: number) {
		const ahead = [1, 2, 3, 4, 5].map((d) => mediaItems[index + d]);
		const behind = [1, 2].map((d) => mediaItems[index - d]);
		vaultCache.prefetch([...ahead, ...behind].filter(Boolean) as VaultEntry[]);
	}

	async function download(entry: VaultEntry) {
		try {
			const url = await vaultCache.get(entry);
			const a = document.createElement('a');
			a.href = url;
			a.download = entry.name;
			a.click();
		} catch (err) {
			error = err instanceof Error ? err.message : 'download failed';
		}
	}

	async function remove(entry: VaultEntry) {
		if (!confirm(`Delete "${entry.name}"? This cannot be undone.`)) return;
		try {
			await deleteBlob(entry.hash);
			manifest.entries = manifest.entries.filter((x) => x.hash !== entry.hash);
			await saveManifest(manifest);
		} catch (err) {
			error = err instanceof Error ? err.message : 'delete failed';
		}
	}

	function closePreview() {
		// Object URLs are owned by vaultCache; don't revoke here.
		preview = null;
	}

	function onPreviewKey(e: KeyboardEvent) {
		if (!preview) return;
		if (e.key === 'Escape') closePreview();
		else if (e.key === 'ArrowRight') step(1);
		else if (e.key === 'ArrowLeft') step(-1);
	}

	function fmtSize(n: number): string {
		if (n < 1024) return `${n} B`;
		if (n < 1024 * 1024) return `${(n / 1024).toFixed(1)} KB`;
		if (n < 1024 * 1024 * 1024) return `${(n / 1024 / 1024).toFixed(1)} MB`;
		return `${(n / 1024 / 1024 / 1024).toFixed(2)} GB`;
	}

	function isImage(t: string) {
		return t.startsWith('image/');
	}
	function isVideo(t: string) {
		return t.startsWith('video/');
	}
	function isAudio(t: string) {
		return t.startsWith('audio/');
	}
	function isPdf(t: string) {
		return t === 'application/pdf';
	}

	let offEvent: (() => void) | null = null;
	onMount(() => {
		void refresh();
		// Refresh when another device changes the vault.
		offEvent = connection.onEvent((topic) => {
			if (topic === 'vault.changed') void refresh();
		});
	});
	onDestroy(() => {
		offEvent?.();
		closePreview();
		vaultCache.clear();
	});

	// Drop decrypted blobs when the vault locks (keys gone).
	$effect(() => {
		if (locked) {
			closePreview();
			vaultCache.clear();
		}
	});
</script>

<svelte:window onkeydown={preview ? onPreviewKey : undefined} />

{#if locked}
	<Surface level={2}>
		<Stack gap={2} align="center">
			<Icon name="lock" size={28} />
			<Text role="heading">Vault locked</Text>
			<Text role="muted">Sign in with your password to unlock the vault.</Text>
		</Stack>
	</Surface>
{:else}
	<Stack gap={3}>
		<Surface level={2}>
			<Stack direction="row" gap={2} align="center" justify="between">
				<!-- Breadcrumb -->
				<nav class="crumbs">
					<button class="crumb" onclick={() => openFolder(null)}>Vault</button>
					{#each trail as f (f.id)}
						<Icon name="chevron-right" size={14} />
						<button class="crumb" onclick={() => openFolder(f.id)}>{f.name}</button>
					{/each}
				</nav>
				<div class="toolbar">
					<Button variant="ghost" size="sm" onclick={() => (newFolderOpen = true)}>
						<Icon name="folder-plus" size={16} />
						New folder
					</Button>
					<input
						bind:this={fileInput}
						type="file"
						multiple
						style="display:none"
						onchange={onPick}
					/>
					<Button onclick={() => fileInput?.click()} disabled={uploadPct !== null}>
						<Icon name="upload" size={16} />
						{uploadPct !== null ? `Encrypting… ${Math.round(uploadPct * 100)}%` : 'Upload'}
					</Button>
				</div>
			</Stack>
		</Surface>

		{#if error}
			<span class="err">{error}</span>
		{/if}

		{#if loading}
			<Text role="muted">Loading…</Text>
		{:else if subFolders.length === 0 && items.length === 0}
			<Text role="muted">
				{currentFolderId === null
					? "Vault is empty. Upload anything — it's encrypted before it leaves this device."
					: 'This folder is empty.'}
			</Text>
		{:else}
			<Stack gap={2}>
				{#each subFolders as folder (folder.id)}
					<Surface interactive>
						<Stack direction="row" gap={2} align="center" justify="between">
							<button class="row-main" onclick={() => openFolder(folder.id)}>
								<Icon name="folder" size={18} />
								<span class="name">{folder.name}</span>
							</button>
							<div class="actions">
								<Button variant="danger" size="sm" onclick={() => removeFolder(folder)}>
									<Icon name="trash" size={15} />
								</Button>
							</div>
						</Stack>
					</Surface>
				{/each}

				{#each items as entry (entry.hash)}
					<Surface interactive>
						<Stack direction="row" gap={2} align="center" justify="between">
							<button class="row-main" onclick={() => open(entry)}>
								<Icon
									name={isImage(entry.type)
										? 'image'
										: isVideo(entry.type)
											? 'video'
											: isPdf(entry.type)
												? 'file-text'
												: 'file'}
									size={18}
								/>
								<span class="name">{entry.name}</span>
								<span class="meta">{fmtSize(entry.size)}</span>
							</button>
							<div class="actions">
								<Button variant="ghost" size="sm" onclick={() => download(entry)}>
									<Icon name="download" size={15} />
								</Button>
								<Button variant="danger" size="sm" onclick={() => remove(entry)}>
									<Icon name="trash" size={15} />
								</Button>
							</div>
						</Stack>
					</Surface>
				{/each}
			</Stack>
		{/if}
	</Stack>

	<Modal open={newFolderOpen} title="New folder" size="sm" onclose={() => (newFolderOpen = false)}>
		<Stack gap={3}>
			<Field
				label="Folder name"
				bind:value={newFolderName}
				placeholder="e.g. Trip photos"
				onkeydown={(e: KeyboardEvent) => e.key === 'Enter' && createFolder()}
			/>
			<Stack direction="row" gap={2} justify="end">
				<Button variant="ghost" onclick={() => (newFolderOpen = false)}>Cancel</Button>
				<Button onclick={createFolder} disabled={!newFolderName.trim()}>Create</Button>
			</Stack>
		</Stack>
	</Modal>

	{#if preview}
		<button class="scrim" aria-label="Close preview" onclick={closePreview}></button>
		<div class="preview" role="dialog" aria-modal="true">
			<Surface level={2}>
				<Stack gap={2}>
					<Stack direction="row" gap={2} align="center" justify="between">
						<Text role="heading">{preview.entry.name}</Text>
						<Stack direction="row" gap={2} align="center">
							{#if preview.index >= 0 && mediaItems.length > 1}
								<Text role="muted">{preview.index + 1} / {mediaItems.length}</Text>
							{/if}
							<Button variant="ghost" size="sm" onclick={closePreview}>
								<Icon name="x" size={18} />
							</Button>
						</Stack>
					</Stack>

					<div class="stage">
						{#if preview.index >= 0 && mediaItems.length > 1}
							<button class="nav prev" aria-label="Previous" onclick={() => step(-1)}>
								<Icon name="chevron-left" size={24} />
							</button>
							<button class="nav next" aria-label="Next" onclick={() => step(1)}>
								<Icon name="chevron-right" size={24} />
							</button>
						{/if}

						{#if preview.pct !== null}
							<Text role="muted">Decrypting… {Math.round(preview.pct * 100)}%</Text>
						{:else if isImage(preview.entry.type)}
							<img src={preview.url} alt={preview.entry.name} />
						{:else if isVideo(preview.entry.type)}
							<!-- svelte-ignore a11y_media_has_caption -->
							<video src={preview.url} controls></video>
						{:else if isAudio(preview.entry.type)}
							<audio src={preview.url} controls></audio>
						{:else if isPdf(preview.entry.type)}
							<iframe class="pdf" src={preview.url} title={preview.entry.name}></iframe>
						{:else}
							<Stack gap={2} align="center">
								<Text role="muted">No inline preview for {preview.entry.type || 'this type'}.</Text>
								<Button onclick={() => download(preview!.entry)}>Download</Button>
							</Stack>
						{/if}
					</div>
				</Stack>
			</Surface>
		</div>
	{/if}
{/if}

<style>
	.err {
		color: var(--danger);
		font-size: 0.9rem;
	}
	.crumbs {
		display: flex;
		align-items: center;
		gap: var(--space-1);
		min-width: 0;
		overflow: hidden;
		color: var(--muted);
	}
	.crumb {
		background: none;
		border: none;
		color: var(--muted);
		font: inherit;
		cursor: pointer;
		padding: 0;
		white-space: nowrap;
	}
	.crumb:hover {
		color: var(--fg);
		text-decoration: underline;
	}
	.crumbs .crumb:last-of-type {
		color: var(--fg);
	}
	.toolbar {
		display: flex;
		gap: var(--space-2);
		flex: none;
	}
	.row-main {
		display: flex;
		align-items: center;
		gap: var(--space-2);
		flex: 1;
		min-width: 0;
		background: none;
		border: none;
		color: var(--fg);
		font: inherit;
		cursor: pointer;
		text-align: left;
		padding: 0;
	}
	.name {
		overflow: hidden;
		text-overflow: ellipsis;
		white-space: nowrap;
	}
	.meta {
		color: var(--muted);
		font-size: 0.85rem;
		flex: none;
	}
	.actions {
		display: flex;
		gap: var(--space-1);
		flex: none;
	}
	.scrim {
		position: fixed;
		inset: 0;
		z-index: 60;
		border: none;
		background: var(--overlay, rgba(0, 0, 0, 0.5));
		cursor: pointer;
	}
	.preview {
		position: fixed;
		z-index: 61;
		top: 50%;
		left: 50%;
		transform: translate(-50%, -50%);
		width: min(720px, 92vw);
		max-height: 88vh;
		overflow: auto;
	}
	.stage {
		position: relative;
		display: flex;
		align-items: center;
		justify-content: center;
		min-height: 120px;
	}
	.preview img,
	.preview video {
		max-width: 100%;
		max-height: 70vh;
		border-radius: var(--radius-md);
	}
	.pdf {
		width: 100%;
		height: 70vh;
		border: none;
		border-radius: var(--radius-md);
		background: var(--surface);
	}
	.nav {
		position: absolute;
		top: 50%;
		transform: translateY(-50%);
		z-index: 1;
		display: inline-flex;
		align-items: center;
		justify-content: center;
		width: 40px;
		height: 40px;
		border: none;
		border-radius: 50%;
		background: var(--overlay, rgba(0, 0, 0, 0.5));
		color: var(--fg);
		cursor: pointer;
	}
	.nav:hover {
		background: var(--surface-2);
	}
	.nav.prev {
		left: var(--space-1);
	}
	.nav.next {
		right: var(--space-1);
	}
</style>

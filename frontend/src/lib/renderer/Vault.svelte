<script lang="ts">
	// Zero-knowledge vault UI. Renders the file list from the decrypted manifest,
	// uploads any file type (client-encrypted), and previews on demand by
	// streaming + decrypting the blob in-browser. The Pi only ever stores opaque
	// ciphertext. Token-only styling.
	import { onMount, onDestroy } from 'svelte';
	import { Surface, Stack, Text, Button, Icon } from '$lib/components';
	import { connection } from '$lib/connection.svelte';
	import { auth } from '$lib/auth.svelte';
	import {
		loadManifest,
		saveManifest,
		uploadFile,
		downloadAndDecrypt,
		deleteBlob,
		type Manifest,
		type VaultEntry
	} from '$lib/crypto/vault';

	let manifest = $state<Manifest>({ version: 1, entries: [] });
	let loading = $state(true);
	let error = $state<string | null>(null);
	let locked = $derived(auth.masterKey === null);

	// Upload progress (0..1) and current preview.
	let uploadPct = $state<number | null>(null);
	let preview = $state<{ entry: VaultEntry; url: string; pct: number | null } | null>(null);

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
				const entry = await uploadFile(file, (f) => (uploadPct = f));
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

	async function open(entry: VaultEntry) {
		closePreview();
		preview = { entry, url: '', pct: 0 };
		try {
			const blob = await downloadAndDecrypt(entry, (f) => {
				if (preview) preview.pct = f;
			});
			if (preview?.entry.hash === entry.hash) {
				preview.url = URL.createObjectURL(blob);
				preview.pct = null;
			}
		} catch (err) {
			error = err instanceof Error ? err.message : 'failed to open';
			closePreview();
		}
	}

	async function download(entry: VaultEntry) {
		const blob = await downloadAndDecrypt(entry);
		const url = URL.createObjectURL(blob);
		const a = document.createElement('a');
		a.href = url;
		a.download = entry.name;
		a.click();
		URL.revokeObjectURL(url);
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
		if (preview?.url) URL.revokeObjectURL(preview.url);
		preview = null;
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
	});
</script>

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
				<Text role="muted">
					{manifest.entries.length} item{manifest.entries.length === 1 ? '' : 's'} · end-to-end encrypted
				</Text>
				<div>
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
		{:else if manifest.entries.length === 0}
			<Text role="muted">Vault is empty. Upload anything — it's encrypted before it leaves this device.</Text>
		{:else}
			<Stack gap={2}>
				{#each manifest.entries as entry (entry.hash)}
					<Surface interactive>
						<Stack direction="row" gap={2} align="center" justify="between">
							<button class="row-main" onclick={() => open(entry)}>
								<Icon
									name={isImage(entry.type)
										? 'image'
										: isVideo(entry.type)
											? 'video'
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

	{#if preview}
		<button class="scrim" aria-label="Close preview" onclick={closePreview}></button>
		<div class="preview" role="dialog" aria-modal="true">
			<Surface level={2}>
				<Stack gap={2}>
					<Stack direction="row" gap={2} align="center" justify="between">
						<Text role="heading">{preview.entry.name}</Text>
						<Button variant="ghost" size="sm" onclick={closePreview}>
							<Icon name="x" size={18} />
						</Button>
					</Stack>
					{#if preview.pct !== null}
						<Text role="muted">Decrypting… {Math.round(preview.pct * 100)}%</Text>
					{:else if isImage(preview.entry.type)}
						<img src={preview.url} alt={preview.entry.name} />
					{:else if isVideo(preview.entry.type)}
						<!-- svelte-ignore a11y_media_has_caption -->
						<video src={preview.url} controls></video>
					{:else if isAudio(preview.entry.type)}
						<audio src={preview.url} controls></audio>
					{:else}
						<Stack gap={2} align="center">
							<Text role="muted">No inline preview for {preview.entry.type || 'this type'}.</Text>
							<Button onclick={() => download(preview!.entry)}>Download</Button>
						</Stack>
					{/if}
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
	.preview img,
	.preview video {
		max-width: 100%;
		max-height: 70vh;
		border-radius: var(--radius-md);
	}
</style>

<script lang="ts">
	// Dropbox UI — drop end-to-end-encrypted files onto another account, and browse
	// what's been dropped to you (incl. chat media), filterable by sender.
	//
	// All crypto is client-side: files are encrypted under a fresh data key and the
	// metadata is sealed to the recipient's public key; the Pi only stores opaque
	// ciphertext it can't read. Reads the account directory from the identity
	// attachment; gates on the vault being unlocked (the keypair derives from the
	// master key). Token-only styling.
	import { onMount, onDestroy } from 'svelte';
	import { Surface, Stack, Text, Button, Icon, Spinner, AccountPicker, MediaBubble } from '$lib/components';
	import { auth } from '$lib/auth.svelte';
	import { connection } from '$lib/connection.svelte';
	import { fetchDirectory, type DirectoryEntry } from '$lib/crypto/identity';
	import {
		sendFile,
		listItems,
		listSenders,
		downloadAndDecrypt,
		deleteItem,
		type OpenedDrop,
		type Sender
	} from '$lib/crypto/dropbox';

	let locked = $derived(auth.masterKey === null);
	let ready = $state(false);
	let error = $state<string | null>(null);

	let directory = $state<DirectoryEntry[]>([]);
	let recipients = $derived(directory.filter((d) => d.username !== auth.username));
	let selectedRecipient = $state<string | null>(null);

	let items = $state<OpenedDrop[]>([]);
	let senders = $state<Sender[]>([]);
	let filterFrom = $state<string | null>(null);

	let sending = $state(false);
	let sendPct = $state<number | null>(null);
	let fileInput = $state<HTMLInputElement>();
	let dragOver = $state(false);

	let unsub: (() => void) | null = null;

	onMount(async () => {
		if (locked) return;
		try {
			await auth.ensureIdentity();
			await refreshAll();
			ready = true;
			// Live: a new drop to me re-pulls the inbox.
			unsub = connection.onEvent((topic, payload) => {
				const p = payload as { to?: string } | null;
				if (topic === 'dropbox.received' && p?.to === auth.username) refreshInbox();
				else if (topic === 'dropbox.changed') refreshInbox();
			});
		} catch (e) {
			error = e instanceof Error ? e.message : 'Failed to load dropbox.';
		}
	});

	// Provision + load once the vault unlocks if it was locked at mount.
	$effect(() => {
		if (!locked && !ready && !error) {
			auth
				.ensureIdentity()
				.then(refreshAll)
				.then(() => (ready = true))
				.catch((e) => (error = e instanceof Error ? e.message : 'Failed to load dropbox.'));
		}
	});

	onDestroy(() => unsub?.());

	async function refreshAll() {
		directory = await fetchDirectory();
		await refreshInbox();
	}

	async function refreshInbox() {
		[items, senders] = await Promise.all([listItems(filterFrom ?? undefined), listSenders()]);
	}

	async function applyFilter(from: string | null) {
		filterFrom = from;
		items = await listItems(from ?? undefined);
	}

	async function onFilesPicked(files: FileList | File[]) {
		const list = Array.from(files);
		if (!list.length) return;
		if (!selectedRecipient) {
			error = 'Pick a recipient account first.';
			return;
		}
		const rec = directory.find((d) => d.username === selectedRecipient);
		if (!rec) {
			error = 'That account has no published key yet.';
			return;
		}
		error = null;
		sending = true;
		try {
			for (let i = 0; i < list.length; i++) {
				await sendFile(rec.username, rec.public_key, list[i], 'drop', (f) => {
					sendPct = (i + f) / list.length;
				});
			}
		} catch (e) {
			error = e instanceof Error ? e.message : 'Send failed.';
		} finally {
			sending = false;
			sendPct = null;
		}
	}

	function onDrop(e: DragEvent) {
		e.preventDefault();
		dragOver = false;
		if (e.dataTransfer?.files?.length) onFilesPicked(e.dataTransfer.files);
	}

	// One decrypted media item per inbox row (image/video preview).
	function isPreviewable(it: OpenedDrop): boolean {
		const t = it.meta?.type ?? '';
		return t.startsWith('image/') || t.startsWith('video/');
	}

	async function loadOne(it: OpenedDrop): Promise<Blob> {
		if (!it.meta) throw new Error('cannot open (not addressed to you)');
		return downloadAndDecrypt(it, it.meta);
	}

	async function download(it: OpenedDrop) {
		if (!it.meta) return;
		const blob = await downloadAndDecrypt(it, it.meta);
		const url = URL.createObjectURL(blob);
		const a = document.createElement('a');
		a.href = url;
		a.download = it.meta.name || 'file';
		a.click();
		setTimeout(() => URL.revokeObjectURL(url), 1000);
	}

	async function remove(it: OpenedDrop) {
		await deleteItem(it.id);
		await refreshInbox();
	}

	function fmtSize(n: number): string {
		if (n < 1024) return `${n} B`;
		if (n < 1024 * 1024) return `${(n / 1024).toFixed(1)} KB`;
		return `${(n / 1024 / 1024).toFixed(1)} MB`;
	}
</script>

{#if locked}
	<Surface>
		<Stack gap={2} align="center">
			<Icon name="lock" size={28} />
			<Text role="muted">Unlock your vault to use the dropbox.</Text>
		</Stack>
	</Surface>
{:else if error && !ready}
	<Surface><Text role="muted">{error}</Text></Surface>
{:else if !ready}
	<Surface><Stack align="center"><Spinner /></Stack></Surface>
{:else}
	<Stack gap={4}>
		<!-- Send panel -->
		<Surface>
			<Stack gap={3}>
				<Text role="heading">Drop a file</Text>
				<Text role="muted">Pick an account, then choose or drag files. They're encrypted so only that account can open them.</Text>
				<AccountPicker
					accounts={recipients.map((r) => ({ username: r.username, role: r.role }))}
					bind:selected={selectedRecipient}
				/>
				<!-- svelte-ignore a11y_no_static_element_interactions -->
				<div
					class="dropzone"
					class:over={dragOver}
					role="button"
					tabindex="0"
					onclick={() => fileInput?.click()}
					onkeydown={(e) => (e.key === 'Enter' || e.key === ' ') && fileInput?.click()}
					ondragover={(e) => {
						e.preventDefault();
						dragOver = true;
					}}
					ondragleave={() => (dragOver = false)}
					ondrop={onDrop}
				>
					{#if sending}
						<Spinner />
						<Text role="muted">Encrypting & sending… {sendPct != null ? Math.round(sendPct * 100) + '%' : ''}</Text>
					{:else}
						<Icon name="upload" size={26} />
						<Text role="muted">Drop files here, or click to choose</Text>
					{/if}
					<input
						bind:this={fileInput}
						type="file"
						multiple
						hidden
						onchange={(e) => {
							const t = e.currentTarget as HTMLInputElement;
							if (t.files) onFilesPicked(t.files);
							t.value = '';
						}}
					/>
				</div>
				{#if error}<Text role="muted">{error}</Text>{/if}
			</Stack>
		</Surface>

		<!-- Inbox -->
		<Surface>
			<Stack gap={3}>
				<Text role="heading">Received</Text>
				{#if senders.length}
					<div class="filters">
						<button class="chip" class:on={filterFrom === null} onclick={() => applyFilter(null)}>All</button>
						{#each senders as s (s.from)}
							<button class="chip" class:on={filterFrom === s.from} onclick={() => applyFilter(s.from)}>
								{s.from} <span class="count">{s.count}</span>
							</button>
						{/each}
					</div>
				{/if}
				{#if items.length === 0}
					<Text role="muted">Nothing dropped to you yet.</Text>
				{:else}
					<div class="grid">
						{#each items as it (it.id)}
							<Surface level={2}>
								<Stack gap={2}>
									<div class="head">
										<Stack gap={1}>
											<Text role="label">{it.meta?.name ?? '(locked)'}</Text>
											<Text role="muted">
												from {it.from}{it.source === 'chat' ? ' · chat' : ''} · {fmtSize(it.size)}
											</Text>
										</Stack>
										<Icon name={it.source === 'chat' ? 'message-circle' : 'inbox'} size={16} />
									</div>
									{#if it.meta && isPreviewable(it)}
										<MediaBubble items={[{ name: it.meta.name, type: it.meta.type }]} load={() => loadOne(it)} compact />
									{/if}
									<div class="actions">
										<Button size="sm" variant="ghost" disabled={!it.meta} onclick={() => download(it)}>
											<Icon name="download" size={15} /> Download
										</Button>
										<Button size="sm" variant="ghost" onclick={() => remove(it)}>
											<Icon name="trash-2" size={15} />
										</Button>
									</div>
								</Stack>
							</Surface>
						{/each}
					</div>
				{/if}
			</Stack>
		</Surface>
	</Stack>
{/if}

<style>
	.dropzone {
		display: flex;
		flex-direction: column;
		align-items: center;
		gap: var(--space-2);
		padding: var(--space-6) var(--space-4);
		border: 2px dashed var(--border-color);
		border-radius: var(--radius-lg);
		cursor: pointer;
		transition: border-color var(--motion-fast) var(--motion-ease), background var(--motion-fast);
	}
	.dropzone.over {
		border-color: var(--accent);
		background: color-mix(in srgb, var(--accent) 10%, transparent);
	}
	.filters {
		display: flex;
		flex-wrap: wrap;
		gap: var(--space-2);
	}
	.chip {
		display: inline-flex;
		align-items: center;
		gap: var(--space-1);
		padding: var(--space-1) var(--space-3);
		border-radius: var(--radius-full, 999px);
		border: var(--border-width) solid var(--border-color);
		background: transparent;
		color: var(--fg);
		cursor: pointer;
		font-size: 0.85rem;
	}
	.chip.on {
		background: color-mix(in srgb, var(--accent) 22%, transparent);
	}
	.chip .count {
		opacity: 0.6;
		font-size: 0.75rem;
	}
	.grid {
		display: grid;
		grid-template-columns: repeat(auto-fill, minmax(220px, 1fr));
		gap: var(--space-3);
	}
	.head {
		display: flex;
		justify-content: space-between;
		align-items: flex-start;
		gap: var(--space-2);
	}
	.actions {
		display: flex;
		gap: var(--space-2);
		justify-content: flex-end;
	}
</style>

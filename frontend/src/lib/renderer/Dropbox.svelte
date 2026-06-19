<script lang="ts">
	// Dropbox UI — a two-tab app:
	//   • Drop — pick a recipient and drop encrypted files onto them.
	//   • See  — an account pill bar; pick an account to browse everything they sent
	//            you (files + chat media), paginated mail-app style, with a filename
	//            search and timestamps.
	//
	// All crypto is client-side: files are encrypted under a fresh data key and the
	// metadata is sealed to the recipient's public key; the Pi only stores opaque
	// ciphertext. Media previews are decrypted through the app-scoped mediaCache, so
	// they decrypt once and are freed when you leave the app. Token-only styling.
	import { onMount, onDestroy, tick } from 'svelte';
	import { Surface, Stack, Text, Button, Icon, Spinner, AccountPicker, MediaBubble, Field } from '$lib/components';
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
	import { clearMediaCache } from '$lib/crypto/mediaCache';

	type Tab = 'drop' | 'see';
	const PAGE = 30;

	let locked = $derived(auth.masterKey === null);
	let ready = $state(false);
	let error = $state<string | null>(null);
	let tab = $state<Tab>('drop');

	let directory = $state<DirectoryEntry[]>([]);
	let recipients = $derived(directory.filter((d) => d.username !== auth.username));

	// --- Drop tab state ---
	let selectedRecipient = $state<string | null>(null);
	let sending = $state(false);
	let sendPct = $state<number | null>(null);
	let fileInput = $state<HTMLInputElement>();
	let dragOver = $state(false);

	// --- See tab state ---
	let senders = $state<Sender[]>([]);
	let seeAccount = $state<string | null>(null);
	let items = $state<OpenedDrop[]>([]);
	let search = $state('');
	let hasMore = $state(false);
	let loadingMore = $state(false);
	let sentinel = $state<HTMLElement>();

	// Filename search runs client-side (names live in the sealed metadata).
	let shown = $derived(
		search.trim()
			? items.filter((it) => (it.meta?.name ?? '').toLowerCase().includes(search.trim().toLowerCase()))
			: items
	);

	let unsub: (() => void) | null = null;

	onMount(async () => {
		if (locked) return;
		await boot();
	});

	$effect(() => {
		if (!locked && !ready && !error) boot();
	});

	async function boot() {
		try {
			await auth.ensureIdentity();
			directory = await fetchDirectory();
			senders = await listSenders();
			ready = true;
			unsub = connection.onEvent((topic, payload) => {
				const p = payload as { to?: string; from?: string } | null;
				if (topic === 'dropbox.received' && p?.to === auth.username) {
					listSenders().then((s) => (senders = s));
					if (tab === 'see' && seeAccount && p?.from === seeAccount) openAccount(seeAccount);
				} else if (topic === 'dropbox.changed' && tab === 'see' && seeAccount) {
					openAccount(seeAccount);
				}
			});
		} catch (e) {
			error = e instanceof Error ? e.message : 'Failed to load dropbox.';
		}
	}

	onDestroy(() => {
		unsub?.();
		clearMediaCache(); // free decrypted previews when leaving the app
	});

	// --- Drop tab ---
	async function onFilesPicked(files: FileList | File[]) {
		const list = Array.from(files);
		if (!list.length) return;
		if (!selectedRecipient) {
			error = 'Pick a recipient account first.';
			return;
		}
		const rec = directory.find((d) => d.username === selectedRecipient);
		if (!rec || !rec.public_key) {
			error = 'That account has no published key yet.';
			return;
		}
		const recKey = rec.public_key;
		error = null;
		sending = true;
		try {
			for (let i = 0; i < list.length; i++) {
				await sendFile(rec.username, recKey, list[i], 'drop', (f) => {
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

	// --- See tab ---
	async function openAccount(username: string) {
		seeAccount = username;
		search = '';
		const page = await listItems(username, PAGE, 0);
		items = page;
		hasMore = page.length === PAGE;
		await tick();
	}

	async function loadMore() {
		if (loadingMore || !hasMore || !seeAccount) return;
		loadingMore = true;
		try {
			const page = await listItems(seeAccount, PAGE, items.length);
			const seen = new Set(items.map((i) => i.id));
			items = [...items, ...page.filter((p) => !seen.has(p.id))];
			hasMore = page.length === PAGE;
		} finally {
			loadingMore = false;
		}
	}

	// Infinite scroll sentinel.
	$effect(() => {
		if (!sentinel) return;
		const obs = new IntersectionObserver((entries) => {
			if (entries[0]?.isIntersecting) void loadMore();
		});
		obs.observe(sentinel);
		return () => obs.disconnect();
	});

	function isPreviewable(it: OpenedDrop): boolean {
		const t = it.meta?.type ?? '';
		return t.startsWith('image/') || t.startsWith('video/');
	}

	function loadOne(it: OpenedDrop): () => Promise<Blob> {
		return () => {
			if (!it.meta) throw new Error('cannot open (not addressed to you)');
			return downloadAndDecrypt(it, it.meta);
		};
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
		items = items.filter((x) => x.id !== it.id);
		senders = await listSenders();
	}

	function fmtSize(n: number): string {
		if (n < 1024) return `${n} B`;
		if (n < 1024 * 1024) return `${(n / 1024).toFixed(1)} KB`;
		return `${(n / 1024 / 1024).toFixed(1)} MB`;
	}
	function when(ts: number): string {
		return new Date(ts * 1000).toLocaleString();
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
	<div class="dropbox">
		<header class="toolbar">
			<nav class="tabs" aria-label="Dropbox views">
				<button class="tab" class:active={tab === 'drop'} onclick={() => (tab = 'drop')}>
					<Icon name="upload" size={16} /> <span>Drop</span>
				</button>
				<button class="tab" class:active={tab === 'see'} onclick={() => (tab = 'see')}>
					<Icon name="inbox" size={16} /> <span>See</span>
				</button>
			</nav>
		</header>

		{#if error}<div class="error">{error}</div>{/if}

		{#if tab === 'drop'}
			<Surface>
				<Stack gap={3}>
					<Text role="muted">Pick an account, then choose or drag files. They're encrypted so only that account can open them.</Text>
					<AccountPicker
						accounts={recipients.map((r) => ({ username: r.username, role: r.role, disabled: !r.has_key }))}
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
				</Stack>
			</Surface>
		{:else}
			<!-- See tab: account pill bar + paginated media -->
			<div class="pills" role="tablist" aria-label="Senders">
				{#each senders as s (s.from)}
					<button class="pill" class:on={seeAccount === s.from} role="tab" aria-selected={seeAccount === s.from} onclick={() => openAccount(s.from)}>
						<span class="dot">{(s.from[0] ?? '?').toUpperCase()}</span>
						{s.from}
						<span class="count">{s.count}</span>
					</button>
				{/each}
				{#if senders.length === 0}
					<Text role="muted">Nobody has dropped anything to you yet.</Text>
				{/if}
			</div>

			{#if seeAccount}
				<div class="search-row">
					<Field type="text" placeholder="Search file names…" bind:value={search} />
				</div>
				{#if shown.length === 0}
					<Surface><Text role="muted">{search ? 'No matches.' : 'Nothing from this account.'}</Text></Surface>
				{:else}
					<div class="grid">
						{#each shown as it (it.id)}
							<Surface level={2}>
								<Stack gap={2}>
									<div class="head">
										<Stack gap={1}>
											<Text role="label">{it.meta?.name ?? '(locked)'}</Text>
											<Text role="muted">{when(it.created)} · {fmtSize(it.size)}{it.source === 'chat' ? ' · chat' : ''}</Text>
										</Stack>
										<Icon name={it.source === 'chat' ? 'message-circle' : 'inbox'} size={16} />
									</div>
									{#if it.meta && isPreviewable(it)}
										<MediaBubble items={[{ hash: it.hash, name: it.meta.name, type: it.meta.type }]} load={loadOne(it)} compact />
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
					{#if hasMore}<div bind:this={sentinel} class="sentinel">{#if loadingMore}<Spinner />{/if}</div>{/if}
				{/if}
			{:else if senders.length}
				<Surface><Text role="muted">Pick an account above to see what they sent you.</Text></Surface>
			{/if}
		{/if}
	</div>
{/if}

<style>
	.dropbox {
		display: flex;
		flex-direction: column;
		gap: var(--space-4);
	}
	.toolbar {
		display: flex;
		align-items: center;
		justify-content: space-between;
		gap: var(--space-3);
		flex-wrap: wrap;
		padding-bottom: var(--space-2);
		border-bottom: var(--border-width) solid var(--border-color);
	}
	.tabs {
		display: flex;
		gap: var(--space-1);
		padding: var(--space-1);
		background: color-mix(in srgb, var(--surface-2) 40%, transparent);
		border: var(--border-width) solid var(--border-color);
		border-radius: var(--radius-lg);
	}
	.tab {
		display: inline-flex;
		align-items: center;
		gap: var(--space-2);
		font: inherit;
		font-weight: var(--font-weight-bold);
		color: var(--muted);
		background: transparent;
		border: var(--border-width) solid transparent;
		border-radius: var(--radius-md);
		padding: var(--space-2) var(--space-3);
		cursor: pointer;
	}
	.tab:hover {
		color: var(--fg);
	}
	.tab.active {
		color: var(--accent-fg);
		background: var(--accent);
		border-color: var(--border-color);
		box-shadow: var(--shadow-sm);
	}
	.error {
		color: var(--danger);
		border: var(--border-width) solid var(--danger);
		border-radius: var(--radius-md);
		padding: var(--space-2) var(--space-3);
		background: color-mix(in srgb, var(--danger) 10%, transparent);
	}
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
	.pills {
		display: flex;
		gap: var(--space-2);
		overflow-x: auto;
		padding-bottom: var(--space-2);
	}
	.pill {
		display: inline-flex;
		align-items: center;
		gap: var(--space-2);
		flex: none;
		padding: var(--space-1) var(--space-3) var(--space-1) var(--space-1);
		border-radius: var(--radius-pill, 999px);
		border: var(--border-width) solid var(--border-color);
		background: color-mix(in srgb, var(--surface-2) 50%, transparent);
		color: var(--fg);
		cursor: pointer;
		font-weight: var(--font-weight-bold);
		white-space: nowrap;
	}
	.pill.on {
		background: var(--accent);
		color: var(--accent-fg);
	}
	.pill .dot {
		width: 1.7rem;
		height: 1.7rem;
		display: grid;
		place-items: center;
		border-radius: 50%;
		background: color-mix(in srgb, var(--fg) 14%, transparent);
		font-size: 0.85rem;
	}
	.pill .count {
		font-size: 0.72rem;
		padding: 0 var(--space-2);
		border-radius: var(--radius-pill, 999px);
		background: color-mix(in srgb, var(--fg) 16%, transparent);
	}
	.search-row {
		max-width: 420px;
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
	.sentinel {
		display: flex;
		justify-content: center;
		padding: var(--space-4);
	}
</style>

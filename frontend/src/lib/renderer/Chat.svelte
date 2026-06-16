<script lang="ts">
	// Chat UI — pick a contact from a horizontal pill bar and exchange E2E messages
	// + media. Text is sealed to the recipient's public key (and your own copy);
	// media is encrypted and delivered through the dropbox, so it also lands in each
	// party's drop box. Multiple images in one message render as a clustered,
	// swipeable carousel (MediaBubble).
	//
	// A topbar carries the title + a message search (client-side, over decrypted
	// text). Media decrypts through the app-scoped mediaCache, so sending a new
	// message no longer re-decrypts existing images, and the cache is freed when you
	// leave the app. Token-only styling.
	import { onMount, onDestroy, tick } from 'svelte';
	import { Surface, Stack, Text, Button, Icon, Spinner, ChatBubble, MediaBubble, Field } from '$lib/components';
	import { auth } from '$lib/auth.svelte';
	import { connection } from '$lib/connection.svelte';
	import { fetchDirectory, type DirectoryEntry } from '$lib/crypto/identity';
	import {
		loadConversation,
		loadThreads,
		sendMessage,
		loadMedia,
		type OpenedMessage,
		type OpenedThread,
		type MediaRef
	} from '$lib/crypto/chat';
	import { clearMediaCache } from '$lib/crypto/mediaCache';

	let locked = $derived(auth.masterKey === null);
	let ready = $state(false);
	let error = $state<string | null>(null);

	let directory = $state<DirectoryEntry[]>([]);
	let others = $derived(directory.filter((d) => d.username !== auth.username));
	let threads = $state<OpenedThread[]>([]);

	let active = $state<string | null>(null);
	let activeKey = $derived(directory.find((d) => d.username === active)?.public_key ?? null);
	let messages = $state<OpenedMessage[]>([]);

	let searching = $state(false);
	let search = $state('');
	let shownMessages = $derived(
		search.trim()
			? messages.filter((m) => (m.payload?.text ?? '').toLowerCase().includes(search.trim().toLowerCase()))
			: messages
	);

	let draft = $state('');
	let pendingFiles = $state<File[]>([]);
	let sending = $state(false);
	let sendPct = $state<number | null>(null);
	let fileInput = $state<HTMLInputElement>();
	let scrollEl = $state<HTMLDivElement>();

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
			threads = await loadThreads();
			ready = true;
			unsub = connection.onEvent((topic, payload) => {
				const p = payload as { from?: string; to?: string } | null;
				if (topic === 'chat.message') {
					if (active && (p?.from === active || p?.to === active)) openConversation(active);
					loadThreads().then((t) => (threads = t));
				}
			});
		} catch (e) {
			error = e instanceof Error ? e.message : 'Failed to load chat.';
		}
	}

	onDestroy(() => {
		unsub?.();
		clearMediaCache();
	});

	async function openConversation(peer: string) {
		active = peer;
		search = '';
		searching = false;
		messages = await loadConversation(peer);
		await scrollToBottom();
	}

	async function scrollToBottom() {
		await tick();
		if (scrollEl) scrollEl.scrollTop = scrollEl.scrollHeight;
	}

	function addFiles(files: FileList | File[]) {
		pendingFiles = [...pendingFiles, ...Array.from(files)];
	}
	function removePending(i: number) {
		pendingFiles = pendingFiles.filter((_, j) => j !== i);
	}

	async function send() {
		if (!active || !activeKey) return;
		if (!draft.trim() && pendingFiles.length === 0) return;
		sending = true;
		error = null;
		const text = draft;
		const files = pendingFiles;
		draft = '';
		pendingFiles = [];
		try {
			const msg = await sendMessage(active, activeKey, text, files, (f) => (sendPct = f));
			messages = [...messages, msg];
			await scrollToBottom();
			threads = await loadThreads();
		} catch (e) {
			error = e instanceof Error ? e.message : 'Send failed.';
			draft = text;
			pendingFiles = files;
		} finally {
			sending = false;
			sendPct = null;
		}
	}

	function mediaItems(refs: MediaRef[]) {
		return refs.map((r) => ({ hash: r.hash, name: r.name, type: r.type }));
	}
	function mediaLoader(refs: MediaRef[]) {
		// Match by hash so the loader is correct regardless of carousel order.
		return (item: { hash: string }) => {
			const ref = refs.find((r) => r.hash === item.hash)!;
			return loadMedia(ref);
		};
	}

	function onComposerKey(e: KeyboardEvent) {
		if (e.key === 'Enter' && !e.shiftKey) {
			e.preventDefault();
			send();
		}
	}

	function initial(name: string): string {
		return (name.trim()[0] ?? '?').toUpperCase();
	}
	function previewOf(username: string): string {
		return threads.find((t) => t.peer === username)?.preview ?? '';
	}
</script>

{#if locked}
	<Surface>
		<Stack gap={2} align="center">
			<Icon name="lock" size={28} />
			<Text role="muted">Unlock your vault to use chat.</Text>
		</Stack>
	</Surface>
{:else if error && !ready}
	<Surface><Text role="muted">{error}</Text></Surface>
{:else if !ready}
	<Surface><Stack align="center"><Spinner /></Stack></Surface>
{:else}
	<div class="chat">
		<header class="toolbar">
			<Text role="heading">{active ? active : 'Chat'}</Text>
			<div class="toolbar-actions">
				{#if active}
					<Button size="sm" variant={searching ? 'accent' : 'neutral'} onclick={() => (searching = !searching)}>
						<Icon name="search" size={15} />
					</Button>
				{/if}
			</div>
		</header>

		<!-- Horizontal contact pill bar -->
		<div class="pills" role="tablist" aria-label="Contacts">
			{#each others as o (o.username)}
				<button class="pill" class:on={active === o.username} role="tab" aria-selected={active === o.username} onclick={() => openConversation(o.username)} title={previewOf(o.username)}>
					<span class="dot">{initial(o.username)}</span>
					{o.username}
				</button>
			{/each}
			{#if others.length === 0}
				<Text role="muted">No other accounts to chat with yet.</Text>
			{/if}
		</div>

		{#if searching && active}
			<div class="search-row">
				<Field type="text" placeholder="Search this conversation…" bind:value={search} />
			</div>
		{/if}

		{#if error}<div class="error">{error}</div>{/if}

		<Surface>
			{#if !active}
				<Stack gap={2} align="center">
					<Icon name="message-circle" size={28} />
					<Text role="muted">Pick a contact above to start chatting.</Text>
				</Stack>
			{:else}
				<div class="convo">
					<div class="messages" bind:this={scrollEl}>
						{#if shownMessages.length === 0}
							<Text role="muted">{search ? 'No matching messages.' : 'No messages yet — say hello.'}</Text>
						{/if}
						{#each shownMessages as m (m.id)}
							<ChatBubble mine={m.mine} text={m.payload?.text ?? ''} time={m.created}>
								{#snippet media()}
									{#if m.payload?.media?.length}
										<MediaBubble items={mediaItems(m.payload.media)} load={mediaLoader(m.payload.media)} compact />
									{/if}
								{/snippet}
							</ChatBubble>
						{/each}
					</div>

					<div class="composer">
						{#if pendingFiles.length}
							<div class="attachments">
								{#each pendingFiles as f, i (i)}
									<span class="att">
										<Icon name="image" size={13} />
										{f.name}
										<button aria-label="Remove" onclick={() => removePending(i)}>
											<Icon name="x" size={12} />
										</button>
									</span>
								{/each}
							</div>
						{/if}
						{#if sending}
							<div class="sending">
								<Spinner />
								<Text role="muted">Sending… {sendPct != null ? Math.round(sendPct * 100) + '%' : ''}</Text>
							</div>
						{/if}
						<div class="bar">
							<button class="attach" aria-label="Attach images" onclick={() => fileInput?.click()}>
								<Icon name="paperclip" size={18} />
							</button>
							<input
								bind:this={fileInput}
								type="file"
								accept="image/*,video/*"
								multiple
								hidden
								onchange={(e) => {
									const t = e.currentTarget as HTMLInputElement;
									if (t.files) addFiles(t.files);
									t.value = '';
								}}
							/>
							<textarea class="input" placeholder="Message…" rows="1" bind:value={draft} onkeydown={onComposerKey}></textarea>
							<Button onclick={send} disabled={sending || (!draft.trim() && !pendingFiles.length)}>
								<Icon name="send" size={16} />
							</Button>
						</div>
					</div>
				</div>
			{/if}
		</Surface>
	</div>
{/if}

<style>
	.chat {
		display: flex;
		flex-direction: column;
		gap: var(--space-3);
		min-height: 60vh;
	}
	.toolbar {
		display: flex;
		align-items: center;
		justify-content: space-between;
		gap: var(--space-3);
		padding-bottom: var(--space-2);
		border-bottom: var(--border-width) solid var(--border-color);
	}
	.toolbar-actions {
		display: flex;
		gap: var(--space-2);
	}
	.pills {
		display: flex;
		gap: var(--space-2);
		overflow-x: auto;
		padding-bottom: var(--space-1);
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
	.search-row {
		max-width: 420px;
	}
	.error {
		color: var(--danger);
		border: var(--border-width) solid var(--danger);
		border-radius: var(--radius-md);
		padding: var(--space-2) var(--space-3);
		background: color-mix(in srgb, var(--danger) 10%, transparent);
	}
	.convo {
		display: flex;
		flex-direction: column;
		height: 68vh;
		min-height: 420px;
	}
	.messages {
		flex: 1;
		overflow-y: auto;
		display: flex;
		flex-direction: column;
		gap: var(--space-2);
		padding-right: var(--space-2);
	}
	.composer {
		display: flex;
		flex-direction: column;
		gap: var(--space-2);
		padding-top: var(--space-3);
	}
	.attachments {
		display: flex;
		flex-wrap: wrap;
		gap: var(--space-2);
	}
	.att {
		display: inline-flex;
		align-items: center;
		gap: var(--space-1);
		padding: var(--space-1) var(--space-2);
		border-radius: var(--radius-sm);
		background: color-mix(in srgb, var(--surface-2) 70%, transparent);
		font-size: 0.8rem;
	}
	.att button {
		display: inline-flex;
		background: transparent;
		border: none;
		color: var(--muted);
		cursor: pointer;
		padding: 0;
	}
	.sending {
		display: flex;
		align-items: center;
		gap: var(--space-2);
	}
	.bar {
		display: flex;
		align-items: flex-end;
		gap: var(--space-2);
	}
	.attach {
		display: inline-flex;
		align-items: center;
		justify-content: center;
		width: 2.4rem;
		height: 2.4rem;
		flex: none;
		border-radius: var(--radius-md);
		border: var(--border-width) solid var(--border-color);
		background: transparent;
		color: var(--fg);
		cursor: pointer;
	}
	.input {
		flex: 1;
		resize: none;
		max-height: 120px;
		padding: var(--space-2) var(--space-3);
		border-radius: var(--radius-md);
		border: var(--border-width) solid var(--border-color);
		background: color-mix(in srgb, var(--surface-2) calc(var(--surface-alpha) * 100%), transparent);
		color: var(--fg);
		font: inherit;
		line-height: 1.4;
	}
</style>

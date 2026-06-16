<script lang="ts">
	import { getContext, onMount } from 'svelte';
	import { attAction, attGet, attGetQuery } from '$lib/api';
	import { connection } from '$lib/connection.svelte';
	import { Accordion, AccordionItem, Badge, Button, Field, Icon, Text } from '$lib/components';
	import type { RenderContext } from './context.svelte';

	interface MailAccount {
		id: number;
		email: string;
		configured: boolean;
		start_after: number;
		poll_seconds: number;
		notify: boolean;
		active: boolean;
		last_uid: number;
		last_poll: number | null;
		last_ok: number | null;
		last_error: string | null;
	}

	interface MailMessage {
		id: number;
		account_id: number;
		account_email: string;
		uid: number;
		message_id: string;
		subject: string;
		sender_name: string;
		sender_email: string;
		sent_at: number;
		labels: string[];
		snippet: string;
		body: string;
		fetched: number;
	}

	type Tab = 'inbox' | 'search' | 'accounts';

	const ctx = getContext<RenderContext>('render');

	let tab = $state<Tab>('inbox');

	let accounts = $state<MailAccount[]>([]);
	let messages = $state<MailMessage[]>([]);
	let expandedId = $state<number | null>(null);
	let loading = $state(false);

	// Infinite scroll: fetch the inbox 25 at a time, appending the next page as the
	// user scrolls to the bottom. `hasMore` is false once a page comes back short.
	const PAGE_SIZE = 25;
	let loadingMore = $state(false);
	let hasMore = $state(true);
	let accountBusy = $state(false);
	let fetchBusy = $state(false);
	let togglingNotify = $state(false);
	let error = $state<string | null>(null);

	let newEmail = $state('');
	let newPassword = $state('');
	let notifyNew = $state(false);

	let query = $state('');
	let sender = $state('');
	let accountFilter = $state('all');

	// A unified mailbox: the inbox tab shows everything, the search tab adds
	// filters. Both read from the same loaded list so we don't double-fetch.
	const hasFilters = $derived(
		query.trim() !== '' || sender.trim() !== '' || accountFilter !== 'all'
	);
	const notifyOn = $derived(accounts.length > 0 && accounts.every((a) => a.notify));

	onMount(() => {
		void loadAll();
		const off = connection.onEvent((topic) => {
			if (topic.startsWith(`${ctx.attachmentId}.`) || topic.startsWith('mail.')) void loadAll({ quiet: true });
		});
		return () => off();
	});

	async function loadAll(opts: { quiet?: boolean } = {}) {
		if (!opts.quiet) loading = true;
		error = null;
		try {
			// A background refresh (new mail arrived / reconnect) keeps the user's scroll
			// depth by re-pulling as many messages as are currently loaded; a foreground
			// load starts fresh at the first page.
			await Promise.all([loadAccounts(), loadMessages({ keepDepth: opts.quiet })]);
		} catch (e) {
			error = e instanceof Error ? e.message : String(e);
		} finally {
			loading = false;
		}
	}

	async function loadAccounts() {
		accounts = await attGet<MailAccount[]>(ctx.attachmentId, 'accounts');
	}

	// Build the query for one page. The active filters (search keyword/sender/account)
	// are shared by the inbox and search tabs.
	function pageParams(offset: number, limit: number): Record<string, string> {
		const params: Record<string, string> = {
			limit: String(limit),
			offset: String(offset)
		};
		if (query.trim()) params.q = query.trim();
		if (sender.trim()) params.sender = sender.trim();
		if (accountFilter !== 'all') params.account_id = accountFilter;
		return params;
	}

	// Replace the list from the top. By default that's the first page (25); a
	// depth-preserving refresh re-pulls however many are already loaded.
	async function loadMessages(opts: { keepDepth?: boolean } = {}) {
		// Backend caps a single page at 500; a deeper refresh just trims to that.
		const limit = opts.keepDepth ? Math.min(500, Math.max(PAGE_SIZE, messages.length)) : PAGE_SIZE;
		const page = await attGetQuery<MailMessage[]>(
			ctx.attachmentId,
			'messages',
			pageParams(0, limit)
		);
		messages = page;
		hasMore = page.length === limit;
		if (expandedId && !messages.some((m) => m.id === expandedId)) expandedId = null;
	}

	// Next page: append. Guarded so concurrent scroll events don't double-fetch.
	async function loadMore() {
		if (loadingMore || !hasMore || loading) return;
		loadingMore = true;
		try {
			const page = await attGetQuery<MailMessage[]>(
				ctx.attachmentId,
				'messages',
				pageParams(messages.length, PAGE_SIZE)
			);
			// Drop any ids we already hold (a new mail arriving up top can shift the
			// offset window by one); keeps the appended page free of duplicates.
			const seen = new Set(messages.map((m) => m.id));
			const fresh = page.filter((m) => !seen.has(m.id));
			messages = [...messages, ...fresh];
			hasMore = page.length === PAGE_SIZE;
		} catch (e) {
			error = e instanceof Error ? e.message : String(e);
		} finally {
			loadingMore = false;
		}
	}

	async function addAccount(e: SubmitEvent) {
		e.preventDefault();
		accountBusy = true;
		error = null;
		try {
			await attAction(ctx.attachmentId, 'POST', 'accounts', {
				email: newEmail,
				app_password: newPassword,
				poll_seconds: 60,
				notify: notifyNew
			});
			newEmail = '';
			newPassword = '';
			notifyNew = false;
			await loadAll();
		} catch (e) {
			error = e instanceof Error ? e.message : String(e);
		} finally {
			accountBusy = false;
		}
	}

	async function patchAccount(id: number, body: Record<string, unknown>) {
		await attAction(ctx.attachmentId, 'PATCH', `accounts/${id}`, body);
	}

	async function toggleActive(account: MailAccount) {
		accountBusy = true;
		error = null;
		try {
			await patchAccount(account.id, { active: !account.active });
			await loadAccounts();
		} catch (e) {
			error = e instanceof Error ? e.message : String(e);
		} finally {
			accountBusy = false;
		}
	}

	async function toggleNotify(account: MailAccount) {
		accountBusy = true;
		error = null;
		try {
			await patchAccount(account.id, { notify: !account.notify });
			await loadAccounts();
		} catch (e) {
			error = e instanceof Error ? e.message : String(e);
		} finally {
			accountBusy = false;
		}
	}

	// Header toggle: flip notifications for every account at once. This is the
	// "off switch" — once mail notifications are noisy, one tap silences them all.
	async function toggleNotifyAll() {
		if (accounts.length === 0) return;
		togglingNotify = true;
		error = null;
		const next = !notifyOn;
		try {
			await Promise.all(
				accounts
					.filter((a) => a.notify !== next)
					.map((a) => patchAccount(a.id, { notify: next }))
			);
			await loadAccounts();
		} catch (e) {
			error = e instanceof Error ? e.message : String(e);
		} finally {
			togglingNotify = false;
		}
	}

	async function fetchAll() {
		fetchBusy = true;
		error = null;
		try {
			await attAction(ctx.attachmentId, 'POST', 'fetch');
			await loadAll({ quiet: true });
		} catch (e) {
			error = e instanceof Error ? e.message : String(e);
		} finally {
			fetchBusy = false;
		}
	}

	async function fetchAccount(id: number) {
		fetchBusy = true;
		error = null;
		try {
			await attAction(ctx.attachmentId, 'POST', `accounts/${id}/fetch`);
			await loadAll({ quiet: true });
		} catch (e) {
			error = e instanceof Error ? e.message : String(e);
		} finally {
			fetchBusy = false;
		}
	}

	async function deleteAccount(id: number) {
		accountBusy = true;
		error = null;
		try {
			await attAction(ctx.attachmentId, 'DELETE', `accounts/${id}`);
			if (accountFilter === String(id)) accountFilter = 'all';
			await loadAll();
		} catch (e) {
			error = e instanceof Error ? e.message : String(e);
		} finally {
			accountBusy = false;
		}
	}

	function clearSearch() {
		query = '';
		sender = '';
		accountFilter = 'all';
		void loadMessages();
	}

	function toggleExpand(id: number) {
		expandedId = expandedId === id ? null : id;
	}

	function when(ts: number | null): string {
		if (!ts) return 'Never';
		return new Date(ts * 1000).toLocaleString();
	}

	// --- day grouping (inbox) ---
	// Which day is selected in the inbox day-bar: a `YYYY-MM-DD` key, or 'all'.
	let selectedDay = $state('all');

	// Local-day key for a message timestamp (so days split at the user's midnight).
	function dayKey(ts: number | null): string {
		if (!ts) return 'unknown';
		const d = new Date(ts * 1000);
		return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, '0')}-${String(d.getDate()).padStart(2, '0')}`;
	}
	function dayKeyOf(d: Date): string {
		return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, '0')}-${String(d.getDate()).padStart(2, '0')}`;
	}
	// Short, friendly label for a day chip: Today / Yesterday / "Mon 12 Jun".
	function dayLabel(key: string): string {
		if (key === 'unknown') return 'Undated';
		const today = dayKeyOf(new Date());
		const yesterday = dayKeyOf(new Date(Date.now() - 86400000));
		if (key === today) return 'Today';
		if (key === yesterday) return 'Yesterday';
		const [y, m, d] = key.split('-').map(Number);
		const dt = new Date(y, m - 1, d);
		return dt.toLocaleDateString(undefined, { weekday: 'short', day: 'numeric', month: 'short' });
	}

	// Days present in the loaded mail, newest first, each with its message count.
	const days = $derived.by(() => {
		const counts = new Map<string, number>();
		for (const m of messages) {
			const k = dayKey(m.sent_at);
			counts.set(k, (counts.get(k) ?? 0) + 1);
		}
		return [...counts.entries()]
			.sort((a, b) => (a[0] < b[0] ? 1 : a[0] > b[0] ? -1 : 0)) // newest day first
			.map(([key, count]) => ({ key, count, label: dayLabel(key) }));
	});

	// Messages shown in the list. The day filter applies only on the inbox tab; the
	// search tab has its own filters and ignores the selected day.
	const visibleMessages = $derived(
		tab !== 'inbox' || selectedDay === 'all'
			? messages
			: messages.filter((m) => dayKey(m.sent_at) === selectedDay)
	);

	// If the selected day disappears (e.g. after a reload/filter), fall back to All.
	$effect(() => {
		if (selectedDay !== 'all' && !days.some((d) => d.key === selectedDay)) selectedDay = 'all';
	});

	// Infinite scroll: watch a sentinel at the end of the list and pull the next page
	// when it nears the viewport. `rootMargin` pre-loads slightly before the bottom so
	// scrolling feels seamless.
	let sentinel = $state<HTMLElement | undefined>();
	$effect(() => {
		const el = sentinel;
		if (!el) return;
		const io = new IntersectionObserver(
			(entries) => {
				if (entries[0]?.isIntersecting) void loadMore();
			},
			{ rootMargin: '400px 0px' }
		);
		io.observe(el);
		return () => io.disconnect();
	});

	function senderLabel(message: MailMessage): string {
		return message.sender_name
			? `${message.sender_name} <${message.sender_email}>`
			: message.sender_email;
	}

	const tabs: { id: Tab; label: string; icon: string }[] = [
		{ id: 'inbox', label: 'Inbox', icon: 'mail' },
		{ id: 'search', label: 'Search', icon: 'search' },
		{ id: 'accounts', label: 'Accounts', icon: 'user' }
	];
</script>

<div class="mail-client">
	<header class="toolbar">
		<nav class="tabs" aria-label="Mail views">
			{#each tabs as t (t.id)}
				<button class="tab" class:active={tab === t.id} onclick={() => (tab = t.id)}>
					<Icon name={t.icon} size={16} />
					<span>{t.label}</span>
					{#if t.id === 'accounts' && accounts.length > 0}
						<span class="count">{accounts.length}</span>
					{/if}
				</button>
			{/each}
		</nav>

		<div class="toolbar-actions">
			<Button
				variant={notifyOn ? 'success' : 'neutral'}
				size="sm"
				disabled={togglingNotify || accounts.length === 0}
				onclick={toggleNotifyAll}
				aria-pressed={notifyOn}
				title={notifyOn ? 'Notifications on — tap to silence' : 'Notifications off — tap to enable'}
			>
				<Icon name={notifyOn ? 'bell' : 'bell-off'} size={15} />
				{notifyOn ? 'Notify on' : 'Notify off'}
			</Button>
			<Button
				variant="neutral"
				size="sm"
				disabled={fetchBusy || accounts.length === 0}
				onclick={fetchAll}
			>
				<Icon name="refresh-cw" size={15} /> Fetch now
			</Button>
		</div>
	</header>

	{#if error}
		<div class="error">{error}</div>
	{/if}

	{#if tab === 'search'}
		<div class="search-bar">
			<Field type="text" label="Keyword" placeholder="Subject, sender, content" bind:value={query} />
			<Field type="text" label="Sender" placeholder="person@example.com" bind:value={sender} />
			<label class="select-wrap">
				<span>Account</span>
				<select bind:value={accountFilter}>
					<option value="all">All accounts</option>
					{#each accounts as account (account.id)}
						<option value={String(account.id)}>{account.email}</option>
					{/each}
				</select>
			</label>
			<div class="search-buttons">
				<Button variant="neutral" disabled={loading} onclick={() => loadMessages()}>
					<Icon name="search" size={16} /> Search
				</Button>
				{#if hasFilters}
					<Button variant="ghost" disabled={loading} onclick={clearSearch}>Clear</Button>
				{/if}
			</div>
		</div>
	{/if}

	{#if tab === 'accounts'}
		<section class="accounts-view">
			<form class="account-form" onsubmit={addAccount}>
				<Field type="email" label="Gmail address" placeholder="name@gmail.com" bind:value={newEmail} />
				<Field
					type="password"
					label="App password"
					placeholder="16-character code"
					bind:value={newPassword}
				/>
				<Field type="checkbox" label="Notify on new mail" bind:value={notifyNew} />
				<Button type="submit" disabled={accountBusy || !newEmail || !newPassword}>
					<Icon name="mail-plus" size={16} /> Add account
				</Button>
			</form>

			{#if accounts.length === 0}
				<Text role="muted">No accounts configured. Add one above to start polling.</Text>
			{:else}
				<div class="accounts">
					{#each accounts as account (account.id)}
						<div class="account-card">
							<div class="account-head">
								<span class="account-email">{account.email}</span>
								<Badge variant={account.last_error ? 'danger' : account.active ? 'success' : 'neutral'}>
									{account.last_error ? 'Error' : account.active ? 'Polling' : 'Paused'}
								</Badge>
							</div>
							<div class="account-meta">Last fetch: {when(account.last_ok)}</div>
							{#if account.last_error}
								<div class="account-error">{account.last_error}</div>
							{/if}
							<div class="account-controls">
								<Button
									variant={account.active ? 'neutral' : 'success'}
									size="sm"
									disabled={accountBusy}
									onclick={() => toggleActive(account)}
								>
									<Icon name={account.active ? 'pause' : 'play'} size={14} />
									{account.active ? 'Pause' : 'Resume'}
								</Button>
								<Button
									variant={account.notify ? 'success' : 'neutral'}
									size="sm"
									disabled={accountBusy}
									onclick={() => toggleNotify(account)}
								>
									<Icon name={account.notify ? 'bell' : 'bell-off'} size={14} />
									{account.notify ? 'Notify' : 'Silent'}
								</Button>
								<Button
									variant="ghost"
									size="sm"
									disabled={fetchBusy}
									onclick={() => fetchAccount(account.id)}
								>
									<Icon name="refresh-cw" size={14} /> Fetch
								</Button>
								<Button
									variant="danger"
									size="sm"
									disabled={accountBusy}
									onclick={() => deleteAccount(account.id)}
								>
									<Icon name="trash" size={14} />
								</Button>
							</div>
						</div>
					{/each}
				</div>
			{/if}
		</section>
	{:else}
		<section class="message-list">
			{#if tab === 'inbox' && days.length > 0}
				<!-- Day bar: filter the inbox to a single day. Scrolls horizontally so it
				     stays usable on narrow screens. -->
				<nav class="day-bar" aria-label="Filter by day">
					<button
						class="day-chip"
						class:active={selectedDay === 'all'}
						onclick={() => (selectedDay = 'all')}
					>
						All <span class="day-count">{messages.length}</span>
					</button>
					{#each days as d (d.key)}
						<button
							class="day-chip"
							class:active={selectedDay === d.key}
							onclick={() => (selectedDay = d.key)}
						>
							{d.label} <span class="day-count">{d.count}</span>
						</button>
					{/each}
				</nav>
			{/if}

			{#if loading && messages.length === 0}
				<Text role="muted">Loading…</Text>
			{:else if messages.length === 0}
				<Text role="muted">
					{tab === 'search' && hasFilters ? 'No mail matches your filters.' : 'No mail captured yet.'}
				</Text>
			{:else if visibleMessages.length === 0}
				<Text role="muted">No mail on {dayLabel(selectedDay)}.</Text>
			{:else}
				<!-- One accordion: every mail is a divider-separated section; opening one
				     closes the others (single `expandedId`). -->
				<Accordion>
					{#each visibleMessages as message (message.id)}
						{@const open = expandedId === message.id}
						{@const body = message.body || message.snippet}
						<AccordionItem {open} ontoggle={() => toggleExpand(message.id)} bodyText={body}>
							{#snippet header()}
								<div class="message-row">
									<Icon name={open ? 'chevron-down' : 'chevron-right'} size={16} />
									<div class="message-body-preview">
										<div class="message-top">
											<span class="sender">{senderLabel(message)}</span>
											<span class="date">{when(message.sent_at)}</span>
										</div>
										<div class="subject">{message.subject || '(no subject)'}</div>
										{#if !open}
											<div class="snippet">{message.snippet}</div>
										{/if}
										<div class="message-tags">
											<Badge variant="info">{message.account_email}</Badge>
											{#each message.labels.slice(0, 3) as label (label)}
												<Badge>{label}</Badge>
											{/each}
										</div>
									</div>
								</div>
							{/snippet}
							<pre class="message-text" data-ac-text>{body}</pre>
						</AccordionItem>
					{/each}
				</Accordion>

				<!-- Infinite-scroll trigger + status. The sentinel is observed while more
				     pages remain; once exhausted we show a quiet end-of-list note. -->
				{#if hasMore}
					<div class="load-more" bind:this={sentinel}>
						<Text role="muted">{loadingMore ? 'Loading more…' : 'Scroll for more'}</Text>
					</div>
				{:else if messages.length > PAGE_SIZE}
					<div class="load-more">
						<Text role="muted">That's everything.</Text>
					</div>
				{/if}
			{/if}
		</section>
	{/if}
</div>

<style>
	.mail-client {
		display: flex;
		flex-direction: column;
		gap: var(--space-3);
		min-height: 0;
	}

	/* --- toolbar / tabs --- */
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
		transition:
			background var(--motion-fast) var(--motion-ease),
			color var(--motion-fast) var(--motion-ease);
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
	.count {
		font-size: 0.72rem;
		padding: 0 var(--space-2);
		border-radius: var(--radius-pill, 999px);
		background: color-mix(in srgb, var(--fg) 16%, transparent);
	}
	.tab.active .count {
		background: color-mix(in srgb, var(--accent-fg) 28%, transparent);
	}
	.toolbar-actions {
		display: flex;
		align-items: center;
		gap: var(--space-2);
	}

	.error {
		color: var(--danger);
		border: var(--border-width) solid var(--danger);
		border-radius: var(--radius-md);
		padding: var(--space-2) var(--space-3);
		background: color-mix(in srgb, var(--danger) 10%, transparent);
	}

	/* --- search bar --- */
	.search-bar {
		display: grid;
		grid-template-columns: minmax(160px, 1.4fr) minmax(160px, 1fr) minmax(150px, 0.8fr) auto;
		gap: var(--space-3);
		align-items: end;
	}
	.search-buttons {
		display: flex;
		gap: var(--space-2);
	}
	.select-wrap {
		display: flex;
		flex-direction: column;
		gap: var(--space-1);
	}
	.select-wrap span {
		font-size: 0.85rem;
		font-weight: var(--font-weight-bold);
		color: var(--muted);
	}
	.select-wrap select {
		font: inherit;
		color: var(--fg);
		background: color-mix(in srgb, var(--surface-2) calc(var(--surface-alpha) * 100%), transparent);
		border: var(--border-width) solid var(--border-color);
		border-radius: var(--radius-md);
		padding: var(--space-2) var(--space-3);
		box-shadow: var(--shadow-sm);
		min-height: 2.45rem;
	}

	/* --- accounts view --- */
	.accounts-view {
		display: flex;
		flex-direction: column;
		gap: var(--space-4);
	}
	.account-form {
		display: grid;
		grid-template-columns: minmax(200px, 1fr) minmax(200px, 1fr) auto auto;
		gap: var(--space-3);
		align-items: end;
		padding: var(--space-3);
		border: var(--border-width) solid var(--border-color);
		border-radius: var(--radius-lg);
		background: color-mix(in srgb, var(--surface) 56%, transparent);
		box-shadow: var(--shadow-sm);
	}
	.account-form :global(.field.inline) {
		align-self: center;
	}
	.accounts {
		display: grid;
		grid-template-columns: repeat(auto-fill, minmax(320px, 1fr));
		gap: var(--space-3);
	}
	.account-card {
		display: flex;
		flex-direction: column;
		gap: var(--space-2);
		padding: var(--space-3);
		border: var(--border-width) solid var(--border-color);
		border-radius: var(--radius-lg);
		background: color-mix(in srgb, var(--surface) calc(var(--surface-alpha) * 100%), transparent);
		box-shadow: var(--shadow-sm);
	}
	.account-head {
		display: flex;
		align-items: center;
		justify-content: space-between;
		gap: var(--space-2);
		font-weight: var(--font-weight-bold);
	}
	.account-email {
		overflow: hidden;
		text-overflow: ellipsis;
		white-space: nowrap;
	}
	.account-controls {
		display: flex;
		flex-wrap: wrap;
		gap: var(--space-2);
		margin-top: var(--space-1);
	}
	.account-meta,
	.account-error {
		color: var(--muted);
		font-size: 0.82rem;
	}
	.account-error {
		color: var(--danger);
		overflow-wrap: anywhere;
	}

	/* --- message list (inbox + search results) --- */
	.message-list {
		display: flex;
		flex-direction: column;
		gap: var(--space-3);
	}

	.load-more {
		display: flex;
		justify-content: center;
		padding: var(--space-3);
	}

	/* --- day bar (inbox) --- */
	.day-bar {
		display: flex;
		gap: var(--space-2);
		overflow-x: auto;
		-webkit-overflow-scrolling: touch;
		padding-bottom: var(--space-1);
		scrollbar-width: thin;
	}
	.day-chip {
		display: inline-flex;
		align-items: center;
		gap: var(--space-2);
		flex: none;
		font: inherit;
		font-size: 0.85rem;
		font-weight: var(--font-weight-bold);
		color: var(--muted);
		background: color-mix(in srgb, var(--surface-2) 40%, transparent);
		border: var(--border-width) solid var(--border-color);
		border-radius: var(--radius-pill, 999px);
		padding: var(--space-1) var(--space-3);
		cursor: pointer;
		white-space: nowrap;
		transition:
			background var(--motion-fast) var(--motion-ease),
			color var(--motion-fast) var(--motion-ease),
			border-color var(--motion-fast) var(--motion-ease);
	}
	.day-chip:hover {
		color: var(--fg);
	}
	.day-chip.active {
		color: var(--accent-fg);
		background: var(--accent);
		border-color: var(--accent);
	}
	.day-count {
		font-size: 0.72rem;
		padding: 0 var(--space-2);
		border-radius: var(--radius-pill, 999px);
		background: color-mix(in srgb, var(--fg) 16%, transparent);
	}
	.day-chip.active .day-count {
		background: color-mix(in srgb, var(--accent-fg) 28%, transparent);
	}

	/* The list is one Accordion: its single bordered container and the per-row
	   dividers/open-state/header-hover come from the Accordion components. Here we
	   only style the header content. */
	.message-row {
		display: flex;
		align-items: flex-start;
		gap: var(--space-3);
		width: 100%;
		padding: var(--space-3) var(--space-4);
	}
	.message-row :global(svg) {
		margin-top: 0.15rem;
		flex: none;
		color: var(--muted);
	}
	.message-body-preview {
		display: flex;
		flex-direction: column;
		gap: var(--space-1);
		min-width: 0;
		flex: 1;
	}
	.message-top {
		display: flex;
		align-items: center;
		justify-content: space-between;
		gap: var(--space-2);
	}
	.sender {
		font-weight: var(--font-weight-bold);
		overflow: hidden;
		text-overflow: ellipsis;
		white-space: nowrap;
	}
	.date {
		flex: none;
		color: var(--muted);
		font-size: 0.82rem;
	}
	.subject {
		font-weight: var(--font-weight-bold);
		overflow: hidden;
		text-overflow: ellipsis;
		white-space: nowrap;
	}
	.snippet {
		color: var(--muted);
		font-size: 0.86rem;
		display: -webkit-box;
		line-clamp: 2;
		-webkit-line-clamp: 2;
		-webkit-box-orient: vertical;
		overflow: hidden;
		line-height: 1.35;
	}
	.message-tags {
		display: flex;
		flex-wrap: wrap;
		gap: var(--space-1);
		margin-top: var(--space-1);
	}
	/* The expanded body. This <pre> is the Accordion's measured text element
	   (data-ac-text): its padding/border/line-height are read once and fed to
	   pretext, so the open-height animation matches its real wrapped height. */
	.message-text {
		margin: 0;
		padding: var(--space-3) var(--space-4) var(--space-4)
			calc(var(--space-4) + var(--space-3) + 16px);
		border-top: var(--border-width) solid var(--border-color);
		white-space: pre-wrap;
		overflow-wrap: anywhere;
		font: inherit;
		line-height: 1.55;
		color: var(--fg);
	}

	@media (max-width: 760px) {
		.search-bar,
		.account-form {
			grid-template-columns: 1fr;
		}
		.toolbar {
			align-items: stretch;
		}
		/* Tabs scroll horizontally instead of wrapping into a tall block, and the
		   action buttons grow to fill the row so they're easy to tap. */
		.tabs {
			overflow-x: auto;
			-webkit-overflow-scrolling: touch;
		}
		.tab {
			flex: none;
		}
		.toolbar-actions {
			flex-wrap: wrap;
		}
		.toolbar-actions :global(.btn) {
			flex: 1;
		}
		/* Sender/date stack so neither truncates awkwardly on a narrow screen. */
		.message-top {
			flex-direction: column;
			align-items: flex-start;
			gap: 2px;
		}
		/* Tighten the body's deep left indent on small screens. */
		.message-text {
			padding-left: var(--space-4);
		}
	}
</style>

<script lang="ts">
	import { getContext, onMount } from 'svelte';
	import { attAction, attGet, attGetQuery } from '$lib/api';
	import { connection } from '$lib/connection.svelte';
	import { Badge, Button, Field, Icon, Stack, Surface, Text } from '$lib/components';
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

	const ctx = getContext<RenderContext>('render');

	let accounts = $state<MailAccount[]>([]);
	let messages = $state<MailMessage[]>([]);
	let selectedId = $state<number | null>(null);
	let loading = $state(false);
	let accountBusy = $state(false);
	let fetchBusy = $state(false);
	let error = $state<string | null>(null);

	let newEmail = $state('');
	let newPassword = $state('');
	let notifyNew = $state(false);
	let query = $state('');
	let sender = $state('');
	let accountFilter = $state('all');

	const selected = $derived(messages.find((m) => m.id === selectedId) ?? messages[0] ?? null);

	onMount(() => {
		void loadAll();
		const off = connection.onEvent((topic) => {
			if (topic.startsWith(`${ctx.attachmentId}.`) || topic.startsWith('mail.')) void loadAll();
		});
		const timer = setInterval(() => void loadAll({ quiet: true }), 60_000);
		return () => {
			off();
			clearInterval(timer);
		};
	});

	async function loadAll(opts: { quiet?: boolean } = {}) {
		if (!opts.quiet) loading = true;
		error = null;
		try {
			await Promise.all([loadAccounts(), loadMessages()]);
		} catch (e) {
			error = e instanceof Error ? e.message : String(e);
		} finally {
			loading = false;
		}
	}

	async function loadAccounts() {
		accounts = await attGet<MailAccount[]>(ctx.attachmentId, 'accounts');
	}

	async function loadMessages() {
		const params: Record<string, string> = { limit: '200' };
		if (query.trim()) params.q = query.trim();
		if (sender.trim()) params.sender = sender.trim();
		if (accountFilter !== 'all') params.account_id = accountFilter;
		messages = await attGetQuery<MailMessage[]>(ctx.attachmentId, 'messages', params);
		if (selectedId && !messages.some((m) => m.id === selectedId)) selectedId = null;
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

	async function fetchAll() {
		fetchBusy = true;
		error = null;
		try {
			await attAction(ctx.attachmentId, 'POST', 'fetch');
			await loadAll();
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
			await loadAll();
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

	function when(ts: number | null): string {
		if (!ts) return 'Never';
		return new Date(ts * 1000).toLocaleString();
	}

	function senderLabel(message: MailMessage): string {
		return message.sender_name
			? `${message.sender_name} <${message.sender_email}>`
			: message.sender_email;
	}
</script>

<div class="mail-client">
	{#if error}
		<div class="error">{error}</div>
	{/if}

	<div class="top-grid">
		<Surface level={2}>
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
		</Surface>

		<Surface level={2}>
			<Stack gap={2}>
				<div class="section-head">
					<Text role="label">Accounts</Text>
					<Button variant="neutral" size="sm" disabled={fetchBusy || accounts.length === 0} onclick={fetchAll}>
						<Icon name="refresh-cw" size={15} /> Fetch now
					</Button>
				</div>
				{#if accounts.length === 0}
					<Text role="muted">No accounts configured.</Text>
				{:else}
					<div class="accounts">
						{#each accounts as account (account.id)}
							<div class="account-row">
								<div class="account-main">
									<div class="account-title">
										<span>{account.email}</span>
										<Badge variant={account.last_error ? 'danger' : account.active ? 'success' : 'neutral'}>
											{account.last_error ? 'Error' : account.active ? 'Polling' : 'Paused'}
										</Badge>
									</div>
									<div class="account-meta">Last fetch: {when(account.last_ok)}</div>
									{#if account.last_error}
										<div class="account-error">{account.last_error}</div>
									{/if}
								</div>
								<div class="account-actions">
									<Button
										variant="ghost"
										size="sm"
										disabled={fetchBusy}
										onclick={() => fetchAccount(account.id)}
									>
										<Icon name="refresh-cw" size={14} />
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
			</Stack>
		</Surface>
	</div>

	<div class="mail-grid">
		<section class="inbox-panel">
			<div class="search-row">
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
				<Button variant="neutral" disabled={loading} onclick={() => loadMessages()}>
					<Icon name="search" size={16} /> Search
				</Button>
			</div>

			<div class="message-list">
				{#if loading && messages.length === 0}
					<Text role="muted">Loading…</Text>
				{:else if messages.length === 0}
					<Text role="muted">No mail captured yet.</Text>
				{:else}
					{#each messages as message (message.id)}
						<button
							class="message-row"
							class:selected={selected?.id === message.id}
							onclick={() => (selectedId = message.id)}
						>
							<div class="message-top">
								<span class="sender">{senderLabel(message)}</span>
								<span class="date">{when(message.sent_at)}</span>
							</div>
							<div class="subject">{message.subject || '(no subject)'}</div>
							<div class="snippet">{message.snippet}</div>
							<div class="message-tags">
								<Badge variant="info">{message.account_email}</Badge>
								{#each message.labels.slice(0, 3) as label (label)}
									<Badge>{label}</Badge>
								{/each}
							</div>
						</button>
					{/each}
				{/if}
			</div>
		</section>

		<aside class="detail-panel">
			{#if selected}
				<div class="detail-head">
					<div>
						<div class="detail-subject">{selected.subject || '(no subject)'}</div>
						<div class="detail-from">{senderLabel(selected)}</div>
					</div>
					<Badge variant="info">{selected.account_email}</Badge>
				</div>
				<div class="detail-meta">{when(selected.sent_at)}</div>
				<div class="detail-labels">
					{#each selected.labels as label (label)}
						<Badge>{label}</Badge>
					{/each}
				</div>
				<pre class="message-body">{selected.body || selected.snippet}</pre>
			{:else}
				<Text role="muted">Select a message.</Text>
			{/if}
		</aside>
	</div>
</div>

<style>
	.mail-client {
		display: flex;
		flex-direction: column;
		gap: var(--space-4);
	}
	.error {
		color: var(--danger);
		border: var(--border-width) solid var(--danger);
		border-radius: var(--radius-md);
		padding: var(--space-2) var(--space-3);
		background: color-mix(in srgb, var(--danger) 10%, transparent);
	}
	.top-grid {
		display: grid;
		grid-template-columns: minmax(280px, 0.9fr) minmax(320px, 1.1fr);
		gap: var(--space-3);
		align-items: stretch;
	}
	.account-form {
		display: grid;
		grid-template-columns: minmax(180px, 1fr) minmax(180px, 1fr);
		gap: var(--space-3);
		align-items: end;
	}
	.account-form :global(.field.inline) {
		align-self: center;
	}
	.section-head,
	.account-title,
	.message-top,
	.detail-head,
	.account-row {
		display: flex;
		align-items: center;
		justify-content: space-between;
		gap: var(--space-2);
	}
	.accounts {
		display: flex;
		flex-direction: column;
		gap: var(--space-2);
	}
	.account-row {
		padding: var(--space-2);
		border: var(--border-width) solid var(--border-color);
		border-radius: var(--radius-md);
		background: color-mix(in srgb, var(--surface) 56%, transparent);
	}
	.account-main {
		min-width: 0;
	}
	.account-title {
		justify-content: flex-start;
		font-weight: var(--font-weight-bold);
	}
	.account-title span:first-child,
	.sender,
	.subject,
	.detail-subject {
		overflow: hidden;
		text-overflow: ellipsis;
		white-space: nowrap;
	}
	.account-meta,
	.account-error,
	.date,
	.snippet,
	.detail-meta,
	.detail-from {
		color: var(--muted);
		font-size: 0.82rem;
	}
	.account-error {
		color: var(--danger);
		overflow-wrap: anywhere;
	}
	.account-actions,
	.message-tags,
	.detail-labels {
		display: flex;
		align-items: center;
		flex-wrap: wrap;
		gap: var(--space-1);
	}
	.mail-grid {
		display: grid;
		grid-template-columns: minmax(320px, 0.92fr) minmax(360px, 1.08fr);
		gap: var(--space-3);
		min-height: 38rem;
	}
	.inbox-panel,
	.detail-panel {
		min-width: 0;
		border: var(--border-width) solid var(--border-color);
		border-radius: var(--radius-lg);
		background: color-mix(in srgb, var(--surface) calc(var(--surface-alpha) * 100%), transparent);
		box-shadow: var(--shadow-md);
	}
	.inbox-panel {
		display: flex;
		flex-direction: column;
		overflow: hidden;
	}
	.search-row {
		display: grid;
		grid-template-columns: minmax(140px, 1fr) minmax(140px, 0.9fr) minmax(130px, 0.7fr) auto;
		gap: var(--space-2);
		align-items: end;
		padding: var(--space-3);
		border-bottom: var(--border-width) solid var(--border-color);
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
	.message-list {
		display: flex;
		flex-direction: column;
		gap: 1px;
		overflow: auto;
		padding: var(--space-2);
	}
	.message-row {
		display: flex;
		flex-direction: column;
		gap: var(--space-1);
		width: 100%;
		min-height: 8.5rem;
		text-align: left;
		color: var(--fg);
		background: transparent;
		border: var(--border-width) solid transparent;
		border-radius: var(--radius-md);
		padding: var(--space-3);
		cursor: pointer;
	}
	.message-row:hover,
	.message-row.selected {
		background: color-mix(in srgb, var(--accent) 10%, transparent);
		border-color: color-mix(in srgb, var(--accent) 42%, var(--border-color));
	}
	.sender,
	.subject,
	.detail-subject {
		font-weight: var(--font-weight-bold);
	}
	.date {
		flex: none;
	}
	.snippet {
		display: -webkit-box;
		line-clamp: 2;
		-webkit-line-clamp: 2;
		-webkit-box-orient: vertical;
		overflow: hidden;
		line-height: 1.35;
	}
	.detail-panel {
		display: flex;
		flex-direction: column;
		gap: var(--space-3);
		padding: var(--space-4);
		overflow: hidden;
	}
	.detail-head {
		align-items: flex-start;
	}
	.detail-subject {
		font-size: 1.08rem;
		white-space: normal;
		overflow-wrap: anywhere;
	}
	.message-body {
		flex: 1;
		min-height: 20rem;
		overflow: auto;
		white-space: pre-wrap;
		overflow-wrap: anywhere;
		margin: 0;
		font: inherit;
		line-height: 1.5;
		color: var(--fg);
	}

	@media (max-width: 1050px) {
		.top-grid,
		.mail-grid {
			grid-template-columns: 1fr;
		}
		.mail-grid {
			min-height: 0;
		}
	}
	@media (max-width: 760px) {
		.account-form,
		.search-row {
			grid-template-columns: 1fr;
		}
	}
</style>

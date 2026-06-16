<script lang="ts">
	import { onMount } from 'svelte';
	import { apiUrl } from '$lib/api';
	import { csrfToken } from '$lib/auth.svelte';
	import { deriveAuthKey } from '$lib/crypto/kdf';
	import { Badge, Button, Checkbox, Field, Icon, Stack, Surface, Text } from '$lib/components';

	interface GrantableApp {
		id: string;
		title: string;
		icon: string;
	}

	interface Account {
		username: string;
		role: 'admin' | 'child';
		must_reset: boolean;
		allowed_apps: string[] | null;
		created: number;
	}

	let apps = $state<GrantableApp[]>([]);
	let accounts = $state<Account[]>([]);
	let drafts = $state<Record<string, string[]>>({});
	let createName = $state('');
	let createAllowed = $state<string[]>([]);
	let busy = $state(false);
	let error = $state<string | null>(null);
	let created = $state<{ username: string; password: string; pin: string } | null>(null);

	onMount(() => {
		void load();
	});

	async function request<T>(path: string, init: RequestInit = {}): Promise<T> {
		const method = (init.method ?? 'GET').toUpperCase();
		const headers: Record<string, string> = {
			accept: 'application/json',
			...((init.headers as Record<string, string>) ?? {})
		};
		if (method !== 'GET') {
			const csrf = csrfToken();
			if (csrf) headers['x-csrf-token'] = csrf;
		}
		const res = await fetch(apiUrl(path), { ...init, credentials: 'include', headers });
		if (!res.ok) {
			const body = await res.json().catch(() => ({}));
			throw new Error(typeof body.detail === 'string' ? body.detail : `HTTP ${res.status}`);
		}
		if (res.status === 204) return undefined as T;
		return (await res.json()) as T;
	}

	async function load() {
		error = null;
		try {
			const [nextApps, nextAccounts] = await Promise.all([
				request<GrantableApp[]>('/api/auth/admin/apps'),
				request<Account[]>('/api/auth/admin/accounts')
			]);
			apps = nextApps;
			accounts = nextAccounts;
			const nextDrafts: Record<string, string[]> = {};
			for (const account of nextAccounts) {
				nextDrafts[account.username] = [...(account.allowed_apps ?? [])];
			}
			drafts = nextDrafts;
		} catch (e) {
			error = e instanceof Error ? e.message : 'Could not load accounts.';
		}
	}

	function randomString(length: number): string {
		const chars = 'ABCDEFGHJKLMNPQRSTUVWXYZabcdefghijkmnopqrstuvwxyz23456789';
		const bytes = new Uint8Array(length);
		crypto.getRandomValues(bytes);
		let out = '';
		for (const b of bytes) out += chars[b % chars.length];
		return out;
	}

	function randomPin(): string {
		const bytes = new Uint8Array(6);
		crypto.getRandomValues(bytes);
		return Array.from(bytes, (b) => String(b % 10)).join('');
	}

	function randomSalt(): string {
		const bytes = new Uint8Array(16);
		crypto.getRandomValues(bytes);
		let raw = '';
		for (const b of bytes) raw += String.fromCharCode(b);
		return btoa(raw).replace(/\+/g, '-').replace(/\//g, '_').replace(/=+$/, '');
	}

	function toggleCreate(appId: string) {
		createAllowed = createAllowed.includes(appId)
			? createAllowed.filter((id) => id !== appId)
			: [...createAllowed, appId];
	}

	function toggleDraft(username: string, appId: string) {
		const current = drafts[username] ?? [];
		drafts = {
			...drafts,
			[username]: current.includes(appId)
				? current.filter((id) => id !== appId)
				: [...current, appId]
		};
	}

	async function createAccount(e: Event) {
		e.preventDefault();
		const username = createName.trim();
		if (!username) return;
		const password = randomString(16);
		const pin = randomPin();
		const authSalt = randomSalt();
		const masterSalt = randomSalt();
		busy = true;
		error = null;
		try {
			const authKey = await deriveAuthKey(password, authSalt);
			await request('/api/auth/admin/accounts', {
				method: 'POST',
				headers: { 'content-type': 'application/json' },
				body: JSON.stringify({
					username,
					auth_key: authKey,
					temp_pin: pin,
					auth_salt: authSalt,
					master_salt: masterSalt,
					allowed_apps: createAllowed
				})
			});
			created = { username, password, pin };
			createName = '';
			createAllowed = [];
			await load();
		} catch (e) {
			error = e instanceof Error ? e.message : 'Could not create account.';
		} finally {
			busy = false;
		}
	}

	async function saveAccount(username: string) {
		busy = true;
		error = null;
		try {
			await request(`/api/auth/admin/accounts/${encodeURIComponent(username)}`, {
				method: 'PATCH',
				headers: { 'content-type': 'application/json' },
				body: JSON.stringify({ allowed_apps: drafts[username] ?? [] })
			});
			await load();
		} catch (e) {
			error = e instanceof Error ? e.message : 'Could not save account.';
		} finally {
			busy = false;
		}
	}

	async function deleteAccount(username: string) {
		if (!confirm(`Delete ${username}?`)) return;
		busy = true;
		error = null;
		try {
			await request(`/api/auth/admin/accounts/${encodeURIComponent(username)}`, {
				method: 'DELETE'
			});
			await load();
		} catch (e) {
			error = e instanceof Error ? e.message : 'Could not delete account.';
		} finally {
			busy = false;
		}
	}
</script>

<Stack gap={4}>
	{#if error}
		<div class="error">{error}</div>
	{/if}

	<Surface level={1}>
		<form onsubmit={createAccount}>
			<Stack gap={4}>
				<Text role="heading">Create child account</Text>
				<Field label="Account name" bind:value={createName} autocomplete="off" required />
				<div class="checklist">
					{#each apps as app (app.id)}
						<div class="check">
							<Checkbox
								checked={createAllowed.includes(app.id)}
								onchange={() => toggleCreate(app.id)}
							/>
							<Icon name={app.icon} size={16} />
							<span>{app.title}</span>
						</div>
					{/each}
				</div>
				<Button type="submit" disabled={busy || !createName.trim()}>
					<Icon name="plus" size={16} />
					<span>Create</span>
				</Button>
			</Stack>
		</form>
	</Surface>

	{#if created}
		<Surface level={1}>
			<Stack gap={3}>
				<Stack direction="row" align="center" justify="between">
					<Text role="heading">Temporary credentials</Text>
					<Button variant="ghost" size="sm" onclick={() => (created = null)}>
						<Icon name="x" size={15} />
					</Button>
				</Stack>
				<div class="credential-grid">
					<span>Account</span>
					<code>{created.username}</code>
					<span>Password</span>
					<code>{created.password}</code>
					<span>PIN</span>
					<code>{created.pin}</code>
				</div>
			</Stack>
		</Surface>
	{/if}

	<Stack gap={3}>
		<Text role="heading">Accounts</Text>
		{#each accounts as account (account.username)}
			<div class="account-row">
				<div class="account-head">
					<div>
						<div class="name">{account.username}</div>
						<div class="date">{new Date(account.created * 1000).toLocaleString()}</div>
					</div>
					<Stack direction="row" gap={2} align="center">
						<Badge variant={account.role === 'admin' ? 'accent' : 'neutral'}>
							{account.role === 'admin' ? 'Admin' : 'Child'}
						</Badge>
						{#if account.must_reset}
							<Badge variant="warn">Setup pending</Badge>
						{/if}
					</Stack>
				</div>

				{#if account.role === 'child'}
					<div class="checklist">
						{#each apps as app (app.id)}
							<div class="check">
								<Checkbox
									checked={(drafts[account.username] ?? []).includes(app.id)}
									onchange={() => toggleDraft(account.username, app.id)}
								/>
								<Icon name={app.icon} size={16} />
								<span>{app.title}</span>
							</div>
						{/each}
					</div>
					<div class="row-actions">
						<Button size="sm" disabled={busy} onclick={() => saveAccount(account.username)}>
							<Icon name="check" size={15} />
							<span>Save</span>
						</Button>
						<Button
							size="sm"
							variant="danger"
							disabled={busy}
							onclick={() => deleteAccount(account.username)}
						>
							<Icon name="trash" size={15} />
							<span>Delete</span>
						</Button>
					</div>
				{/if}
			</div>
		{/each}
	</Stack>
</Stack>

<style>
	.error {
		padding: var(--space-2) var(--space-3);
		color: var(--danger);
		background: color-mix(in srgb, var(--danger) 10%, transparent);
		border: var(--border-width) solid color-mix(in srgb, var(--danger) 35%, var(--border-color));
		border-radius: var(--radius-md);
	}
	.checklist {
		display: grid;
		grid-template-columns: repeat(auto-fit, minmax(150px, 1fr));
		gap: var(--space-2);
	}
	.check {
		display: flex;
		align-items: center;
		gap: var(--space-2);
		min-width: 0;
		padding: var(--space-2);
		background: color-mix(in srgb, var(--surface) 55%, transparent);
		border: var(--border-width) solid var(--border-color);
		border-radius: var(--radius-md);
		cursor: pointer;
	}
	.check span {
		min-width: 0;
		overflow: hidden;
		text-overflow: ellipsis;
		white-space: nowrap;
	}
	.credential-grid {
		display: grid;
		grid-template-columns: max-content 1fr;
		gap: var(--space-2) var(--space-3);
		align-items: center;
	}
	.credential-grid span {
		color: var(--muted);
		font-weight: var(--font-weight-bold);
	}
	code {
		min-width: 0;
		overflow-wrap: anywhere;
		padding: var(--space-1) var(--space-2);
		background: var(--surface);
		border: var(--border-width) solid var(--border-color);
		border-radius: var(--radius-sm);
	}
	.account-row {
		display: flex;
		flex-direction: column;
		gap: var(--space-3);
		padding: var(--space-3);
		background: color-mix(in srgb, var(--surface-2) 72%, transparent);
		border: var(--border-width) solid var(--border-color);
		border-radius: var(--radius-md);
		box-shadow: var(--shadow-sm);
	}
	.account-head {
		display: flex;
		align-items: flex-start;
		justify-content: space-between;
		gap: var(--space-3);
	}
	.name {
		font-weight: var(--font-weight-bold);
	}
	.date {
		color: var(--muted);
		font-size: 0.8rem;
	}
	.row-actions {
		display: flex;
		flex-wrap: wrap;
		gap: var(--space-2);
	}
	@media (max-width: 560px) {
		.account-head {
			flex-direction: column;
		}
		.credential-grid {
			grid-template-columns: 1fr;
		}
	}
</style>

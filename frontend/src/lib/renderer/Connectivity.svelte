<script lang="ts">
	// Connectivity dashboard — every way to reach this Raspy box, plus controls to
	// bring the remote links up. Admin only (backend 403s otherwise; hidden from
	// children). Shows LAN/private IPs, public IP, the Tailscale address + MagicDNS
	// link, and the Cloudflare tunnel — each as a copyable http://<addr>:<port> link.
	import { onMount } from 'svelte';
	import { attGet, attAction } from '$lib/api';
	import { Badge, Button, Icon, Stack, Surface, Text } from '$lib/components';

	interface LocalAddr {
		ip: string;
		version: 4 | 6;
		host: string;
		class: 'lan' | 'tailscale' | 'public' | 'link-local' | 'other';
		url: string;
	}
	interface TsLink {
		label: string;
		url: string;
	}
	interface Status {
		port: number;
		local: LocalAddr[];
		public: { v4: string | null; v6: string | null };
		tailscale: {
			installed: boolean;
			state: string;
			connected: boolean;
			ips: string[];
			magic_dns: string | null;
			links: TsLink[];
			login_url: string | null;
			login_name: string | null;
			display_name: string | null;
			hostname: string | null;
			tailnet: string | null;
			ssh: boolean;
			install_url: string;
		};
		cloudflare: {
			installed: boolean;
			configured: boolean;
			running: boolean;
			hostname: string | null;
			url: string | null;
			install_url: string;
		};
	}

	let { node }: { node: { title?: string } } = $props();

	let status = $state<Status | null>(null);
	let error = $state<string | null>(null);
	let busy = $state<string | null>(null);
	let copied = $state<string | null>(null);
	let cfTokenInput = $state('');

	onMount(() => void refresh());

	async function refresh() {
		try {
			status = await attGet<Status>('connectivity', 'status');
			error = null;
		} catch (e) {
			error = (e as Error)?.message ?? 'failed to load status';
		}
	}

	async function act(key: string, fn: () => Promise<unknown>) {
		busy = key;
		error = null;
		try {
			await fn();
			await refresh();
		} catch (e) {
			error = (e as Error)?.message ?? 'action failed';
		} finally {
			busy = null;
		}
	}

	async function copy(url: string) {
		try {
			await navigator.clipboard.writeText(url);
			copied = url;
			setTimeout(() => (copied === url ? (copied = null) : null), 1500);
		} catch {
			/* clipboard blocked — the link is still selectable */
		}
	}

	const lanAddrs = $derived((status?.local ?? []).filter((a) => a.class === 'lan'));
	const otherAddrs = $derived(
		(status?.local ?? []).filter((a) => a.class === 'link-local' || a.class === 'other')
	);

	const saveCfToken = () =>
		act('cf-token', async () => {
			await attAction('connectivity', 'POST', 'cloudflare/token', { token: cfTokenInput });
			cfTokenInput = '';
		});
	const cfUp = () => act('cf-up', () => attAction('connectivity', 'POST', 'cloudflare/up'));
	const cfDown = () => act('cf-down', () => attAction('connectivity', 'POST', 'cloudflare/down'));
	const tsUp = () => act('ts-up', () => attAction('connectivity', 'POST', 'tailscale/up'));
	const tsDown = () => act('ts-down', () => attAction('connectivity', 'POST', 'tailscale/down'));
	const tsLogout = () => act('ts-logout', () => attAction('connectivity', 'POST', 'tailscale/logout'));
	const tsSsh = (enable: boolean) =>
		act('ts-ssh', () => attAction('connectivity', 'POST', 'tailscale/ssh', { enable }));
</script>

{#snippet linkRow(label: string, url: string)}
	<div class="link">
		<span class="link-label">{label}</span>
		<a class="link-url" href={url} target="_blank" rel="noreferrer">{url}</a>
		<button class="copy" aria-label="Copy" onclick={() => copy(url)}>
			<Icon name={copied === url ? 'check-square' : 'file'} size={15} />
		</button>
	</div>
{/snippet}

<Stack gap={4}>
	<Text role="heading">{node.title ?? 'Connectivity'}</Text>
	<Text role="muted">Every address you can use to reach Raspy, plus remote-access setup.</Text>

	{#if error}
		<Surface level={2}><span class="err">{error}</span></Surface>
	{/if}

	{#if !status}
		<Text role="muted">Loading…</Text>
	{:else}
		<!-- LAN / same-network -->
		<Surface level={1}>
			<Stack gap={2}>
				<div class="head"><Icon name="home" size={18} /><Text role="title">On this network (LAN)</Text></div>
				{#if lanAddrs.length === 0}
					<Text role="muted">No private network address found.</Text>
				{:else}
					{#each lanAddrs as a (a.ip)}
						{@render linkRow(`IPv${a.version}`, a.url)}
					{/each}
				{/if}
			</Stack>
		</Surface>

		<!-- Tailscale -->
		<Surface level={1}>
			<Stack gap={2}>
				<div class="head">
					<Icon name="globe" size={18} /><Text role="title">Tailscale</Text>
					{#if status.tailscale.connected}
						<Badge variant="success">connected</Badge>
					{:else if status.tailscale.installed}
						<Badge variant="warn">{status.tailscale.state}</Badge>
					{:else}
						<Badge variant="neutral">not installed</Badge>
					{/if}
				</div>
				{#if !status.tailscale.installed}
					<Text role="muted">
						<code>tailscale</code> isn't installed.
						<a href={status.tailscale.install_url} target="_blank" rel="noreferrer">Install it</a>, then reload.
					</Text>
				{:else if status.tailscale.connected}
					{#if status.tailscale.login_name}
						<Text role="muted">
							Logged in as <b>{status.tailscale.login_name}</b>{#if status.tailscale.display_name}
								({status.tailscale.display_name}){/if}
						</Text>
					{/if}
					<Text role="muted">Reach Raspy from any device on your tailnet:</Text>
					{#each status.tailscale.links as l (l.url)}
						{@render linkRow(l.label, l.url)}
					{/each}
					<div class="row">
						{#if status.tailscale.ssh}
							<Badge variant="info">SSH on</Badge>
							<Button size="sm" variant="neutral" disabled={busy === 'ts-ssh'} onclick={() => tsSsh(false)}>
								Disable SSH
							</Button>
						{:else}
							<Button size="sm" variant="neutral" disabled={busy === 'ts-ssh'} onclick={() => tsSsh(true)}>
								Enable Tailscale SSH
							</Button>
						{/if}
						<Button size="sm" variant="warn" disabled={busy === 'ts-down'} onclick={tsDown}>Disconnect</Button>
						<Button size="sm" variant="danger" disabled={busy === 'ts-logout'} onclick={tsLogout}>Log out</Button>
					</div>
				{:else}
					{#if status.tailscale.login_url}
						<Text role="muted">Finish login to join your tailnet:</Text>
						<a class="link-url" href={status.tailscale.login_url} target="_blank" rel="noreferrer">
							{status.tailscale.login_url}
						</a>
					{/if}
					<div class="row">
						<Button size="sm" variant="accent" disabled={busy === 'ts-up'} onclick={tsUp}>
							{status.tailscale.login_url ? 'Re-check login' : 'Log in / connect'}
						</Button>
					</div>
					<Text role="muted">Tip: <code>tailscale up</code> may need root; if it fails, run it on the Pi.</Text>
				{/if}
			</Stack>
		</Surface>

		<!-- Cloudflare tunnel -->
		<Surface level={1}>
			<Stack gap={2}>
				<div class="head">
					<Icon name="globe" size={18} /><Text role="title">Cloudflare Tunnel</Text>
					{#if status.cloudflare.running}
						<Badge variant="success">running</Badge>
					{:else if status.cloudflare.configured}
						<Badge variant="warn">stopped</Badge>
					{:else}
						<Badge variant="neutral">not configured</Badge>
					{/if}
				</div>
				{#if !status.cloudflare.installed}
					<Text role="muted">
						<code>cloudflared</code> isn't installed.
						<a href={status.cloudflare.install_url} target="_blank" rel="noreferrer">Install it</a>, then reload.
					</Text>
				{:else}
					{#if status.cloudflare.url}
						{@render linkRow('Public', status.cloudflare.url)}
					{/if}
					<label class="lbl">
						<span>Tunnel token</span>
						<input
							class="in"
							type="password"
							placeholder={status.cloudflare.configured ? '•••••• (configured)' : 'paste your tunnel token'}
							bind:value={cfTokenInput}
						/>
					</label>
					<div class="row">
						<Button size="sm" variant="neutral" disabled={!cfTokenInput || busy === 'cf-token'} onclick={saveCfToken}>
							Save token
						</Button>
						{#if status.cloudflare.running}
							<Button size="sm" variant="danger" disabled={busy === 'cf-down'} onclick={cfDown}>Disconnect</Button>
						{:else}
							<Button size="sm" variant="accent" disabled={!status.cloudflare.configured || busy === 'cf-up'} onclick={cfUp}>
								Connect
							</Button>
						{/if}
					</div>
				{/if}
			</Stack>
		</Surface>

		<!-- Public IP (informational) -->
		<Surface level={1}>
			<Stack gap={2}>
				<div class="head"><Icon name="globe" size={18} /><Text role="title">Public IP</Text></div>
				{#if status.public.v4 || status.public.v6}
					{#if status.public.v4}{@render linkRow('IPv4', `http://${status.public.v4}:${status.port}`)}{/if}
					{#if status.public.v6}{@render linkRow('IPv6', `http://[${status.public.v6}]:${status.port}`)}{/if}
					<Text role="muted">Only reachable if you've forwarded the port / exposed the box directly.</Text>
				{:else}
					<Text role="muted">Couldn't determine a public IP (offline or blocked).</Text>
				{/if}
			</Stack>
		</Surface>

		{#if otherAddrs.length}
			<Surface level={2}>
				<Stack gap={2}>
					<Text role="muted">Other interfaces</Text>
					{#each otherAddrs as a (a.ip)}
						{@render linkRow(`IPv${a.version} (${a.class})`, a.url)}
					{/each}
				</Stack>
			</Surface>
		{/if}
	{/if}
</Stack>

<style>
	.head {
		display: flex;
		align-items: center;
		gap: var(--space-2);
	}
	.row {
		display: flex;
		gap: var(--space-2);
		flex-wrap: wrap;
	}
	.link {
		display: flex;
		align-items: center;
		gap: var(--space-2);
		min-width: 0;
	}
	.link-label {
		flex: none;
		min-width: 3.5rem;
		font-size: 0.8rem;
		color: var(--fg-muted, var(--fg));
	}
	.link-url {
		flex: 1;
		min-width: 0;
		overflow: hidden;
		text-overflow: ellipsis;
		white-space: nowrap;
		font-family: var(--font-mono, monospace);
		font-size: 0.85rem;
	}
	.copy {
		flex: none;
		display: inline-flex;
		padding: var(--space-1);
		background: transparent;
		color: var(--fg-muted, var(--fg));
		border: none;
		border-radius: var(--radius-md);
		cursor: pointer;
	}
	.copy:hover {
		background: var(--surface);
	}
	.lbl {
		display: flex;
		flex-direction: column;
		gap: var(--space-1);
		font-size: 0.85rem;
		color: var(--fg-muted, var(--fg));
	}
	.in {
		width: 100%;
		padding: var(--space-2) var(--space-3);
		background: var(--surface);
		color: var(--fg);
		border: var(--border-width) solid var(--border-color);
		border-radius: var(--radius-md);
		font: inherit;
	}
	.err {
		color: var(--danger, crimson);
		font-size: 0.9rem;
	}
	code {
		font-family: var(--font-mono, monospace);
		font-size: 0.85em;
	}
</style>

<script lang="ts">
	// Connectivity dashboard — every way to reach this Raspy box, plus controls to
	// bring the remote links up. Admin only (backend 403s otherwise; hidden from
	// children). Shows LAN/private IPs, public IP, the Tailscale address + MagicDNS
	// link, and the Cloudflare tunnel — each as a copyable http://<addr>:<port> link.
	import { onMount } from 'svelte';
	import { attGet, attAction, type ApiError } from '$lib/api';
	import { Badge, Button, Field, Icon, Stack, Surface, SudoPrompt, Text } from '$lib/components';

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
			exit_node: string | null;
			advertising_exit_node: boolean;
			exit_nodes: { name: string; online: boolean }[];
			version: string | null;
			update_available: boolean;
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

	// sudo-password prompt state. When a privileged action returns the backend's
	// `needs-root` signal (HTTP 428), we stash it here and re-run it with the
	// password the user types. The password lives only inside SudoPrompt.
	let sudo = $state<{
		open: boolean;
		busy: boolean;
		error: string | null;
		detail: string;
		retry: ((password: string) => Promise<unknown>) | null;
	}>({ open: false, busy: false, error: null, detail: '', retry: null });

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

	/** Run a privileged tailscale action. `run(password)` calls the endpoint with
	 *  the optional sudo password. On a 428 needs-root we open the prompt; the
	 *  prompt's submit re-invokes `run` with the typed password. A 403 means the
	 *  password was wrong — we keep the dialog open and show the error. */
	async function privileged(key: string, detail: string, run: (password?: string) => Promise<unknown>) {
		const attempt = async (password?: string) => {
			try {
				await run(password);
				sudo.open = false;
				sudo.retry = null;
				await refresh();
			} catch (e) {
				const err = e as ApiError;
				if (err.status === 428) {
					// Needs root and we haven't supplied a password yet → prompt.
					sudo = { open: true, busy: false, error: null, detail, retry: async (p) => attempt(p) };
				} else if (err.status === 403 && sudo.open) {
					sudo.busy = false;
					sudo.error = err.detail ?? 'wrong sudo password';
				} else {
					sudo.open = false;
					sudo.retry = null;
					error = err.detail ?? err.message ?? 'action failed';
				}
			}
		};
		busy = key;
		error = null;
		try {
			await attempt();
		} finally {
			busy = null;
		}
	}

	function onSudoSubmit(password: string) {
		sudo.busy = true;
		sudo.error = null;
		void sudo.retry?.(password);
	}

	function onSudoCancel() {
		sudo = { open: false, busy: false, error: null, detail: '', retry: null };
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
	// Tailscale mutations may need root; `privileged` prompts for sudo on a 428.
	const tsUp = () =>
		privileged('ts-up', 'tailscale up', (sudo_password) =>
			attAction('connectivity', 'POST', 'tailscale/up', { sudo_password })
		);
	const tsDown = () =>
		privileged('ts-down', 'tailscale down', (sudo_password) =>
			attAction('connectivity', 'POST', 'tailscale/down', { sudo_password })
		);
	const tsLogout = () =>
		privileged('ts-logout', 'tailscale logout', (sudo_password) =>
			attAction('connectivity', 'POST', 'tailscale/logout', { sudo_password })
		);
	const tsSsh = (enable: boolean) =>
		privileged('ts-ssh', `tailscale set --ssh${enable ? '' : '=false'}`, (sudo_password) =>
			attAction('connectivity', 'POST', 'tailscale/ssh', { enable, sudo_password })
		);
	let exitNodeChoice = $state('');
	const tsExitNode = (node: string) =>
		privileged('ts-exit-node', `tailscale set --exit-node=${node || '(clear)'}`, (sudo_password) =>
			attAction('connectivity', 'POST', 'tailscale/exit-node', { node, sudo_password })
		);
	const tsAdvertiseExit = (enable: boolean) =>
		privileged('ts-advertise-exit', `tailscale set --advertise-exit-node${enable ? '' : '=false'}`, (sudo_password) =>
			attAction('connectivity', 'POST', 'tailscale/advertise-exit-node', { enable, sudo_password })
		);
	const tsUpdate = () =>
		privileged('ts-update', 'tailscale update --yes', (sudo_password) =>
			attAction('connectivity', 'POST', 'tailscale/update', { sudo_password })
		);

	// Read-only diagnostics — show their text output inline (no sudo).
	let diag = $state<{ kind: string; text: string } | null>(null);
	let pingTarget = $state('');
	async function runDiag(kind: 'netcheck' | 'ping', body?: Record<string, unknown>) {
		busy = `ts-${kind}`;
		error = null;
		diag = null;
		try {
			const r = await attAction<{ ok: boolean; output: string }>(
				'connectivity',
				'POST',
				`tailscale/${kind}`,
				body
			);
			diag = { kind, text: r.output || '(no output)' };
		} catch (e) {
			error = (e as ApiError)?.detail ?? (e as Error)?.message ?? 'diagnostic failed';
		} finally {
			busy = null;
		}
	}
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
							<!-- Exit node: route this box's traffic through a tailnet peer. -->
						{#if status.tailscale.exit_nodes.length || status.tailscale.exit_node}
							<div class="sub">
								<Text role="label">Exit node</Text>
								{#if status.tailscale.exit_node}
									<Text role="muted">Routing through <b>{status.tailscale.exit_node}</b>.</Text>
									<Button size="sm" variant="neutral" disabled={busy === 'ts-exit-node'} onclick={() => tsExitNode('')}>
										Stop using exit node
									</Button>
								{:else}
									<div class="row">
										<Field
											type="select"
											bind:value={exitNodeChoice}
											options={[
												{ value: '', label: 'Select a peer…' },
												...status.tailscale.exit_nodes.map((n) => ({
													value: n.name,
													label: n.online ? n.name : `${n.name} (offline)`
												}))
											]}
										/>
										<Button size="sm" variant="accent" disabled={!exitNodeChoice || busy === 'ts-exit-node'} onclick={() => tsExitNode(exitNodeChoice)}>
											Use
										</Button>
									</div>
								{/if}
							</div>
						{/if}

						<!-- Advertise this node as an exit node for others. -->
						<div class="row">
							{#if status.tailscale.advertising_exit_node}
								<Badge variant="info">offering exit node</Badge>
								<Button size="sm" variant="neutral" disabled={busy === 'ts-advertise-exit'} onclick={() => tsAdvertiseExit(false)}>
									Stop offering exit node
								</Button>
							{:else}
								<Button size="sm" variant="neutral" disabled={busy === 'ts-advertise-exit'} onclick={() => tsAdvertiseExit(true)}>
									Offer as exit node
								</Button>
							{/if}
						</div>

						<!-- Client version + self-update. -->
						{#if status.tailscale.version}
							<div class="row">
								<Text role="muted">Client <code>{status.tailscale.version}</code></Text>
								{#if status.tailscale.update_available}
									<Badge variant="warn">update available</Badge>
									<Button size="sm" variant="accent" disabled={busy === 'ts-update'} onclick={tsUpdate}>Update tailscale</Button>
								{/if}
							</div>
						{/if}

						<!-- Read-only diagnostics. -->
						<div class="sub">
							<Text role="label">Diagnostics</Text>
							<div class="row">
								<Button size="sm" variant="ghost" disabled={busy === 'ts-netcheck'} onclick={() => runDiag('netcheck')}>
									{busy === 'ts-netcheck' ? 'Checking…' : 'Run netcheck'}
								</Button>
								<input class="in diag-target" type="text" placeholder="peer to ping (IP or name)" bind:value={pingTarget} />
								<Button size="sm" variant="ghost" disabled={!pingTarget || busy === 'ts-ping'} onclick={() => runDiag('ping', { target: pingTarget })}>
									{busy === 'ts-ping' ? 'Pinging…' : 'Ping'}
								</Button>
							</div>
							{#if diag}
								<pre class="diag-out">{diag.text}</pre>
							{/if}
						</div>
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
					<Text role="muted">Tip: <code>tailscale up</code> may need root — if it does, you'll be asked for your sudo password.</Text>
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

<SudoPrompt
	open={sudo.open}
	detail={sudo.detail}
	busy={sudo.busy}
	error={sudo.error}
	onsubmit={onSudoSubmit}
	oncancel={onSudoCancel}
/>

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
	/* A grouped sub-section inside the Tailscale card (exit node, diagnostics). */
	.sub {
		display: flex;
		flex-direction: column;
		gap: var(--space-2);
		padding-top: var(--space-2);
		border-top: var(--border-width) solid var(--border-color);
	}
	.diag-target {
		flex: 1;
		min-width: 8rem;
	}
	.diag-out {
		margin: 0;
		max-height: 16rem;
		overflow: auto;
		padding: var(--space-2) var(--space-3);
		background: color-mix(in srgb, var(--surface-2) calc(var(--surface-alpha) * 100%), transparent);
		border: var(--border-width) solid var(--border-color);
		border-radius: var(--radius-md);
		font-family: var(--font-mono, monospace);
		font-size: 0.8rem;
		white-space: pre-wrap;
		word-break: break-word;
	}
	code {
		font-family: var(--font-mono, monospace);
		font-size: 0.85em;
	}
</style>

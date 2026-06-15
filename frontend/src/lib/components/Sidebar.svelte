<script lang="ts">
	// App navigation, driven entirely by the backend manifest. Lists every loaded
	// attachment as a link to /a/<id>; the home link goes to the dashboard. Footer
	// carries the live connection status and the theme picker.
	import { page } from '$app/state';
	import Icon from './Icon.svelte';
	import Badge from './Badge.svelte';
	import Button from './Button.svelte';
	import Modal from './Modal.svelte';
	import ThemePicker from './ThemePicker.svelte';
	import { manifest } from '$lib/manifest/store.svelte';
	import { connection } from '$lib/connection.svelte';
	import { notifications, type PushStatus } from '$lib/notifications/store.svelte';
	import { auth } from '$lib/auth.svelte';

	// `onClose`, when provided, renders the in-drawer close button (mobile only) and
	// is also fired when a nav link is tapped so the drawer dismisses on navigation.
	let { onClose }: { onClose?: () => void } = $props();
	let accountOpen = $state(false);

	async function togglePush() {
		if (notifications.pushEnabled) await notifications.disablePush();
		else await notifications.enablePush();
	}

	const pushVariant: Record<PushStatus, 'success' | 'warn' | 'danger' | 'neutral'> = {
		enabled: 'success',
		off: 'warn',
		denied: 'danger',
		unsupported: 'neutral'
	};
	const pushLabel: Record<PushStatus, string> = {
		enabled: 'Enabled',
		off: 'Off',
		denied: 'Blocked',
		unsupported: 'Unsupported'
	};
	const pushDetail: Record<PushStatus, string> = {
		enabled: 'Permission granted and this device is subscribed.',
		off: 'Supported, but this device is not subscribed.',
		denied: 'Browser permission is blocked for this site.',
		unsupported: 'This browser or connection cannot use Web Push.'
	};

	// The brand dot encodes both channels at once so the footer can drop the two
	// status pills: red = nothing up, amber = one of the two, green = both.
	type LinkHealth = 'none' | 'api' | 'ws' | 'all';
	const linkHealth = $derived<LinkHealth>(
		connection.http === 'online' && connection.ws === 'online'
			? 'all'
			: connection.http === 'online'
				? 'api'
				: connection.ws === 'online'
					? 'ws'
					: 'none'
	);
	const linkTitle: Record<LinkHealth, string> = {
		all: 'API & WebSocket connected',
		api: 'API connected · WebSocket offline',
		ws: 'WebSocket connected · API offline',
		none: 'Disconnected'
	};

	function active(href: string): boolean {
		if (href === '/') return page.url.pathname === '/';
		return page.url.pathname === href;
	}

	async function leaveAccount() {
		accountOpen = false;
		onClose?.();
		await auth.logout();
	}
</script>

<aside class="sidebar">
	<div class="brand">
		<span class="dot {linkHealth}" title={linkTitle[linkHealth]}></span>
		<span class="brand-name">Raspy</span>
		{#if onClose}
			<button class="drawer-close" aria-label="Close menu" onclick={onClose}>
				<Icon name="x" size={20} />
			</button>
		{/if}
	</div>

	<nav class="nav">
		<a class="item" class:active={active('/')} href="/" onclick={onClose}>
			<Icon name="home" />
			<span>Dashboard</span>
		</a>

		<div class="section-label">Apps</div>

		<!-- Only the app list scrolls; the Dashboard link and "Apps" label above it
		     stay pinned, and a long list never pushes the footer off-screen. -->
		<div class="apps">
			{#if manifest.loading && manifest.attachments.length === 0}
				{#each [0, 1, 2] as i (i)}
					<div class="item skeleton"></div>
				{/each}
			{:else if manifest.attachments.length === 0}
				<div class="empty">No apps {manifest.error ? '(offline)' : 'installed'}.</div>
			{:else}
				{#each manifest.attachments as app (app.id)}
					<a class="item" class:active={active(`/a/${app.id}`)} href="/a/{app.id}" onclick={onClose}>
						<Icon name={app.icon} />
						<span>{app.title}</span>
						{#if app.id === 'notifications' && notifications.unread > 0}
							<span class="count">{notifications.unread > 99 ? '99+' : notifications.unread}</span>
						{/if}
					</a>
				{/each}
			{/if}
		</div>
	</nav>

	<div class="footer">
		<button class="account" onclick={() => (accountOpen = true)} aria-label="Account">
			<Icon name="user" />
			<span class="account-name">{auth.username ?? 'Account'}</span>
			<span class="account-role">{auth.role === 'admin' ? 'Admin' : 'Child'}</span>
		</button>
		{#if connection.version}
			<div class="meta">v{connection.version} · {connection.attachmentCount} apps</div>
		{/if}
		<details class="disclosure push {notifications.pushStatus}">
			<summary>
				<span class="push-dot" aria-hidden="true"></span>
				<span class="disclosure-label">Push</span>
				<Badge variant={pushVariant[notifications.pushStatus]}>
					{pushLabel[notifications.pushStatus]}
				</Badge>
			</summary>
			<div class="disclosure-body push-body">
				<div class="push-detail">{pushDetail[notifications.pushStatus]}</div>
				{#if notifications.pushError}
					<div class="push-error">{notifications.pushError}</div>
				{/if}
				{#if notifications.pushStatus === 'enabled' || notifications.pushStatus === 'off'}
					<button class="push-toggle" disabled={notifications.pushBusy} onclick={togglePush}>
						<Icon name={notifications.pushStatus === 'enabled' ? 'bell-off' : 'bell'} size={15} />
						<span>
							{notifications.pushBusy
								? 'Working…'
								: notifications.pushStatus === 'enabled'
									? 'Disable push'
									: 'Enable push'}
						</span>
					</button>
				{/if}
			</div>
		</details>

		<details class="disclosure theme">
			<summary><span class="disclosure-label">Theme</span></summary>
			<div class="disclosure-body"><ThemePicker /></div>
		</details>
	</div>
</aside>

<Modal open={accountOpen} title="Account" size="sm" onclose={() => (accountOpen = false)}>
	<div class="account-panel">
		<div class="identity">
			<div class="identity-name">{auth.username}</div>
			<div class="identity-role">{auth.role === 'admin' ? 'Master admin' : 'Child account'}</div>
		</div>
		<Button variant="neutral" onclick={leaveAccount}>
			<Icon name="log-out" size={16} />
			<span>Sign out</span>
		</Button>
		<Button variant="ghost" onclick={leaveAccount}>
			<Icon name="users" size={16} />
			<span>Switch account</span>
		</Button>
	</div>
</Modal>

<style>
	.sidebar {
		display: flex;
		flex-direction: column;
		gap: var(--space-3);
		width: 240px;
		flex: none;
		height: 100dvh;
		position: sticky;
		top: 0;
		padding: var(--space-4) var(--space-3);
		background: color-mix(
			in srgb,
			var(--surface-2) calc(var(--surface-alpha, 1) * 100%),
			transparent
		);
		backdrop-filter: blur(var(--blur));
		-webkit-backdrop-filter: blur(var(--blur));
		border-right: var(--border-width) solid var(--border-color);
		overflow: hidden;
	}
	.brand {
		display: flex;
		align-items: center;
		gap: var(--space-2);
		padding: 0 var(--space-2);
		flex: none;
	}
	.brand-name {
		font-weight: var(--font-weight-bold);
		font-size: 1.05rem;
	}
	.drawer-close {
		display: none;
		margin-left: auto;
		align-items: center;
		justify-content: center;
		padding: var(--space-1);
		background: transparent;
		color: var(--muted);
		border: none;
		border-radius: var(--radius-md);
		cursor: pointer;
	}
	.drawer-close:hover {
		color: var(--fg);
		background: var(--surface);
	}
	.count {
		margin-left: auto;
		min-width: 1.15rem;
		height: 1.15rem;
		padding: 0 5px;
		display: inline-flex;
		align-items: center;
		justify-content: center;
		font-size: 0.66rem;
		font-weight: var(--font-weight-bold);
		line-height: 1;
		color: var(--danger-fg);
		background: var(--danger);
		border-radius: var(--radius-full);
	}
	.dot {
		width: 0.6rem;
		height: 0.6rem;
		border-radius: var(--radius-full);
		background: var(--muted);
		flex: none;
	}
	/* Brand-dot color coding: both channels up (green), exactly one up (amber),
	   neither (red). */
	.dot.all {
		background: var(--success);
	}
	.dot.api,
	.dot.ws {
		background: var(--warn);
	}
	.dot.none {
		background: var(--danger);
	}
	@keyframes pulse {
		0%,
		100% {
			opacity: 1;
		}
		50% {
			opacity: 0.35;
		}
	}
	.nav {
		display: flex;
		flex-direction: column;
		gap: 2px;
		flex: 1;
		min-height: 0;
	}
	/* The scrollable app list. The Dashboard link and "Apps" label above stay
	   pinned; only this region scrolls when the list outgrows the column. */
	.apps {
		display: flex;
		flex-direction: column;
		gap: 2px;
		flex: 1;
		min-height: 0;
		overflow-y: auto;
		/* Room for the scrollbar so rows don't sit under it. */
		margin-right: calc(-1 * var(--space-1));
		padding-right: var(--space-1);
	}
	.section-label {
		font-size: 0.7rem;
		text-transform: uppercase;
		letter-spacing: 0.05em;
		color: var(--muted);
		padding: var(--space-3) var(--space-2) var(--space-1);
	}
	.item {
		display: flex;
		align-items: center;
		gap: var(--space-2);
		padding: var(--space-2) var(--space-2);
		border-radius: var(--radius-md);
		color: var(--muted);
		text-decoration: none;
		font-weight: var(--font-weight-bold);
		font-size: 0.92rem;
		transition: color 120ms var(--motion-ease, ease), background 120ms var(--motion-ease, ease);
	}
	.item:hover {
		color: var(--fg);
		background: var(--surface);
	}
	.item.active {
		color: var(--accent);
		background: color-mix(in srgb, var(--accent) 14%, transparent);
	}
	.item.skeleton {
		height: 2.1rem;
		background: var(--surface);
		opacity: 0.6;
		animation: pulse 1.2s ease-in-out infinite;
	}
	.empty {
		color: var(--muted);
		font-size: 0.85rem;
		padding: var(--space-2);
	}
	.footer {
		display: flex;
		flex-direction: column;
		gap: var(--space-2);
		margin-top: var(--space-3);
		padding-top: var(--space-3);
		border-top: var(--border-width) solid var(--border-color);
		flex: none;
	}
	.account {
		display: grid;
		grid-template-columns: auto 1fr auto;
		align-items: center;
		gap: var(--space-2);
		width: 100%;
		min-width: 0;
		padding: var(--space-2);
		color: var(--fg);
		background: color-mix(in srgb, var(--surface) 58%, transparent);
		border: var(--border-width) solid var(--border-color);
		border-radius: var(--radius-md);
		cursor: pointer;
		text-align: left;
	}
	.account:hover {
		background: var(--surface);
	}
	.account-name {
		min-width: 0;
		overflow: hidden;
		text-overflow: ellipsis;
		white-space: nowrap;
		font-weight: var(--font-weight-bold);
	}
	.account-role {
		color: var(--muted);
		font-size: 0.72rem;
	}
	.account-panel {
		display: flex;
		flex-direction: column;
		gap: var(--space-3);
	}
	.identity {
		display: flex;
		flex-direction: column;
		gap: 2px;
		padding-bottom: var(--space-2);
		border-bottom: var(--border-width) solid var(--border-color);
	}
	.identity-name {
		font-weight: var(--font-weight-bold);
	}
	.identity-role {
		color: var(--muted);
		font-size: 0.85rem;
	}
	.signals {
		display: flex;
		flex-wrap: wrap;
		gap: var(--space-1);
	}
	.meta {
		color: var(--muted);
		font-size: 0.75rem;
	}
	/* Collapsible footer sections (Push, Theme). Compact summary rows so the
	   drawer footer stays short; details expand on tap/click. */
	.disclosure {
		border: var(--border-width) solid var(--border-color);
		border-radius: var(--radius-md);
		background: color-mix(in srgb, var(--surface) 58%, transparent);
	}
	.disclosure > summary {
		display: flex;
		align-items: center;
		gap: var(--space-2);
		padding: var(--space-2);
		cursor: pointer;
		list-style: none;
		font-size: 0.8rem;
		font-weight: var(--font-weight-bold);
		color: var(--muted);
	}
	.disclosure > summary::-webkit-details-marker {
		display: none;
	}
	.disclosure-label {
		color: var(--fg);
		margin-right: auto;
	}
	.disclosure[open] > summary {
		border-bottom: var(--border-width) solid var(--border-color);
	}
	.disclosure-body {
		padding: var(--space-2);
	}
	.push-body {
		display: flex;
		flex-direction: column;
		gap: var(--space-2);
	}
	.push-dot {
		width: 0.6rem;
		height: 0.6rem;
		border-radius: var(--radius-full);
		background: var(--muted);
		flex: none;
	}
	.push.enabled .push-dot {
		background: var(--success);
	}
	.push.off .push-dot {
		background: var(--warn);
	}
	.push.denied .push-dot {
		background: var(--danger);
	}
	.push-detail,
	.push-error {
		font-size: 0.72rem;
		line-height: 1.35;
		overflow-wrap: anywhere;
	}
	.push-detail {
		color: var(--muted);
	}
	.push-error {
		color: var(--danger);
	}
	.push-toggle {
		display: inline-flex;
		align-items: center;
		justify-content: center;
		gap: var(--space-2);
		padding: var(--space-1) var(--space-2);
		background: transparent;
		border: var(--border-width) solid var(--border-color);
		border-radius: var(--radius-md);
		color: var(--muted);
		font-size: 0.78rem;
		font-weight: var(--font-weight-bold);
		cursor: pointer;
		transition: color 120ms ease, background 120ms ease;
	}
	.push-toggle:hover {
		color: var(--fg);
		background: var(--surface);
	}
	.push-toggle:disabled {
		cursor: wait;
		opacity: 0.65;
	}

	@media (max-width: 720px) {
		.sidebar {
			/* Inside the drawer the sidebar fills the panel; the drawer (in the
			   layout) owns positioning, width, and the slide animation. */
			width: 100%;
			height: 100%;
			position: static;
			border-right: none;
		}
		.drawer-close {
			display: inline-flex;
		}
	}
</style>

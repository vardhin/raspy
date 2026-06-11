<script lang="ts">
	// App navigation, driven entirely by the backend manifest. Lists every loaded
	// attachment as a link to /a/<id>; the home link goes to the dashboard. Footer
	// carries the live connection status and the theme picker.
	import { page } from '$app/state';
	import Icon from './Icon.svelte';
	import Badge from './Badge.svelte';
	import ThemePicker from './ThemePicker.svelte';
	import { manifest } from '$lib/manifest/store.svelte';
	import { connection, type LinkState } from '$lib/connection.svelte';
	import { notifications, type PushStatus } from '$lib/notifications/store.svelte';

	async function togglePush() {
		if (notifications.pushEnabled) await notifications.disablePush();
		else await notifications.enablePush();
	}

	const stateVariant: Record<LinkState, 'success' | 'warn' | 'danger'> = {
		online: 'success',
		connecting: 'warn',
		offline: 'danger'
	};
	const stateLabel: Record<LinkState, string> = {
		online: 'Connected',
		connecting: 'Connecting…',
		offline: 'Offline'
	};
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

	const overall = $derived<LinkState>(
		connection.http === 'online' && connection.ws === 'online'
			? 'online'
			: connection.http === 'offline' && connection.ws === 'offline'
				? 'offline'
				: 'connecting'
	);

	function active(href: string): boolean {
		if (href === '/') return page.url.pathname === '/';
		return page.url.pathname === href;
	}
</script>

<aside class="sidebar">
	<div class="brand">
		<span class="dot {overall}" title={stateLabel[overall]}></span>
		<span class="brand-name">Raspy</span>
	</div>

	<nav class="nav">
		<a class="item" class:active={active('/')} href="/">
			<Icon name="home" />
			<span>Dashboard</span>
		</a>

		<div class="section-label">Apps</div>

		{#if manifest.loading && manifest.attachments.length === 0}
			{#each [0, 1, 2] as i (i)}
				<div class="item skeleton"></div>
			{/each}
		{:else if manifest.attachments.length === 0}
			<div class="empty">No apps {manifest.error ? '(offline)' : 'installed'}.</div>
		{:else}
			{#each manifest.attachments as app (app.id)}
				<a class="item" class:active={active(`/a/${app.id}`)} href="/a/{app.id}">
					<Icon name={app.icon} />
					<span>{app.title}</span>
					{#if app.id === 'notifications' && notifications.unread > 0}
						<span class="count">{notifications.unread > 99 ? '99+' : notifications.unread}</span>
					{/if}
				</a>
			{/each}
		{/if}
	</nav>

	<div class="footer">
		<div class="signals">
			<Badge variant={stateVariant[connection.http]}>API · {stateLabel[connection.http]}</Badge>
			<Badge variant={stateVariant[connection.ws]}>WS · {stateLabel[connection.ws]}</Badge>
		</div>
		{#if connection.version}
			<div class="meta">v{connection.version} · {connection.attachmentCount} apps</div>
		{/if}
		<div class="push-panel {notifications.pushStatus}">
			<div class="push-state">
				<span class="push-dot" aria-hidden="true"></span>
				<div class="push-copy">
					<div class="push-title">
						Push <Badge variant={pushVariant[notifications.pushStatus]}>
							{pushLabel[notifications.pushStatus]}
						</Badge>
					</div>
					<div class="push-detail">{pushDetail[notifications.pushStatus]}</div>
				</div>
			</div>
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

		<details class="theme">
			<summary>Theme</summary>
			<div class="theme-body"><ThemePicker /></div>
		</details>
	</div>
</aside>

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
		overflow-y: auto;
	}
	.brand {
		display: flex;
		align-items: center;
		gap: var(--space-2);
		padding: 0 var(--space-2);
	}
	.brand-name {
		font-weight: var(--font-weight-bold);
		font-size: 1.05rem;
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
	.dot.online {
		background: var(--success);
	}
	.dot.connecting {
		background: var(--warn);
		animation: pulse 1.2s ease-in-out infinite;
	}
	.dot.offline {
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
		padding-top: var(--space-3);
		border-top: var(--border-width) solid var(--border-color);
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
	.push-panel {
		display: flex;
		flex-direction: column;
		gap: var(--space-2);
		padding: var(--space-2);
		border: var(--border-width) solid var(--border-color);
		border-radius: var(--radius-md);
		background: color-mix(in srgb, var(--surface) 58%, transparent);
	}
	.push-state {
		display: flex;
		align-items: flex-start;
		gap: var(--space-2);
		min-width: 0;
	}
	.push-dot {
		width: 0.6rem;
		height: 0.6rem;
		margin-top: 0.42rem;
		border-radius: var(--radius-full);
		background: var(--muted);
		flex: none;
	}
	.push-panel.enabled .push-dot {
		background: var(--success);
	}
	.push-panel.off .push-dot {
		background: var(--warn);
	}
	.push-panel.denied .push-dot {
		background: var(--danger);
	}
	.push-copy {
		display: flex;
		flex-direction: column;
		gap: 3px;
		min-width: 0;
	}
	.push-title {
		display: flex;
		align-items: center;
		gap: var(--space-1);
		color: var(--fg);
		font-size: 0.78rem;
		font-weight: var(--font-weight-bold);
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
	.theme summary {
		cursor: pointer;
		font-size: 0.8rem;
		font-weight: var(--font-weight-bold);
		color: var(--muted);
		padding: var(--space-1) 0;
	}
	.theme-body {
		padding-top: var(--space-2);
	}

	@media (max-width: 720px) {
		.sidebar {
			width: 100%;
			height: auto;
			position: static;
			flex-direction: column;
			border-right: none;
			border-bottom: var(--border-width) solid var(--border-color);
		}
	}
</style>

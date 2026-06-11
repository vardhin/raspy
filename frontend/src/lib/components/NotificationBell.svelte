<script lang="ts">
	// Bell + dropdown panel of notification history. Lives in the sidebar footer.
	// The unread count and list are driven by the reactive notifications store;
	// "Enable on this device" opts into background Web Push (service worker).
	import Icon from './Icon.svelte';
	import { notifications } from '$lib/notifications/store.svelte';

	let open = $state(false);

	function toggle() {
		open = !open;
		if (open) notifications.refresh();
	}

	function relative(ts: number): string {
		const s = Math.max(0, Math.floor(Date.now() / 1000 - ts));
		if (s < 60) return 'just now';
		if (s < 3600) return `${Math.floor(s / 60)}m ago`;
		if (s < 86400) return `${Math.floor(s / 3600)}h ago`;
		return `${Math.floor(s / 86400)}d ago`;
	}

	async function togglePush() {
		if (notifications.pushEnabled) await notifications.disablePush();
		else await notifications.enablePush();
	}
</script>

<div class="bell-wrap">
	<button class="bell" onclick={toggle} aria-label="Notifications" title="Notifications">
		<Icon name="bell" />
		{#if notifications.unread > 0}
			<span class="count">{notifications.unread > 99 ? '99+' : notifications.unread}</span>
		{/if}
	</button>

	{#if open}
		<!-- click-away backdrop -->
		<button class="backdrop" aria-label="Close notifications" onclick={() => (open = false)}
		></button>

		<div class="panel" role="dialog" aria-label="Notifications">
			<div class="panel-head">
				<span class="title">Notifications</span>
				<div class="head-actions">
					<button class="link" onclick={() => notifications.markAllRead()}>Mark read</button>
					<button class="link" onclick={() => notifications.clear()}>Clear</button>
				</div>
			</div>

			<div class="list">
				{#if notifications.loading && notifications.items.length === 0}
					<div class="empty">Loading…</div>
				{:else if notifications.items.length === 0}
					<div class="empty">No notifications yet.</div>
				{:else}
					{#each notifications.items as n (n.id)}
						<button
							class="row"
							class:unread={!n.read}
							onclick={() => {
								notifications.markRead(n.id);
								if (n.url) window.location.href = n.url;
							}}
						>
							<div class="row-main">
								<span class="row-title">{n.title}</span>
								{#if n.body}<span class="row-body">{n.body}</span>{/if}
							</div>
							<span class="row-time">{relative(n.created)}</span>
						</button>
					{/each}
				{/if}
			</div>

			<div class="panel-foot">
				{#if notifications.permission === 'unsupported'}
					<span class="muted">Push not supported on this browser.</span>
				{:else}
					<label class="push-toggle">
						<input
							type="checkbox"
							checked={notifications.pushEnabled}
							onchange={togglePush}
						/>
						<span>Background push on this device</span>
					</label>
				{/if}
				<button class="link" onclick={() => notifications.sendTest()}>Send test</button>
			</div>
		</div>
	{/if}
</div>

<style>
	.bell-wrap {
		position: relative;
	}
	.bell {
		position: relative;
		display: inline-flex;
		align-items: center;
		justify-content: center;
		width: 2rem;
		height: 2rem;
		border-radius: var(--radius-md);
		background: transparent;
		color: var(--muted);
		border: var(--border-width) solid transparent;
		cursor: pointer;
		transition: color 120ms ease, background 120ms ease;
	}
	.bell:hover {
		color: var(--fg);
		background: var(--surface);
	}
	.count {
		position: absolute;
		top: -2px;
		right: -2px;
		min-width: 1rem;
		height: 1rem;
		padding: 0 3px;
		font-size: 0.62rem;
		font-weight: var(--font-weight-bold);
		line-height: 1rem;
		text-align: center;
		color: var(--danger-fg);
		background: var(--danger);
		border-radius: var(--radius-full);
	}
	.backdrop {
		position: fixed;
		inset: 0;
		z-index: 40;
		background: transparent;
		border: none;
		cursor: default;
	}
	.panel {
		position: absolute;
		bottom: calc(100% + var(--space-2));
		right: 0;
		z-index: 50;
		width: 320px;
		max-width: 90vw;
		max-height: 60vh;
		display: flex;
		flex-direction: column;
		background: var(--surface-2);
		border: var(--border-width) solid var(--border-color);
		border-radius: var(--radius-lg);
		box-shadow: var(--shadow-lg, 0 8px 30px rgba(0, 0, 0, 0.25));
		overflow: hidden;
	}
	.panel-head,
	.panel-foot {
		display: flex;
		align-items: center;
		justify-content: space-between;
		gap: var(--space-2);
		padding: var(--space-2) var(--space-3);
	}
	.panel-head {
		border-bottom: var(--border-width) solid var(--border-color);
	}
	.panel-foot {
		border-top: var(--border-width) solid var(--border-color);
		flex-wrap: wrap;
	}
	.title {
		font-weight: var(--font-weight-bold);
		font-size: 0.9rem;
	}
	.head-actions {
		display: flex;
		gap: var(--space-2);
	}
	.link {
		background: none;
		border: none;
		color: var(--accent);
		font-size: 0.75rem;
		font-weight: var(--font-weight-bold);
		cursor: pointer;
		padding: 0;
	}
	.link:hover {
		text-decoration: underline;
	}
	.list {
		overflow-y: auto;
		flex: 1;
	}
	.empty {
		padding: var(--space-4);
		text-align: center;
		color: var(--muted);
		font-size: 0.85rem;
	}
	.row {
		display: flex;
		align-items: flex-start;
		justify-content: space-between;
		gap: var(--space-2);
		width: 100%;
		text-align: left;
		padding: var(--space-2) var(--space-3);
		background: none;
		border: none;
		border-bottom: var(--border-width) solid var(--border-color);
		cursor: pointer;
	}
	.row:hover {
		background: var(--surface);
	}
	.row.unread {
		background: color-mix(in srgb, var(--accent) 8%, transparent);
	}
	.row-main {
		display: flex;
		flex-direction: column;
		gap: 2px;
		min-width: 0;
	}
	.row-title {
		font-size: 0.85rem;
		font-weight: var(--font-weight-bold);
		color: var(--fg);
	}
	.row-body {
		font-size: 0.78rem;
		color: var(--muted);
		overflow: hidden;
		text-overflow: ellipsis;
		display: -webkit-box;
		-webkit-line-clamp: 2;
		line-clamp: 2;
		-webkit-box-orient: vertical;
	}
	.row-time {
		flex: none;
		font-size: 0.7rem;
		color: var(--muted);
	}
	.push-toggle {
		display: inline-flex;
		align-items: center;
		gap: var(--space-2);
		font-size: 0.75rem;
		color: var(--muted);
		cursor: pointer;
	}
	.muted {
		font-size: 0.75rem;
		color: var(--muted);
	}
</style>

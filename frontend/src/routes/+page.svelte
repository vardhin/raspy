<script lang="ts">
	// Dashboard: connection overview + cards linking to each backend app.
	import { goto } from '$app/navigation';
	import { onMount } from 'svelte';
	import { Surface, Stack, Text, Badge, Icon } from '$lib/components';
	import { manifest } from '$lib/manifest/store.svelte';
	import { connection, type LinkState } from '$lib/connection.svelte';
	import { stats } from '$lib/stats.svelte';

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

	const hasStats = $derived(manifest.attachments.some((a) => a.id === 'stats'));
	const snap = $derived(stats.latest);

	onMount(() => {
		stats.start(true);
	});

	function pctTone(p: number): 'success' | 'warn' | 'danger' {
		if (p >= 90) return 'danger';
		if (p >= 75) return 'warn';
		return 'success';
	}
	function tempTone(c: number): 'success' | 'warn' | 'danger' {
		if (c >= 80) return 'danger';
		if (c >= 70) return 'warn';
		return 'success';
	}
	function fmtUptime(s: number): string {
		const d = Math.floor(s / 86400);
		const h = Math.floor((s % 86400) / 3600);
		const m = Math.floor((s % 3600) / 60);
		if (d > 0) return `${d}d ${h}h`;
		if (h > 0) return `${h}h ${m}m`;
		return `${m}m`;
	}
</script>

<Stack gap={5}>
	<Stack gap={1}>
		<Text role="title">Dashboard</Text>
		<Text role="muted">Apps and status are served live from the backend.</Text>
	</Stack>

	<Surface level={2}>
		<Stack gap={3}>
			<Text role="heading">Connection</Text>
			<Stack direction="row" gap={2} wrap>
				<Badge variant={stateVariant[connection.http]}>API · {stateLabel[connection.http]}</Badge>
				<Badge variant={stateVariant[connection.ws]}>Live events · {stateLabel[connection.ws]}</Badge>
				{#if connection.version}
					<Badge variant="info">v{connection.version}</Badge>
				{/if}
				<Badge>{manifest.attachments.length} apps</Badge>
				{#if connection.erroredCount}
					<Badge variant="danger">{connection.erroredCount} failed</Badge>
				{/if}
			</Stack>
		</Stack>
	</Surface>

	{#if hasStats}
		<Surface level={2} interactive onclick={() => goto('/a/stats')}>
			<Stack gap={3}>
				<Stack direction="row" gap={2} align="center" justify="between">
					<Stack direction="row" gap={2} align="center">
						<span class="ico"><Icon name="activity" size={18} /></span>
						<Text role="heading">Pi health</Text>
					</Stack>
					{#if snap?.throttle}
						{#if snap.throttle.ok}
							<Badge variant="success">Healthy</Badge>
						{:else if snap.throttle.active.length}
							<Badge variant="danger">{snap.throttle.active[0]}</Badge>
						{:else}
							<Badge variant="warn">Past warning</Badge>
						{/if}
					{/if}
				</Stack>
				{#if snap}
					<div class="statline">
						{#if snap.temp_c != null}
							<span class="stat">
								<Icon name="thermometer" size={15} />
								<b style:color={`var(--${tempTone(snap.temp_c)})`}>{snap.temp_c}°C</b>
							</span>
						{/if}
						{#if snap.cpu_percent != null}
							<span class="stat">
								<Icon name="cpu" size={15} />
								<b style:color={`var(--${pctTone(snap.cpu_percent)})`}>{snap.cpu_percent}%</b> CPU
							</span>
						{/if}
						{#if snap.memory}
							<span class="stat">
								<Icon name="memory-stick" size={15} />
								<b style:color={`var(--${pctTone(snap.memory.percent)})`}>{snap.memory.percent}%</b> RAM
							</span>
						{/if}
						{#if snap.storage?.[0]}
							<span class="stat">
								<Icon name="hard-drive" size={15} />
								<b style:color={`var(--${pctTone(snap.storage[0].percent)})`}>{snap.storage[0].percent}%</b> disk
							</span>
						{/if}
						{#if snap.uptime != null}
							<span class="stat"><Icon name="clock" size={15} /> {fmtUptime(snap.uptime)}</span>
						{/if}
					</div>
				{:else}
					<Text role="muted">Reading system…</Text>
				{/if}
			</Stack>
		</Surface>
	{/if}

	<Stack gap={3}>
		<Text role="heading">Apps</Text>
		{#if manifest.attachments.length === 0}
			<Text role="muted">
				{manifest.loading ? 'Loading apps…' : 'No apps available from the backend.'}
			</Text>
		{:else}
			<div class="grid">
				{#each manifest.attachments as app (app.id)}
					<Surface interactive onclick={() => goto(`/a/${app.id}`)}>
						<Stack direction="row" gap={3} align="center">
							<span class="ico"><Icon name={app.icon} size={22} /></span>
							<Stack gap={1}>
								<Text role="label">{app.title}</Text>
							</Stack>
						</Stack>
					</Surface>
				{/each}
			</div>
		{/if}
	</Stack>
</Stack>

<style>
	.grid {
		display: grid;
		grid-template-columns: repeat(auto-fill, minmax(200px, 1fr));
		gap: var(--space-3);
	}
	.ico {
		display: inline-flex;
		color: var(--accent);
	}
	.statline {
		display: flex;
		flex-wrap: wrap;
		gap: var(--space-4);
		align-items: center;
	}
	.stat {
		display: inline-flex;
		align-items: center;
		gap: var(--space-1);
		color: var(--muted);
		font-size: 0.92rem;
	}
	.stat b {
		font-weight: var(--font-weight-bold);
		color: var(--fg);
	}
</style>

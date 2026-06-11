<script lang="ts">
	// Live system-health dashboard for the `system_stats` node. Fetches one snapshot
	// for first paint, then updates from `stats.tick` WebSocket events. Token-only,
	// so it re-skins with any theme. Missing metrics (e.g. no vcgencmd off-Pi) are
	// simply hidden.
	import { onMount, onDestroy } from 'svelte';
	import { Surface, Stack, Text, Badge, Icon } from '$lib/components';
	import { connection } from '$lib/connection.svelte';
	import { stats } from '$lib/stats.svelte';
	import type { UINode } from '$lib/manifest/types';

	// node prop kept for renderer symmetry; this component reads the shared store.
	let { node: _node }: { node: UINode } = $props();

	const snap = $derived(stats.latest);
	let loading = $state(true);

	// --- formatting helpers ---
	function fmtBytes(n: number): string {
		if (n <= 0) return '0 B';
		const u = ['B', 'KB', 'MB', 'GB', 'TB'];
		let v = n;
		let i = 0;
		while (v >= 1024 && i < u.length - 1) {
			v /= 1024;
			i++;
		}
		return `${v.toFixed(v < 10 && i > 0 ? 1 : 0)} ${u[i]}`;
	}
	function fmtUptime(s: number): string {
		const d = Math.floor(s / 86400);
		const h = Math.floor((s % 86400) / 3600);
		const m = Math.floor((s % 3600) / 60);
		if (d > 0) return `${d}d ${h}h ${m}m`;
		if (h > 0) return `${h}h ${m}m`;
		return `${m}m`;
	}
	function tempTone(c: number): 'success' | 'warn' | 'danger' {
		if (c >= 80) return 'danger';
		if (c >= 70) return 'warn';
		return 'success';
	}
	function pctTone(p: number): 'success' | 'warn' | 'danger' {
		if (p >= 90) return 'danger';
		if (p >= 75) return 'warn';
		return 'success';
	}
	const toneVar: Record<'success' | 'warn' | 'danger', string> = {
		success: 'var(--success)',
		warn: 'var(--warn)',
		danger: 'var(--danger)'
	};

	onMount(() => {
		stats.start(true); // subscribe to ticks + fetch one snapshot now
		void stats.refresh().finally(() => (loading = false));
	});
	onDestroy(() => {
		// Leave the shared store running for the dashboard strip; nothing to do.
	});
</script>

{#if loading && !snap}
	<Text role="muted">Reading system…</Text>
{:else if snap}
	<Stack gap={4}>
		<!-- Identity + health banner -->
		<Surface level={2}>
			<Stack direction="row" gap={3} align="center" justify="between" wrap>
				<Stack gap={1}>
					<Text role="label">{snap.model ?? 'System'}</Text>
					{#if snap.uptime != null}
						<Text role="muted">Up {fmtUptime(snap.uptime)} · {snap.cpu_count} cores</Text>
					{/if}
				</Stack>
				{#if snap.throttle}
					{#if snap.throttle.ok}
						<Badge variant="success"><Icon name="check" size={13} /> Healthy</Badge>
					{:else if snap.throttle.active.length}
						<Badge variant="danger"><Icon name="alert-triangle" size={13} /> {snap.throttle.active[0]}</Badge>
					{:else}
						<Badge variant="warn"><Icon name="alert-triangle" size={13} /> Past warning</Badge>
					{/if}
				{/if}
			</Stack>
			{#if snap.throttle && !snap.throttle.ok}
				<Stack gap={1}>
					{#each snap.throttle.active as msg (msg)}
						<Text role="muted">⚠ {msg}</Text>
					{/each}
					{#each snap.throttle.occurred as msg (msg)}
						<Text role="muted">• {msg} (since boot)</Text>
					{/each}
				</Stack>
			{/if}
		</Surface>

		<!-- Metric cards -->
		<div class="cards">
			{#if snap.temp_c != null}
				<Surface>
					<Stack gap={2}>
						<div class="ch"><Icon name="thermometer" size={16} /> <Text role="label">Temperature</Text></div>
						<div class="big" style:color={toneVar[tempTone(snap.temp_c)]}>{snap.temp_c}°C</div>
						<div class="bar"><span style:width="{Math.min(100, (snap.temp_c / 90) * 100)}%" style:background={toneVar[tempTone(snap.temp_c)]}></span></div>
					</Stack>
				</Surface>
			{/if}

			{#if snap.cpu_percent != null}
				<Surface>
					<Stack gap={2}>
						<div class="ch"><Icon name="cpu" size={16} /> <Text role="label">CPU</Text></div>
						<div class="big" style:color={toneVar[pctTone(snap.cpu_percent)]}>{snap.cpu_percent}%</div>
						<div class="bar"><span style:width="{snap.cpu_percent}%" style:background={toneVar[pctTone(snap.cpu_percent)]}></span></div>
						{#if snap.load}
							<Text role="muted">load {snap.load.map((l) => l.toFixed(2)).join(' · ')}</Text>
						{/if}
						{#if snap.arm_hz}
							<Text role="muted">{(snap.arm_hz / 1e9).toFixed(2)} GHz</Text>
						{/if}
					</Stack>
				</Surface>
			{/if}

			{#if snap.memory}
				<Surface>
					<Stack gap={2}>
						<div class="ch"><Icon name="memory-stick" size={16} /> <Text role="label">Memory</Text></div>
						<div class="big" style:color={toneVar[pctTone(snap.memory.percent)]}>{snap.memory.percent}%</div>
						<div class="bar"><span style:width="{snap.memory.percent}%" style:background={toneVar[pctTone(snap.memory.percent)]}></span></div>
						<Text role="muted">{fmtBytes(snap.memory.used)} / {fmtBytes(snap.memory.total)}</Text>
						{#if snap.memory.swap_total > 0}
							<Text role="muted">swap {fmtBytes(snap.memory.swap_used)} / {fmtBytes(snap.memory.swap_total)}</Text>
						{/if}
					</Stack>
				</Surface>
			{/if}

			{#if snap.voltage_v != null}
				<Surface>
					<Stack gap={2}>
						<div class="ch"><Icon name="zap" size={16} /> <Text role="label">Core voltage</Text></div>
						<div class="big">{snap.voltage_v.toFixed(3)} V</div>
					</Stack>
				</Surface>
			{/if}

			{#if snap.uptime != null}
				<Surface>
					<Stack gap={2}>
						<div class="ch"><Icon name="clock" size={16} /> <Text role="label">Uptime</Text></div>
						<div class="big">{fmtUptime(snap.uptime)}</div>
					</Stack>
				</Surface>
			{/if}
		</div>

		<!-- Storage -->
		{#if snap.storage.length}
			<Surface>
				<Stack gap={3}>
					<div class="ch"><Icon name="hard-drive" size={16} /> <Text role="heading">Storage</Text></div>
					{#each snap.storage as disk (disk.mount)}
						<Stack gap={1}>
							<Stack direction="row" gap={2} justify="between" align="center">
								<Text role="label">{disk.mount}</Text>
								<Text role="muted">{fmtBytes(disk.used)} / {fmtBytes(disk.total)} ({disk.percent}%)</Text>
							</Stack>
							<div class="bar"><span style:width="{disk.percent}%" style:background={toneVar[pctTone(disk.percent)]}></span></div>
						</Stack>
					{/each}
				</Stack>
			</Surface>
		{/if}

		<Text role="muted">
			Live · updates every few seconds {connection.ws === 'online' ? '' : '(reconnecting…)'}
		</Text>
	</Stack>
{/if}

<style>
	.cards {
		display: grid;
		grid-template-columns: repeat(auto-fill, minmax(190px, 1fr));
		gap: var(--space-3);
	}
	.ch {
		display: flex;
		align-items: center;
		gap: var(--space-2);
		color: var(--muted);
	}
	.big {
		font-size: 1.8rem;
		font-weight: var(--font-weight-bold);
		line-height: 1;
	}
	.bar {
		height: 6px;
		width: 100%;
		background: var(--surface-2);
		border-radius: var(--radius-full);
		overflow: hidden;
	}
	.bar span {
		display: block;
		height: 100%;
		border-radius: var(--radius-full);
		transition: width var(--motion-base) var(--motion-ease);
	}
</style>

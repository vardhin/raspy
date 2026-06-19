<script lang="ts">
	// Admin-only self-update app. Drives the core updater endpoints
	// (/api/update/*): shows the current version, checks for updates, lists every
	// published GitHub release with its notes, and installs ANY version — upgrade
	// or rollback — via the shared `update` store (download + verify + swap +
	// restart). Also toggles the periodic auto-check. All endpoints are admin-gated
	// server-side; a non-admin never sees this app (manifest _ADMIN_ONLY).
	import { onMount } from 'svelte';
	import { Surface, Stack, Text, Button, Icon, Switch, Field } from '$lib/components';
	import { apiGet, apiPut } from '$lib/api';
	import { update } from '$lib/update/store.svelte';

	type Release = {
		tag: string;
		version: string;
		name: string;
		notes: string;
		published_at: string | null;
		prerelease: boolean;
		installable: boolean;
		is_current: boolean;
		is_newer: boolean;
	};
	type ReleasesResp = {
		current: string;
		updatable: boolean;
		asset: string | null;
		releases: Release[];
		reason: string | null;
	};
	type AutoCheck = { enabled: boolean; interval_s: number };

	let data = $state<ReleasesResp | null>(null);
	let loading = $state(true);
	let listError = $state<string | null>(null);
	let auto = $state<AutoCheck>({ enabled: true, interval_s: 6 * 60 * 60 });
	let expanded = $state<string | null>(null); // tag whose notes are open
	let pendingTag = $state<string | null>(null); // tag the user is confirming
	let savingAuto = $state(false);

	// Common interval presets (hours) for the auto-check picker.
	const INTERVALS = [
		{ value: String(60 * 60), label: 'Every hour' },
		{ value: String(6 * 60 * 60), label: 'Every 6 hours' },
		{ value: String(24 * 60 * 60), label: 'Daily' },
		{ value: String(7 * 24 * 60 * 60), label: 'Weekly' }
	];

	async function loadReleases() {
		loading = true;
		listError = null;
		try {
			data = await apiGet<ReleasesResp>('/api/update/releases');
		} catch (e) {
			listError = e instanceof Error ? e.message : 'failed to load releases';
		} finally {
			loading = false;
		}
	}

	async function loadAuto() {
		try {
			auto = await apiGet<AutoCheck>('/api/update/autocheck');
		} catch {
			/* keep defaults */
		}
	}

	async function saveAuto(next: AutoCheck) {
		savingAuto = true;
		try {
			auto = await apiPut<AutoCheck>('/api/update/autocheck', next);
		} catch {
			/* leave UI as-is on failure */
		} finally {
			savingAuto = false;
		}
	}

	async function checkNow() {
		await Promise.all([update.refresh(), loadReleases()]);
	}

	function relationLabel(r: Release): string {
		if (r.is_current) return 'Installed';
		if (r.is_newer) return 'Newer';
		return 'Older';
	}

	function fmtDate(iso: string | null): string {
		if (!iso) return '';
		try {
			return new Date(iso).toLocaleDateString(undefined, {
				year: 'numeric',
				month: 'short',
				day: 'numeric'
			});
		} catch {
			return '';
		}
	}

	// Apply a specific version. Older versions (rollback) require a confirm step.
	async function install(r: Release) {
		if (!r.is_current && !r.is_newer && pendingTag !== r.tag) {
			pendingTag = r.tag; // first click on a downgrade → ask to confirm
			return;
		}
		pendingTag = null;
		await update.apply(r.tag);
	}

	const applying = $derived(update.phase === 'applying' || update.phase === 'restarting');

	onMount(() => {
		void loadReleases();
		void loadAuto();
		void update.refresh();
	});
</script>

<div class="updates">
	<!-- Current state + check -->
	<Surface level={2}>
		<Stack gap={3}>
			<div class="head">
				<div>
					<Text role="label">Current version</Text>
					<div class="cur">
						<Icon name="check-square" size={18} />
						<span class="ver">{data?.current ?? update.current ?? '—'}</span>
					</div>
				</div>
				<Button onclick={checkNow} disabled={update.phase === 'checking'}>
					<Icon name="refresh-cw" size={16} />
					{update.phase === 'checking' ? 'Checking…' : 'Check now'}
				</Button>
			</div>

			{#if data && !data.updatable}
				<div class="note warn">
					<Icon name="alert-triangle" size={16} />
					<Text role="muted">
						This build can't self-update ({data.reason ?? 'not updatable'}). Installs are
						disabled.
					</Text>
				</div>
			{:else if update.available && update.latest}
				<div class="note ok">
					<Icon name="sparkles" size={16} />
					<Text role="body">Update available: <strong>{update.latest}</strong></Text>
				</div>
			{:else if data}
				<Text role="muted">You're on the latest version.</Text>
			{/if}

			{#if update.phase === 'restarting'}
				<div class="note ok">
					<Icon name="refresh-cw" size={16} />
					<Text role="body">Installing & restarting… this page will reconnect shortly.</Text>
				</div>
			{:else if update.phase === 'error' && update.error}
				<div class="note warn">
					<Icon name="alert-triangle" size={16} />
					<Text role="body">{update.error}</Text>
				</div>
			{/if}
		</Stack>
	</Surface>

	<!-- Auto-check -->
	<Surface level={2}>
		<Stack gap={3}>
			<div class="head">
				<div>
					<Text role="label">Automatic checks</Text>
					<Text role="muted">Periodically check GitHub and notify when an update lands.</Text>
				</div>
				<Switch
					checked={auto.enabled}
					disabled={savingAuto}
					onchange={(v: boolean) => saveAuto({ enabled: v, interval_s: auto.interval_s })}
				/>
			</div>
			{#if auto.enabled}
				<Field
					type="select"
					label="Check frequency"
					options={INTERVALS}
					value={String(auto.interval_s)}
					onchange={(e: Event) =>
						saveAuto({
							enabled: true,
							interval_s: Number((e.target as HTMLSelectElement).value)
						})}
				/>
			{/if}
		</Stack>
	</Surface>

	<!-- Release picker -->
	<Stack gap={2}>
		<Text role="heading">All versions</Text>
		{#if loading && !data}
			<Text role="muted">Loading releases…</Text>
		{:else if listError}
			<Surface level={2}>
				<Stack gap={2} align="center">
					<Icon name="alert-triangle" size={22} />
					<Text role="muted">{listError}</Text>
					<Button onclick={loadReleases}>Try again</Button>
				</Stack>
			</Surface>
		{:else if data && data.releases.length === 0}
			<Text role="muted">No published releases found.</Text>
		{:else if data}
			{#each data.releases as r (r.tag)}
				<Surface level={1} interactive={!r.is_current}>
					<Stack gap={2}>
						<div class="rel-head">
							<div class="rel-id">
								<span class="rel-ver">{r.version}</span>
								<span
									class="rel-tag"
									class:cur={r.is_current}
									class:newer={r.is_newer}
									class:older={!r.is_current && !r.is_newer}
								>
									{relationLabel(r)}
								</span>
								{#if r.prerelease}<span class="rel-tag pre">Pre-release</span>{/if}
								<span class="rel-date">{fmtDate(r.published_at)}</span>
							</div>
							<div class="rel-actions">
								{#if r.notes}
									<Button
										variant="ghost"
										size="sm"
										onclick={() => (expanded = expanded === r.tag ? null : r.tag)}
									>
										<Icon name={expanded === r.tag ? 'chevron-up' : 'chevron-down'} size={16} />
										Notes
									</Button>
								{/if}
								{#if r.is_current}
									<Button variant="ghost" size="sm" disabled>Installed</Button>
								{:else if !r.installable}
									<Button variant="ghost" size="sm" disabled>No build</Button>
								{:else if pendingTag === r.tag}
									<Button variant="danger" size="sm" disabled={applying} onclick={() => install(r)}>
										Confirm {r.is_newer ? 'install' : 'rollback'}
									</Button>
									<Button variant="ghost" size="sm" onclick={() => (pendingTag = null)}>
										Cancel
									</Button>
								{:else}
									<Button
										variant={r.is_newer ? 'accent' : 'neutral'}
										size="sm"
										disabled={applying}
										onclick={() => install(r)}
									>
										<Icon name="download" size={15} />
										{r.is_newer ? 'Install' : 'Roll back'}
									</Button>
								{/if}
							</div>
						</div>
						{#if expanded === r.tag && r.notes}
							<pre class="notes">{r.notes}</pre>
						{/if}
					</Stack>
				</Surface>
			{/each}
		{/if}
	</Stack>
</div>

<style>
	.updates {
		display: flex;
		flex-direction: column;
		gap: var(--space-4);
		width: min(720px, 100%);
		margin: 0 auto;
	}
	.head {
		display: flex;
		align-items: flex-start;
		justify-content: space-between;
		gap: var(--space-3);
		flex-wrap: wrap;
	}
	.cur {
		display: inline-flex;
		align-items: center;
		gap: var(--space-2);
		margin-top: var(--space-1);
	}
	.ver {
		font-size: 1.4rem;
		font-weight: var(--font-weight-bold);
		font-variant-numeric: tabular-nums;
	}
	.note {
		display: flex;
		align-items: center;
		gap: var(--space-2);
		padding: var(--space-2) var(--space-3);
		border-radius: var(--radius-md);
		border: var(--border-width) solid var(--border-color);
	}
	.note.ok {
		background: color-mix(in srgb, var(--success) 16%, transparent);
		border-color: color-mix(in srgb, var(--success) 45%, var(--border-color));
	}
	.note.warn {
		background: color-mix(in srgb, var(--warn) 16%, transparent);
		border-color: color-mix(in srgb, var(--warn) 45%, var(--border-color));
	}
	.rel-head {
		display: flex;
		align-items: center;
		justify-content: space-between;
		gap: var(--space-3);
		flex-wrap: wrap;
	}
	.rel-id {
		display: flex;
		align-items: center;
		gap: var(--space-2);
		flex-wrap: wrap;
	}
	.rel-ver {
		font-weight: var(--font-weight-bold);
		font-size: 1.05rem;
		font-variant-numeric: tabular-nums;
	}
	.rel-tag {
		font-size: 0.72rem;
		text-transform: uppercase;
		letter-spacing: 0.08em;
		padding: 2px var(--space-2);
		border-radius: var(--radius-full);
		border: var(--border-width) solid var(--border-color);
		color: var(--muted);
	}
	.rel-tag.cur {
		color: var(--success);
		border-color: color-mix(in srgb, var(--success) 50%, var(--border-color));
	}
	.rel-tag.newer {
		color: var(--accent);
		border-color: color-mix(in srgb, var(--accent) 50%, var(--border-color));
	}
	.rel-tag.pre {
		color: var(--warn);
		border-color: color-mix(in srgb, var(--warn) 50%, var(--border-color));
	}
	.rel-date {
		color: var(--muted);
		font-size: 0.85rem;
	}
	.rel-actions {
		display: flex;
		gap: var(--space-2);
		align-items: center;
		flex-wrap: wrap;
	}
	.notes {
		margin: 0;
		padding: var(--space-3);
		border-radius: var(--radius-md);
		background: color-mix(in srgb, var(--surface-2) calc(var(--surface-alpha) * 100%), transparent);
		border: var(--border-width) solid var(--border-color);
		white-space: pre-wrap;
		word-break: break-word;
		font-size: 0.85rem;
		line-height: 1.5;
		max-height: 22rem;
		overflow-y: auto;
	}
</style>

<script lang="ts">
	// Dashboard: connection overview + cards linking to each backend app.
	import { goto } from '$app/navigation';
	import { Surface, Stack, Text, Badge, Icon } from '$lib/components';
	import { manifest } from '$lib/manifest/store.svelte';
	import { connection, type LinkState } from '$lib/connection.svelte';

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
				<Badge>{connection.attachmentCount} apps</Badge>
				{#if connection.erroredCount}
					<Badge variant="danger">{connection.erroredCount} failed</Badge>
				{/if}
			</Stack>
		</Stack>
	</Surface>

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
								<Text role="muted">v{app.version}</Text>
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
</style>

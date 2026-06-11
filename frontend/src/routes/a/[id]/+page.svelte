<script lang="ts">
	// Generic app screen: looks up the attachment by route id in the cached manifest
	// and renders its declarative UI. No per-app code — adding an app to the backend
	// makes it appear here automatically.
	import { page } from '$app/state';
	import { AppView } from '$lib/renderer';
	import { Text, Stack } from '$lib/components';
	import { manifest } from '$lib/manifest/store.svelte';

	const app = $derived(manifest.byId(page.params.id ?? ''));
</script>

{#if app}
	{#key app.id}
		<AppView {app} />
	{/key}
{:else if manifest.loading}
	<Text role="muted">Loading…</Text>
{:else}
	<Stack gap={2}>
		<Text role="title">Not found</Text>
		<Text role="muted">No app “{page.params.id}” is installed on the backend.</Text>
	</Stack>
{/if}

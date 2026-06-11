<script lang="ts">
	// Mounts one attachment's declarative UI. Creates a RenderContext, walks the
	// tree to discover every `list`/`table` data source and loads them, then renders
	// the node tree. Re-keys on attachment id so switching apps fully resets state.
	import { setContext, onDestroy } from 'svelte';
	import Node from './Node.svelte';
	import { RenderContext } from './context.svelte';
	import { Text, Stack, Badge } from '$lib/components';
	import type { AttachmentManifest, UINode } from '$lib/manifest/types';

	let { app }: { app: AttachmentManifest } = $props();

	const ctx = new RenderContext(app.id);
	setContext('render', ctx);

	function collectSources(node: UINode | null | undefined, out: Set<string>): void {
		if (!node) return;
		if ((node.type === 'list' || node.type === 'table') && node.source) out.add(node.source);
		for (const child of node.children ?? []) collectSources(child, out);
		if (node.item) collectSources(node.item, out);
	}

	$effect(() => {
		const ui = app.ui;
		const sources = new Set<string>();
		collectSources(ui, sources);
		for (const path of sources) void ctx.registerSource(path);
	});

	onDestroy(() => ctx.destroy());
</script>

{#if app.ui}
	<Stack gap={4}>
		{#if app.ui.title}
			<Stack direction="row" gap={2} align="center">
				<Text role="title">{app.ui.title}</Text>
				{#if ctx.stale}
					<span title="Backend unreachable — showing the last data saved on this device.">
						<Badge variant="warn">Offline · saved data</Badge>
					</span>
				{/if}
			</Stack>
		{/if}
		{#each app.ui.children ?? [] as child, i (i)}
			<Node node={child} />
		{/each}
	</Stack>
{:else}
	<Text role="muted">This app has no UI.</Text>
{/if}

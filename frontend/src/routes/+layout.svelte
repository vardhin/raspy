<script lang="ts">
	import '../app.css';
	import favicon from '$lib/assets/favicon.svg';
	import { onMount, onDestroy } from 'svelte';
	import { theme } from '$lib/themes/store.svelte';
	import { connection } from '$lib/connection.svelte';
	import { manifest } from '$lib/manifest/store.svelte';
	import { Sidebar } from '$lib/components';

	let { children } = $props();

	// App-lifetime setup. This MUST live in onMount/onDestroy, not $effect: the
	// connection (and its WebSocket) is a session singleton, so it should start
	// once and never be torn down because some reactive dependency re-ran the
	// effect — that was closing the freshly-opened socket mid-handshake and
	// leaving the badge stuck on "connecting".
	onMount(() => {
		theme.init();
		manifest.load();
		connection.start();
	});

	// Revalidate the manifest whenever the WS reconnects after a drop.
	const offReconnect = connection.onReconnect(() => manifest.revalidate());

	onDestroy(() => {
		offReconnect();
		connection.stop();
	});
</script>

<svelte:head>
	<link rel="icon" href={favicon} />
</svelte:head>

<div class="shell">
	<Sidebar />
	<main class="content">
		{@render children()}
	</main>
</div>

<style>
	.shell {
		display: flex;
		align-items: flex-start;
		min-height: 100dvh;
	}
	.content {
		flex: 1;
		min-width: 0;
		max-width: 920px;
		margin: 0 auto;
		padding: var(--space-6) var(--space-5);
	}
	@media (max-width: 720px) {
		.shell {
			flex-direction: column;
		}
		.content {
			width: 100%;
			padding: var(--space-4);
		}
	}
</style>

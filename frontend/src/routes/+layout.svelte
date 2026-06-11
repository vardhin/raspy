<script lang="ts">
	import '../app.css';
	import favicon from '$lib/assets/favicon.svg';
	import { theme } from '$lib/themes/store.svelte';

	let { children } = $props();

	// Apply the persisted/default theme tokens once the app mounts. The inline
	// script in app.html already seeded data-mode/color/concept to avoid a flash.
	$effect(() => {
		theme.init();
	});
</script>

<svelte:head>
	<link rel="icon" href={favicon} />
</svelte:head>

{@render children()}

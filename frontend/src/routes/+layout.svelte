<script lang="ts">
	import '../app.css';
	import favicon from '$lib/assets/favicon.svg';
	import { onMount, onDestroy } from 'svelte';
	import { afterNavigate } from '$app/navigation';
	import { theme } from '$lib/themes/store.svelte';
	import { connection } from '$lib/connection.svelte';
	import { manifest } from '$lib/manifest/store.svelte';
	import { notifications } from '$lib/notifications/store.svelte';
	import { Sidebar, Icon } from '$lib/components';

	let { children } = $props();

	// Mobile off-canvas drawer state. The sidebar is always in the DOM; on mobile a
	// CSS transform slides it off-screen until `drawerOpen` is set. It auto-closes on
	// navigation (afterNavigate) and on the link taps inside the sidebar (onClose).
	let drawerOpen = $state(false);
	const closeDrawer = () => (drawerOpen = false);

	afterNavigate(() => {
		drawerOpen = false;
	});

	// App-lifetime setup. This MUST live in onMount/onDestroy, not $effect: the
	// connection (and its WebSocket) is a session singleton, so it should start
	// once and never be torn down because some reactive dependency re-ran the
	// effect — that was closing the freshly-opened socket mid-handshake and
	// leaving the badge stuck on "connecting".
	onMount(() => {
		theme.init();
		manifest.load();
		connection.start();
		// Start after connection: the store subscribes to WS notification events.
		notifications.start();
	});

	// Revalidate the manifest whenever the WS reconnects after a drop, and refetch
	// any notifications we missed while offline.
	const offReconnect = connection.onReconnect(() => {
		manifest.revalidate();
		notifications.refresh();
	});

	onDestroy(() => {
		offReconnect();
		notifications.stop();
		connection.stop();
	});

	// Prevent the page behind the drawer from scrolling while it's open.
	$effect(() => {
		if (typeof document === 'undefined') return;
		document.body.style.overflow = drawerOpen ? 'hidden' : '';
		return () => {
			document.body.style.overflow = '';
		};
	});
</script>

<svelte:head>
	<link rel="icon" href={favicon} />
</svelte:head>

<div class="shell" class:drawer-open={drawerOpen}>
	<!-- Mobile-only top bar with the hamburger. Hidden at desktop widths. -->
	<header class="topbar">
		<button class="hamburger" aria-label="Open menu" aria-expanded={drawerOpen} onclick={() => (drawerOpen = true)}>
			<Icon name="menu" size={22} />
		</button>
		<span class="topbar-title">Raspy</span>
	</header>

	<!-- Tap-to-dismiss scrim, only interactive while the drawer is open. -->
	<button
		class="scrim"
		aria-label="Close menu"
		tabindex={drawerOpen ? 0 : -1}
		onclick={closeDrawer}
	></button>

	<div class="drawer">
		<Sidebar onClose={closeDrawer} />
	</div>

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

	/* Desktop: drawer is just the static sidebar column; the mobile chrome
	   (top bar + scrim) is hidden. */
	.drawer {
		flex: none;
	}
	.topbar,
	.scrim {
		display: none;
	}

	@media (max-width: 720px) {
		.shell {
			flex-direction: column;
		}

		/* Sticky mobile header carrying the hamburger. */
		.topbar {
			display: flex;
			align-items: center;
			gap: var(--space-2);
			position: sticky;
			top: 0;
			z-index: 30;
			width: 100%;
			padding: var(--space-2) var(--space-3);
			background: color-mix(
				in srgb,
				var(--surface-2) calc(var(--surface-alpha, 1) * 100%),
				transparent
			);
			backdrop-filter: blur(var(--blur));
			-webkit-backdrop-filter: blur(var(--blur));
			border-bottom: var(--border-width) solid var(--border-color);
		}
		.hamburger {
			display: inline-flex;
			align-items: center;
			justify-content: center;
			padding: var(--space-2);
			background: transparent;
			color: var(--fg);
			border: none;
			border-radius: var(--radius-md);
			cursor: pointer;
		}
		.hamburger:active {
			background: var(--surface);
		}
		.topbar-title {
			font-weight: var(--font-weight-bold);
			font-size: 1.05rem;
		}

		/* Off-canvas drawer: fixed, slides in from the left. */
		.drawer {
			position: fixed;
			top: 0;
			left: 0;
			z-index: 50;
			height: 100dvh;
			width: min(82vw, 300px);
			transform: translateX(-100%);
			transition: transform var(--motion-base, 220ms) var(--motion-ease, ease);
			box-shadow: var(--shadow-lg);
			will-change: transform;
		}
		.drawer-open .drawer {
			transform: translateX(0);
		}

		/* Dimming scrim behind the open drawer. */
		.scrim {
			display: block;
			position: fixed;
			inset: 0;
			z-index: 40;
			border: none;
			padding: 0;
			background: var(--overlay, rgba(0, 0, 0, 0.5));
			opacity: 0;
			pointer-events: none;
			cursor: pointer;
			transition: opacity var(--motion-base, 220ms) var(--motion-ease, ease);
		}
		.drawer-open .scrim {
			opacity: 1;
			pointer-events: auto;
		}

		.content {
			width: 100%;
			padding: var(--space-4);
		}
	}
</style>

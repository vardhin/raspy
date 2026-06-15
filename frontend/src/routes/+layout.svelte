<script lang="ts">
	import '../app.css';
	import favicon from '$lib/assets/favicon.svg';
	import { onMount, onDestroy } from 'svelte';
	import { afterNavigate } from '$app/navigation';
	import { theme } from '$lib/themes/store.svelte';
	import { connection } from '$lib/connection.svelte';
	import { manifest } from '$lib/manifest/store.svelte';
	import { notifications } from '$lib/notifications/store.svelte';
	import { Sidebar, Icon, PasswordLogin, PinUnlock, AccountSetup } from '$lib/components';
	import { auth } from '$lib/auth.svelte';
	import { setAuthLostHandler } from '$lib/api';

	let { children } = $props();

	// Route 401s (after a failed silent refresh) back into the gate.
	setAuthLostHandler((needs) => auth.onAuthLost(needs));

	// Lazily start the live services the first time we become authenticated, and
	// only once. They must not start before auth (the WS would be rejected 1008).
	let servicesStarted = false;
	function startServicesOnce() {
		if (servicesStarted) return;
		servicesStarted = true;
		connection.start();
		notifications.start();
	}
	let manifestUser: string | null = null;

	// When the tab regains focus, re-check the session: if the access token
	// lapsed while we were away, this flips us to the PIN screen ("out of focus →
	// mini PIN"). Only meaningful while we believe we're active.
	function onVisible() {
		if (typeof document === 'undefined') return;
		if (document.visibilityState === 'visible' && auth.state === 'active') {
			void auth.refresh();
		}
	}

	$effect(() => {
		if (auth.state === 'active') {
			startServicesOnce();
			if (auth.username !== manifestUser) {
				manifestUser = auth.username;
				void manifest.load(auth.username ?? 'default');
				notifications.refresh();
			}
		} else if (auth.state === 'password') {
			manifestUser = null;
		}
	});

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
		// Ask the server what to show (active / pin / password). Services start
		// only once we reach 'active' (see the $effect above).
		void auth.refresh();
		document.addEventListener('visibilitychange', onVisible);
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
		if (typeof document !== 'undefined') {
			document.removeEventListener('visibilitychange', onVisible);
		}
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

{#if auth.state === 'loading'}
	<div class="gate-loading"></div>
{:else if auth.state === 'password'}
	<PasswordLogin />
{:else if auth.state === 'pin'}
	<PinUnlock />
{:else if auth.state === 'reset'}
	<AccountSetup />
{:else}
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
		<div class="content-inner">
			{@render children()}
		</div>
	</main>
</div>
{/if}

<style>
	.gate-loading {
		min-height: 100dvh;
	}
	.shell {
		display: flex;
		align-items: flex-start;
		/* Pin the shell to the viewport so the sidebar column never scrolls with
		   the page; only .content scrolls (see overflow-y below). */
		height: 100dvh;
		overflow: hidden;
	}
	.content {
		flex: 1;
		min-width: 0;
		height: 100%;
		overflow-y: auto;
		padding: var(--space-6) var(--space-5);
	}
	/* Inner wrapper keeps the content centred at its max width while .content
	   itself owns the full-height scroll region. */
	.content-inner {
		max-width: 920px;
		margin: 0 auto;
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
			/* On mobile the sidebar is an off-canvas drawer, so the shell scrolls
			   as a normal page (sticky topbar + scrolling content). */
			height: auto;
			min-height: 100dvh;
			overflow: visible;
		}
		.content {
			height: auto;
			overflow-y: visible;
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

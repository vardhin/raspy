<script lang="ts">
	// Vibe of the Day — a magical daily image + quote. The backend fetches a fresh
	// image + quote per day from keyless public providers (cached to disk) and a
	// random Google display font per day (cached locally on the Pi). This view
	// renders it: a sparkly star field, the page tinted by an image-derived accent,
	// the quote set in the day's font. "Fetch now" forces a fresh pick.
	import { onMount } from 'svelte';
	import { Surface, Stack, Text, Button, Icon, StarField } from '$lib/components';
	import { attGet, attAction, attResourceUrl } from '$lib/api';
	import { connection } from '$lib/connection.svelte';

	type Vibe = {
		date: string;
		image_url: string; // relative to the attachment, e.g. "image/2026-06-15"
		accent: string;
		quote: string;
		author: string;
		font: string;
		rev: number; // fetch timestamp; busts the <img> cache on a manual refresh
	};

	const ID = 'vibe';

	let vibe = $state<Vibe | null>(null);
	let loading = $state(true);
	let refreshing = $state(false);
	let error = $state<string | null>(null);

	// Absolute image URL (same-origin GET → cookie auth flows automatically). The
	// `v=rev` param busts the browser cache so a manual "Fetch now" actually shows
	// the new image (the path itself is stable per date).
	let imageSrc = $derived(
		vibe ? attResourceUrl(ID, vibe.image_url, { v: String(vibe.rev ?? 0) }) : ''
	);
	// The day's font, loaded via a <link> below. CSS-quote the family name.
	let fontFamily = $derived(vibe ? `'${vibe.font}'` : 'inherit');
	let fontHref = $derived(
		vibe ? attResourceUrl(ID, 'font.css', { family: vibe.font }) : ''
	);

	async function load(force = false) {
		if (force) refreshing = true;
		else loading = true;
		error = null;
		try {
			vibe = force
				? await attAction<Vibe>(ID, 'POST', 'refresh')
				: await attGet<Vibe>(ID, 'today');
		} catch (e) {
			error = e instanceof Error ? e.message : 'failed to load the daily vibe';
		} finally {
			loading = false;
			refreshing = false;
		}
	}

	let offEvent: (() => void) | null = null;
	onMount(() => {
		void load();
		offEvent = connection.onEvent((topic) => {
			if (topic === 'vibe.changed') void load();
		});
		return () => offEvent?.();
	});
</script>

<svelte:head>
	{#if fontHref}
		<link rel="stylesheet" href={fontHref} />
	{/if}
</svelte:head>

<div class="vibe" style:--vibe-accent={vibe?.accent ?? 'var(--accent)'}>
	<StarField count={110} />

	<div class="content">
		{#if loading && !vibe}
			<Text role="muted">Summoning today's vibe…</Text>
		{:else if error && !vibe}
			<Surface level={2}>
				<Stack gap={2} align="center">
					<Icon name="image-off" size={28} />
					<Text role="heading">Couldn't load the vibe</Text>
					<Text role="muted">{error}</Text>
					<Button onclick={() => load()}>Try again</Button>
				</Stack>
			</Surface>
		{:else if vibe}
			<figure class="card">
				<div class="frame">
					{#if imageSrc}
						<img src={imageSrc} alt="Vibe of {vibe.date}" />
					{/if}
				</div>
				<figcaption class="quote" style:font-family={fontFamily}>
					<span class="mark">“</span>
					<p class="text">{vibe.quote}</p>
					<p class="author">— {vibe.author || 'Unknown'}</p>
				</figcaption>
			</figure>

			<div class="bar">
				<Text role="muted">{new Date(vibe.date).toDateString()}</Text>
				<Button onclick={() => load(true)} disabled={refreshing}>
					<Icon name={refreshing ? 'refresh-cw' : 'sparkles'} size={16} />
					{refreshing ? 'Fetching…' : 'Fetch now'}
				</Button>
			</div>
			{#if error}<span class="err">{error}</span>{/if}
		{/if}
	</div>
</div>

<style>
	.vibe {
		position: relative;
		min-height: 70dvh;
		display: flex;
		align-items: center;
		justify-content: center;
		padding: var(--space-5) var(--space-3);
		overflow: hidden;
		border-radius: var(--radius-lg);
		/* Tint the whole panel with the image-derived accent, blended toward bg so
		   text stays readable across themes. */
		background:
			radial-gradient(
				120% 90% at 50% 0%,
				color-mix(in srgb, var(--vibe-accent) 55%, var(--bg)) 0%,
				var(--bg) 75%
			);
	}
	.content {
		position: relative;
		z-index: 1;
		width: min(680px, 100%);
		display: flex;
		flex-direction: column;
		gap: var(--space-4);
		align-items: center;
	}
	.card {
		margin: 0;
		width: 100%;
		display: flex;
		flex-direction: column;
		gap: var(--space-4);
		align-items: center;
	}
	.frame {
		position: relative;
		width: 100%;
		aspect-ratio: 16 / 10;
		border-radius: var(--radius-lg);
		overflow: hidden;
		border: var(--border-width) solid var(--border-color);
		/* Accent lives ONLY as a glow behind the frame — the image is untouched. */
		box-shadow:
			var(--shadow-lg),
			0 0 90px -10px color-mix(in srgb, var(--vibe-accent) 75%, transparent),
			0 12px 40px -8px color-mix(in srgb, var(--vibe-accent) 50%, transparent);
	}
	.frame img {
		width: 100%;
		height: 100%;
		object-fit: cover;
		display: block;
	}
	.quote {
		text-align: center;
		color: var(--fg);
		max-width: 36ch;
		position: relative;
	}
	.quote .mark {
		font-size: 3rem;
		line-height: 0;
		color: var(--vibe-accent);
		opacity: 0.7;
	}
	.quote .text {
		font-size: clamp(1.4rem, 4vw, 2.1rem);
		line-height: 1.3;
		margin: var(--space-2) 0;
		text-wrap: balance;
	}
	.quote .author {
		color: var(--muted);
		font-size: 1rem;
		margin: 0;
	}
	.bar {
		display: flex;
		align-items: center;
		justify-content: space-between;
		gap: var(--space-3);
		width: 100%;
		flex-wrap: wrap;
	}
	.err {
		color: var(--danger);
		font-size: 0.9rem;
	}
</style>

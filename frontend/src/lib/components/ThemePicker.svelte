<script lang="ts">
	// Rich, app-sized theme gallery. Two axes — color palette and concept
	// (form/material) — each shown as a grid of live, clickable preview tiles.
	// Selecting one applies it instantly via the theme store (live + persisted).
	// Auto-lists whatever themes exist in the registry (no hardcoding), with a
	// search box and a light/dark filter for the palette grid.
	import { colorThemes, conceptThemes } from '$lib/themes/registry';
	import { fontList, fontMap } from '$lib/themes/fonts/registry';
	import { theme } from '$lib/themes/store.svelte';
	import { Text, Icon, Switch } from '$lib/components';

	let query = $state('');
	let modeFilter = $state<'all' | 'dark' | 'light'>('all');

	const colors = $derived(
		colorThemes.filter(
			(t) =>
				(modeFilter === 'all' || t.mode === modeFilter) &&
				t.name.toLowerCase().includes(query.toLowerCase())
		)
	);
	const concepts = $derived(
		conceptThemes.filter((t) => t.name.toLowerCase().includes(query.toLowerCase()))
	);
	const fonts = $derived(
		fontList.filter((f) => f.name.toLowerCase().includes(query.toLowerCase()))
	);
	// The font a null choice resolves to (the active concept's default), for the
	// "Use concept default" tile's label.
	const conceptDefaultFont = $derived(
		theme.concept.defaultFont ? fontMap.get(theme.concept.defaultFont) : undefined
	);
	// True when no font is pinned → the font follows the active concept's default.
	const usingDefault = $derived(theme.fontChoice === null);

	// The four hues that best convey a palette at a glance.
	const swatchKeys = ['--accent', '--success', '--warn', '--danger'] as const;
</script>

<div class="gallery">
	<div class="controls">
		<label class="search">
			<Icon name="search" size={16} />
			<input placeholder="Search themes…" bind:value={query} />
		</label>
		<div class="modes" role="group" aria-label="Filter by mode">
			{#each ['all', 'dark', 'light'] as m (m)}
				<button class="mode" class:active={modeFilter === m} onclick={() => (modeFilter = m as typeof modeFilter)}>
					{#if m === 'dark'}<Icon name="moon" size={14} />{:else if m === 'light'}<Icon name="sun" size={14} />{/if}
					<span>{m === 'all' ? 'All' : m === 'dark' ? 'Dark' : 'Light'}</span>
				</button>
			{/each}
		</div>
	</div>

	<section>
		<div class="section-head">
			<Text role="heading">Color</Text>
			<span class="hint">{colors.length} palettes</span>
		</div>
		<div class="grid">
			{#each colors as t (t.id)}
				{@const sel = theme.colorId === t.id}
				<button
					class="tile color"
					class:sel
					style:--p-bg={t.tokens['--bg']}
					style:--p-surface={t.tokens['--surface']}
					style:--p-fg={t.tokens['--fg']}
					style:--p-border={t.tokens['--border-color']}
					onclick={() => theme.setColor(t.id)}
					aria-pressed={sel}
				>
					<div class="preview">
						<div class="swatches">
							{#each swatchKeys as k (k)}
								<span class="sw" style:background={t.tokens[k]}></span>
							{/each}
						</div>
						<div class="bar"></div>
						<div class="bar short"></div>
					</div>
					<div class="meta">
						<span class="name">{t.name}</span>
						<span class="badge">{t.mode}</span>
						{#if sel}<span class="tick"><Icon name="check" size={14} /></span>{/if}
					</div>
				</button>
			{/each}
			{#if colors.length === 0}<div class="empty">No palettes match.</div>{/if}
		</div>
	</section>

	<section>
		<div class="section-head">
			<Text role="heading">Concept</Text>
			<span class="hint">{concepts.length} styles</span>
		</div>
		<div class="grid">
			{#each concepts as t (t.id)}
				{@const sel = theme.conceptId === t.id}
				<button
					class="tile concept"
					class:sel
					data-concept={t.id}
					style:--radius-md={t.tokens['--radius-md']}
					style:--radius-sm={t.tokens['--radius-sm']}
					style:--border-width={t.tokens['--border-width']}
					style:--shadow-md={t.tokens['--shadow-md']}
					style:--blur={t.tokens['--blur']}
					onclick={() => theme.setConcept(t.id)}
					aria-pressed={sel}
				>
					<div class="concept-preview">
						<span class="chip">Aa</span>
						<span class="chip accent">Aa</span>
					</div>
					<div class="meta">
						<span class="name">{t.name}</span>
						{#if sel}<span class="tick"><Icon name="check" size={14} /></span>{/if}
					</div>
				</button>
			{/each}
			{#if concepts.length === 0}<div class="empty">No styles match.</div>{/if}
		</div>
	</section>

	<section>
		<div class="section-head">
			<Text role="heading">Font</Text>
			<span class="hint">{fonts.length} fonts</span>
		</div>
		<div class="grid">
			<!-- "Use concept default" — clears any pinned font (null), so the font
			     follows whatever concept is active. -->
			<button
				class="tile font default"
				class:sel={usingDefault}
				onclick={() => theme.setFont(null)}
				aria-pressed={usingDefault}
			>
				<div class="font-preview">
					<span class="font-sample default-sample">Aa</span>
				</div>
				<div class="meta">
					<span class="name">Concept default</span>
					{#if usingDefault}<span class="tick"><Icon name="check" size={14} /></span>{/if}
				</div>
				<span class="badge"
					>{conceptDefaultFont ? conceptDefaultFont.name : 'system'}</span
				>
			</button>

			{#each fonts as f (f.id)}
				{@const sel = theme.fontChoice === f.id}
				<button
					class="tile font"
					class:sel
					style:--p-font={f.stack}
					onclick={() => theme.setFont(f.id)}
					aria-pressed={sel}
				>
					<div class="font-preview">
						<span class="font-sample">Aa</span>
					</div>
					<div class="meta">
						<span class="name">{f.name}</span>
						{#if sel}<span class="tick"><Icon name="check" size={14} /></span>{/if}
					</div>
					<span class="badge">{f.category}</span>
				</button>
			{/each}
			{#if fonts.length === 0}<div class="empty">No fonts match.</div>{/if}
		</div>
	</section>

	<section>
		<div class="section-head">
			<Text role="heading">Effects</Text>
		</div>
		<Switch
			checked={theme.animations}
			label="Animated background effects"
			onchange={(on) => theme.setAnimations(on)}
		/>
	</section>
</div>

<style>
	.gallery {
		display: flex;
		flex-direction: column;
		gap: var(--space-5);
	}
	.controls {
		display: flex;
		gap: var(--space-3);
		flex-wrap: wrap;
		align-items: center;
		position: sticky;
		top: 0;
		z-index: 2;
		padding: var(--space-2) 0;
		background: color-mix(in srgb, var(--bg) 92%, transparent);
		backdrop-filter: blur(var(--blur));
		-webkit-backdrop-filter: blur(var(--blur));
	}
	.search {
		display: inline-flex;
		align-items: center;
		gap: var(--space-2);
		flex: 1;
		min-width: 180px;
		color: var(--muted);
		background: color-mix(
			in srgb,
			var(--surface-2) calc(var(--surface-alpha) * 100%),
			transparent
		);
		border: var(--border-width) solid var(--border-color);
		border-radius: var(--radius-md);
		padding: var(--space-2) var(--space-3);
	}
	.search input {
		font: inherit;
		flex: 1;
		min-width: 0;
		color: var(--fg);
		background: transparent;
		border: none;
		outline: none;
	}
	.modes {
		display: inline-flex;
		gap: var(--space-1);
		padding: var(--space-1);
		background: color-mix(
			in srgb,
			var(--surface-2) calc(var(--surface-alpha) * 100%),
			transparent
		);
		border: var(--border-width) solid var(--border-color);
		border-radius: var(--radius-full);
	}
	.mode {
		display: inline-flex;
		align-items: center;
		gap: var(--space-1);
		font: inherit;
		font-size: 0.82rem;
		font-weight: var(--font-weight-bold);
		color: var(--muted);
		background: transparent;
		border: none;
		border-radius: var(--radius-full);
		padding: var(--space-1) var(--space-3);
		cursor: pointer;
	}
	.mode.active {
		background: var(--accent);
		color: var(--accent-fg);
	}
	section {
		display: flex;
		flex-direction: column;
		gap: var(--space-3);
	}
	.section-head {
		display: flex;
		align-items: baseline;
		gap: var(--space-2);
	}
	.hint {
		color: var(--muted);
		font-size: 0.8rem;
	}
	.grid {
		display: grid;
		grid-template-columns: repeat(auto-fill, minmax(150px, 1fr));
		gap: var(--space-3);
	}
	.tile {
		display: flex;
		flex-direction: column;
		gap: var(--space-2);
		padding: var(--space-2);
		text-align: left;
		background: color-mix(
			in srgb,
			var(--surface-2) calc(var(--surface-alpha) * 100%),
			transparent
		);
		border: var(--border-width) solid var(--border-color);
		border-radius: var(--radius-lg);
		box-shadow: var(--shadow-sm);
		cursor: pointer;
		transition: var(--transition);
	}
	.tile:hover {
		transform: translateY(var(--hover-lift));
		border-color: var(--accent);
		box-shadow: var(--shadow-hover), var(--hover-glow);
	}
	.tile:active {
		transform: scale(var(--press-scale));
	}
	.tile:focus-visible {
		outline: none;
		box-shadow: var(--focus-ring);
	}
	.tile.sel {
		border-color: var(--accent);
		box-shadow: 0 0 0 2px var(--accent);
	}
	/* Color tile: render a miniature of the palette using its own tokens. */
	.preview {
		display: flex;
		flex-direction: column;
		gap: 5px;
		padding: var(--space-2);
		background: var(--p-bg);
		border: 1px solid var(--p-border);
		border-radius: var(--radius-md);
		min-height: 64px;
	}
	.swatches {
		display: flex;
		gap: 4px;
	}
	.sw {
		width: 16px;
		height: 16px;
		border-radius: var(--radius-full);
	}
	.bar {
		height: 6px;
		width: 100%;
		border-radius: var(--radius-full);
		background: var(--p-fg);
		opacity: 0.85;
	}
	.bar.short {
		width: 60%;
		opacity: 0.45;
	}
	/* Concept tile: render two chips using the concept's form tokens (inlined
	   above) so you see its radius / border / shadow / blur at a glance. */
	.concept-preview {
		display: flex;
		gap: var(--space-2);
		align-items: center;
		justify-content: center;
		min-height: 64px;
		padding: var(--space-2);
	}
	.chip {
		display: inline-flex;
		align-items: center;
		justify-content: center;
		width: 42px;
		height: 42px;
		font-weight: 700;
		color: var(--fg);
		background: var(--surface);
		border: var(--border-width) solid var(--border-color);
		border-radius: var(--radius-md);
		box-shadow: var(--shadow-md);
	}
	.chip.accent {
		color: var(--accent-fg);
		background: var(--accent);
		border-color: var(--accent);
	}
	/* Font tile: a big "Aa" rendered in the font itself. */
	.font-preview {
		display: flex;
		align-items: center;
		justify-content: center;
		min-height: 64px;
		padding: var(--space-2);
		background: var(--surface);
		border: var(--border-width) solid var(--border-color);
		border-radius: var(--radius-md);
	}
	.font-sample {
		font-family: var(--p-font);
		font-size: 2rem;
		line-height: 1;
		color: var(--fg);
	}
	.default-sample {
		font-family: var(--font-sans);
		color: var(--accent);
	}
	.meta {
		display: flex;
		align-items: center;
		gap: var(--space-2);
	}
	.name {
		font-weight: var(--font-weight-bold);
		font-size: 0.88rem;
		color: var(--fg);
		flex: 1;
		min-width: 0;
		overflow: hidden;
		text-overflow: ellipsis;
		white-space: nowrap;
	}
	.badge {
		font-size: 0.66rem;
		text-transform: uppercase;
		letter-spacing: 0.04em;
		color: var(--muted);
	}
	.tick {
		display: inline-flex;
		color: var(--accent);
	}
	.empty {
		color: var(--muted);
		font-size: 0.85rem;
		padding: var(--space-3);
	}
</style>

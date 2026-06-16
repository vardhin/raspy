<script lang="ts">
	// Wallpaper chooser for the Theme app. Three sources: none, your uploaded
	// images (saved in IndexedDB, reusable later), and recent Vibe-of-the-Day
	// images (already cached on the Pi, fetched live by date). Plus dim/blur
	// controls. All frontend-only — see themes/wallpaper.svelte.ts.
	import { onMount, onDestroy } from 'svelte';
	import { wallpaper, type SavedWallpaper } from '$lib/themes/wallpaper.svelte';
	import { manifest } from '$lib/manifest/store.svelte';
	import { attResourceUrl } from '$lib/api';
	import { Text, Icon, Button, Slider } from '$lib/components';

	let fileInput = $state<HTMLInputElement>();
	let busy = $state(false);

	// Object URLs for saved-upload thumbnails, by id; revoked on teardown.
	let thumbs = $state<Record<string, string>>({});

	const vibeInstalled = $derived(!!manifest.byId('vibe'));

	// Recent ~24 days as candidate Vibe wallpapers. Days without a cached image
	// 404 and hide themselves (onerror). The vibe app warms today on load.
	const vibeDates = (() => {
		const out: string[] = [];
		const d = new Date();
		for (let i = 0; i < 24; i++) {
			out.push(d.toISOString().slice(0, 10));
			d.setDate(d.getDate() - 1);
		}
		return out;
	})();
	let vibeOk = $state<Record<string, boolean>>({});
	function vibeSrc(date: string) {
		return attResourceUrl('vibe', `image/${date}`, {});
	}

	// Load any thumbnails we don't have yet, and revoke ones whose wallpaper was
	// removed. Driven off the saved-ids signature (NOT off `thumbs`, so this never
	// feeds back into itself — that caused an effect_update_depth loop).
	async function syncThumbs(ids: string[]) {
		for (const id of ids) {
			if (!thumbs[id]) {
				const url = await wallpaper.thumbUrl(id);
				if (url) thumbs[id] = url; // mutate in place; no new object each run
			}
		}
		for (const id of Object.keys(thumbs)) {
			if (!ids.includes(id)) {
				wallpaper.revoke(thumbs[id]);
				delete thumbs[id];
			}
		}
	}

	// Track only the id list (a primitive string), so the effect re-runs when the
	// set of saved wallpapers changes — not when `thumbs` mutates.
	const savedIds = $derived(wallpaper.saved.map((w) => w.id).join(','));
	$effect(() => {
		void savedIds; // establish the dependency
		void syncThumbs(wallpaper.saved.map((w) => w.id));
	});

	async function onPick(e: Event) {
		const files = (e.target as HTMLInputElement).files;
		if (!files || files.length === 0) return;
		busy = true;
		try {
			for (const f of Array.from(files)) await wallpaper.addUpload(f);
		} finally {
			busy = false;
			if (fileInput) fileInput.value = '';
		}
	}

	async function removeSaved(id: string) {
		if (thumbs[id]) wallpaper.revoke(thumbs[id]);
		await wallpaper.remove(id);
	}

	onMount(() => void wallpaper.init());
	onDestroy(() => {
		for (const url of Object.values(thumbs)) wallpaper.revoke(url);
	});

	const isActiveUpload = (id: string) => wallpaper.kind === 'upload' && wallpaper.ref === id;
	const isActiveVibe = (date: string) => wallpaper.kind === 'vibe' && wallpaper.ref === date;
</script>

<div class="wp">
	<div class="section-head">
		<Text role="heading">Wallpaper</Text>
		<input
			bind:this={fileInput}
			type="file"
			accept="image/*"
			multiple
			style="display:none"
			onchange={onPick}
		/>
		<Button size="sm" disabled={busy} onclick={() => fileInput?.click()}>
			<Icon name="upload" size={15} />
			<span>{busy ? 'Adding…' : 'Upload'}</span>
		</Button>
	</div>

	<div class="grid">
		<!-- None -->
		<button class="tile none" class:sel={wallpaper.kind === 'none'} onclick={() => wallpaper.clear()}>
			<div class="thumb empty"><Icon name="image-off" size={22} /></div>
			<span class="cap">None</span>
		</button>

		<!-- Your uploads -->
		{#each wallpaper.saved as w (w.id)}
			<div class="tile" class:sel={isActiveUpload(w.id)}>
				<button class="pick" onclick={() => wallpaper.useUpload(w.id)} aria-label={w.name}>
					<div class="thumb">
						{#if thumbs[w.id]}<img src={thumbs[w.id]} alt={w.name} />{/if}
						{#if isActiveUpload(w.id)}<span class="tick"><Icon name="check" size={14} /></span>{/if}
					</div>
					<span class="cap">{w.name}</span>
				</button>
				<button class="rm" aria-label="Remove" onclick={() => removeSaved(w.id)}>
					<Icon name="trash" size={13} />
				</button>
			</div>
		{/each}
	</div>

	{#if vibeInstalled}
		<div class="section-head sub">
			<Text role="label">From Vibe of the Day</Text>
			<Text role="muted">Recently cached daily images.</Text>
		</div>
		<div class="grid">
			{#each vibeDates as date (date)}
				<button
					class="tile vibe"
					class:sel={isActiveVibe(date)}
					class:hidden={vibeOk[date] === false}
					onclick={() => wallpaper.useVibe(date)}
				>
					<div class="thumb">
						<img
							src={vibeSrc(date)}
							alt="Vibe {date}"
							onload={() => (vibeOk = { ...vibeOk, [date]: true })}
							onerror={() => (vibeOk = { ...vibeOk, [date]: false })}
						/>
						{#if isActiveVibe(date)}<span class="tick"><Icon name="check" size={14} /></span>{/if}
					</div>
					<span class="cap">{new Date(date + 'T00:00:00').toLocaleDateString(undefined, { month: 'short', day: 'numeric' })}</span>
				</button>
			{/each}
		</div>
	{/if}

	{#if wallpaper.kind !== 'none'}
		<div class="knobs">
			<label class="knob">
				<span>Dim</span>
				<Slider min={0} max={100} value={Math.round(wallpaper.dim * 100)} oninput={(v) => wallpaper.setDim(v / 100)} />
			</label>
			<label class="knob">
				<span>Blur</span>
				<Slider min={0} max={24} value={wallpaper.blur} oninput={(v) => wallpaper.setBlur(v)} />
			</label>
		</div>
	{/if}
</div>

<style>
	.wp {
		display: flex;
		flex-direction: column;
		gap: var(--space-3);
	}
	.section-head {
		display: flex;
		align-items: center;
		justify-content: space-between;
		gap: var(--space-2);
		flex-wrap: wrap;
	}
	.section-head.sub {
		flex-direction: column;
		align-items: flex-start;
		gap: 0;
		margin-top: var(--space-2);
	}
	.grid {
		display: grid;
		grid-template-columns: repeat(auto-fill, minmax(120px, 1fr));
		gap: var(--space-3);
	}
	.tile {
		position: relative;
		display: flex;
		flex-direction: column;
		gap: var(--space-1);
		padding: 0;
		background: none;
		border: none;
		cursor: pointer;
		text-align: left;
	}
	.tile.hidden {
		display: none;
	}
	.pick {
		display: flex;
		flex-direction: column;
		gap: var(--space-1);
		padding: 0;
		background: none;
		border: none;
		cursor: pointer;
		width: 100%;
	}
	.thumb {
		position: relative;
		aspect-ratio: 16 / 10;
		width: 100%;
		overflow: hidden;
		border: var(--border-width) solid var(--border-color);
		border-radius: var(--radius-md);
		box-shadow: var(--shadow-sm);
		background: color-mix(
			in srgb,
			var(--surface-2) calc(var(--surface-alpha) * 100%),
			transparent
		);
		transition: border-color var(--motion-fast) var(--motion-ease);
	}
	.thumb img {
		width: 100%;
		height: 100%;
		object-fit: cover;
		display: block;
	}
	.thumb.empty {
		display: flex;
		align-items: center;
		justify-content: center;
		color: var(--muted);
	}
	.tile:hover .thumb {
		border-color: var(--accent);
	}
	.tile.sel .thumb {
		border-color: var(--accent);
		box-shadow: 0 0 0 2px var(--accent);
	}
	.tick {
		position: absolute;
		top: var(--space-1);
		right: var(--space-1);
		display: inline-flex;
		padding: 2px;
		color: var(--accent-fg);
		background: var(--accent);
		border-radius: var(--radius-full);
	}
	.cap {
		font-size: 0.78rem;
		font-weight: var(--font-weight-bold);
		color: var(--fg);
		overflow: hidden;
		text-overflow: ellipsis;
		white-space: nowrap;
	}
	.rm {
		position: absolute;
		top: var(--space-1);
		left: var(--space-1);
		display: inline-flex;
		padding: 3px;
		color: var(--danger-fg);
		background: var(--danger);
		border: none;
		border-radius: var(--radius-full);
		box-shadow: var(--shadow-sm);
		cursor: pointer;
		opacity: 0;
		transition: opacity var(--motion-fast) var(--motion-ease);
	}
	.tile:hover .rm {
		opacity: 1;
	}
	.knobs {
		display: flex;
		gap: var(--space-4);
		flex-wrap: wrap;
		padding-top: var(--space-2);
	}
	.knob {
		display: flex;
		align-items: center;
		gap: var(--space-2);
		flex: 1;
		min-width: 180px;
		font-size: 0.85rem;
		font-weight: var(--font-weight-bold);
		color: var(--muted);
	}
	.knob span {
		flex: none;
		width: 2.4rem;
	}
</style>

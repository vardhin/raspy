<script lang="ts">
	// Calendar — a continuous-timeline memory journal + planner. Every day in the
	// chosen range is a card; days with entries show photos + text (inline
	// carousel, multi-entry switcher), empty days show that day's shared "vibe"
	// placeholder (image + quote, from the vibe app's cache). A zoom slider sets
	// cards-per-row; a Week/Month/Custom switch sets the range. Each card is tinted
	// by its weekday on a rising gradient (Mon→Sun) derived from theme tokens, so
	// you can read the day at a glance in any palette. Future entries can carry a
	// reminder that fires a durable notification.
	import { onMount } from 'svelte';
	import {
		Surface,
		Stack,
		Text,
		Button,
		Icon,
		Field,
		Modal,
		Slider,
		SegmentedControl,
		Carousel
	} from '$lib/components';
	import {
		attGetQuery,
		attAction,
		attResourceUrl,
		attUpload,
		attDeleteQuery
	} from '$lib/api';
	import { connection } from '$lib/connection.svelte';
	import { kvGet, kvSet } from '$lib/kv';

	const ID = 'calendar';
	const ZOOM_KEY = 'calendar:zoom';

	type Img = { id: number; hash: string; mime: string; ord: number; url: string };
	type Entry = {
		id: number;
		date: string;
		title: string;
		description: string;
		remind_at: number | null;
		notified: boolean;
		images: Img[];
	};
	type Placeholder = { image_url: string; quote: string; author: string; accent: string };
	type Day = {
		date: string;
		weekday: number; // 0 = Mon … 6 = Sun
		entries: Entry[];
		placeholder?: Placeholder;
	};

	type Mode = 'week' | 'month' | 'custom';

	// --- range + zoom state --------------------------------------------------
	let mode = $state<Mode>('month');
	let anchor = $state(todayISO()); // a date inside the current window
	let customFrom = $state(todayISO());
	let customTo = $state(addDays(todayISO(), 13));
	let zoom = $state(3); // 1 (tiny, many cols) … 5 (large, few cols)

	let days = $state<Day[]>([]);
	let loading = $state(true);
	let error = $state<string | null>(null);

	// Per-day index into its entries (which entry is shown on the card).
	let entryIdx = $state<Record<string, number>>({});
	// Per-day index into the shown entry's images (card carousel position).
	let imgIdx = $state<Record<string, number>>({});

	// --- date helpers --------------------------------------------------------
	function todayISO(): string {
		return new Date().toISOString().slice(0, 10);
	}
	function addDays(iso: string, n: number): string {
		const d = new Date(iso + 'T00:00:00');
		d.setDate(d.getDate() + n);
		return d.toISOString().slice(0, 10);
	}
	function mondayOf(iso: string): string {
		const d = new Date(iso + 'T00:00:00');
		const dow = (d.getDay() + 6) % 7; // 0 = Monday
		d.setDate(d.getDate() - dow);
		return d.toISOString().slice(0, 10);
	}

	const WEEKDAYS = ['Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat', 'Sun'];

	let window_ = $derived.by(() => {
		if (mode === 'week') {
			const from = mondayOf(anchor);
			return { from, to: addDays(from, 6) };
		}
		if (mode === 'month') {
			const d = new Date(anchor + 'T00:00:00');
			const from = `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, '0')}-01`;
			const last = new Date(d.getFullYear(), d.getMonth() + 1, 0).getDate();
			const to = `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, '0')}-${String(last).padStart(2, '0')}`;
			return { from, to };
		}
		return { from: customFrom, to: customTo };
	});

	let rangeLabel = $derived.by(() => {
		const f = new Date(window_.from + 'T00:00:00');
		if (mode === 'month') return f.toLocaleDateString(undefined, { month: 'long', year: 'numeric' });
		const t = new Date(window_.to + 'T00:00:00');
		const fmt = (d: Date) => d.toLocaleDateString(undefined, { month: 'short', day: 'numeric' });
		return `${fmt(f)} – ${fmt(t)}`;
	});

	// Zoom → grid columns. At the lowest zoom (1) we force a dense 7-wide row;
	// higher zooms use auto-fill with a growing min width so cards get bigger and
	// columns reduce as you zoom in. Persisted across sessions (see onMount).
	let gridCols = $derived(
		zoom <= 1
			? 'repeat(7, minmax(0, 1fr))'
			: `repeat(auto-fill, minmax(${110 + (zoom - 1) * 70}px, 1fr))`
	);

	$effect(() => {
		void kvSet(ZOOM_KEY, zoom);
	});

	// Weekday tint: a rising gradient Mon→Sun, mixing --accent toward --info by the
	// weekday index. Pure token math, so it re-skins with the theme.
	function tint(weekday: number): string {
		const pct = Math.round((weekday / 6) * 100);
		return `color-mix(in srgb, var(--info) ${pct}%, var(--accent))`;
	}

	// A small, stable per-day tilt so the wall of polaroids feels scattered, not
	// gridded. Deterministic from the date so it doesn't jitter on re-render.
	function tiltFor(date: string): number {
		let h = 0;
		for (const ch of date) h = (h * 31 + ch.charCodeAt(0)) | 0;
		return ((h % 5) - 2) * 0.7; // -1.4° … +1.4°
	}

	// --- data ----------------------------------------------------------------
	async function load() {
		loading = true;
		error = null;
		try {
			days = await attGetQuery<Day[]>(ID, 'range', { from: window_.from, to: window_.to });
		} catch (e) {
			error = e instanceof Error ? e.message : 'failed to load calendar';
		} finally {
			loading = false;
		}
	}

	// Reload whenever the window changes.
	$effect(() => {
		void window_.from;
		void window_.to;
		void load();
	});

	function shiftWindow(dir: number) {
		if (mode === 'week') anchor = addDays(anchor, 7 * dir);
		else if (mode === 'month') {
			const d = new Date(anchor + 'T00:00:00');
			d.setMonth(d.getMonth() + dir);
			anchor = d.toISOString().slice(0, 10);
		} else {
			const span = Math.max(1, daysBetween(customFrom, customTo) + 1);
			customFrom = addDays(customFrom, span * dir);
			customTo = addDays(customTo, span * dir);
		}
	}
	function daysBetween(a: string, b: string): number {
		return Math.round(
			(new Date(b + 'T00:00:00').getTime() - new Date(a + 'T00:00:00').getTime()) / 86400000
		);
	}
	function goToday() {
		anchor = todayISO();
	}

	function curEntry(day: Day): Entry | null {
		if (day.entries.length === 0) return null;
		const i = Math.min(entryIdx[day.date] ?? 0, day.entries.length - 1);
		return day.entries[i];
	}
	function entryImages(entry: Entry) {
		return entry.images
			.slice()
			.sort((a, b) => a.ord - b.ord)
			.map((im) => ({ src: attResourceUrl(ID, im.url, {}), alt: entry.title }));
	}
	function isPast(date: string): boolean {
		return date < todayISO();
	}
	function isToday(date: string): boolean {
		return date === todayISO();
	}

	function cycleEntry(day: Day, delta: number) {
		const n = day.entries.length;
		if (n < 2) return;
		entryIdx[day.date] = ((entryIdx[day.date] ?? 0) + delta + n) % n;
		imgIdx[day.date] = 0;
	}

	// --- editor modal --------------------------------------------------------
	let editorOpen = $state(false);
	let editing = $state<Entry | null>(null);
	let formDate = $state(todayISO());
	let formTitle = $state('');
	let formDesc = $state('');
	// Reminder: a simple toggle + an optional hour-of-day. The reminder always
	// fires ON the entry's own date (no separate date picker), at the chosen hour
	// in the device's local time. 24h selection, with a 12h echo shown beside it.
	let formRemindOn = $state(false);
	let formRemindHour = $state('9'); // "0".."23" (Field select binds strings)
	let pendingFiles = $state<File[]>([]);
	let uploadBusy = $state(false);
	let fileInput = $state<HTMLInputElement>();

	// 24h → "9:00 AM" style echo.
	function hour12(h: number): string {
		const ampm = h < 12 ? 'AM' : 'PM';
		const hr = h % 12 === 0 ? 12 : h % 12;
		return `${hr}:00 ${ampm}`;
	}
	// Unix seconds for the entry's date at the given local hour.
	function remindTs(date: string, hour: number): number {
		const d = new Date(date + 'T00:00:00'); // local midnight of the entry date
		d.setHours(hour, 0, 0, 0);
		return Math.floor(d.getTime() / 1000);
	}

	function openCreate(date: string) {
		editing = null;
		formDate = date;
		formTitle = '';
		formDesc = '';
		formRemindOn = false;
		formRemindHour = '9';
		pendingFiles = [];
		editorOpen = true;
	}
	function openEdit(entry: Entry) {
		editing = entry;
		formDate = entry.date;
		formTitle = entry.title;
		formDesc = entry.description;
		formRemindOn = entry.remind_at != null;
		formRemindHour =
			entry.remind_at != null ? String(new Date(entry.remind_at * 1000).getHours()) : '9';
		pendingFiles = [];
		editorOpen = true;
	}

	async function saveEntry() {
		uploadBusy = true;
		error = null;
		try {
			const remind_at = formRemindOn ? remindTs(formDate, Number(formRemindHour)) : null;
			let entry: Entry;
			if (editing) {
				entry = await attAction<Entry>(ID, 'PATCH', `entries/${editing.id}`, {
					date: formDate,
					title: formTitle,
					description: formDesc,
					...(remind_at != null ? { remind_at } : { clear_remind: true })
				});
			} else {
				entry = await attAction<Entry>(ID, 'POST', 'entries', {
					date: formDate,
					title: formTitle,
					description: formDesc,
					...(remind_at != null ? { remind_at } : {})
				});
			}
			for (const file of pendingFiles) {
				await attUpload(ID, `entries/${entry.id}/images`, {}, file);
			}
			editorOpen = false;
			await load();
		} catch (e) {
			error = e instanceof Error ? e.message : 'failed to save entry';
		} finally {
			uploadBusy = false;
		}
	}

	async function deleteEntry(entry: Entry) {
		if (!confirm('Delete this entry and its photos? This cannot be undone.')) return;
		try {
			await attAction(ID, 'DELETE', `entries/${entry.id}`);
			if (viewing?.id === entry.id) viewing = null;
			await load();
		} catch (e) {
			error = e instanceof Error ? e.message : 'failed to delete';
		}
	}

	async function deleteImage(im: Img) {
		try {
			await attDeleteQuery(ID, `images/${im.id}`, {});
			await load();
			if (viewing) viewing = days.flatMap((d) => d.entries).find((e) => e.id === viewing!.id) ?? null;
		} catch (e) {
			error = e instanceof Error ? e.message : 'failed to remove photo';
		}
	}

	function onPickFiles(e: Event) {
		const files = (e.target as HTMLInputElement).files;
		if (files) pendingFiles = [...pendingFiles, ...Array.from(files)];
		if (fileInput) fileInput.value = '';
	}

	// --- full-view modal -----------------------------------------------------
	let viewing = $state<Entry | null>(null);
	let viewIdx = $state(0);

	function openView(entry: Entry) {
		viewing = entry;
		viewIdx = 0;
	}

	function fmtDate(date: string): string {
		return new Date(date + 'T00:00:00').toLocaleDateString(undefined, {
			weekday: 'long',
			year: 'numeric',
			month: 'long',
			day: 'numeric'
		});
	}
	function oneLine(s: string): string {
		const t = s.trim().split('\n')[0] ?? '';
		return t.length > 90 ? t.slice(0, 87) + '…' : t;
	}

	let offEvent: (() => void) | null = null;
	onMount(() => {
		// Restore the last zoom level.
		void kvGet<number>(ZOOM_KEY).then((z) => {
			if (typeof z === 'number' && z >= 1 && z <= 5) zoom = z;
		});
		offEvent = connection.onEvent((topic) => {
			if (topic === 'calendar.changed') void load();
		});
		return () => offEvent?.();
	});
</script>

<Stack gap={3}>
	<!-- Top bar -->
	<Surface level={2}>
		<div class="bar">
			<div class="nav">
				<Button variant="ghost" size="sm" onclick={() => shiftWindow(-1)}>
					<Icon name="chevron-left" size={18} />
				</Button>
				<Text role="heading">{rangeLabel}</Text>
				<Button variant="ghost" size="sm" onclick={() => shiftWindow(1)}>
					<Icon name="chevron-right" size={18} />
				</Button>
				<Button variant="ghost" size="sm" onclick={goToday}>Today</Button>
			</div>

			<div class="controls">
				<SegmentedControl
					bind:value={mode}
					options={[
						{ value: 'week', label: 'Week' },
						{ value: 'month', label: 'Month' },
						{ value: 'custom', label: 'Custom' }
					]}
				/>
				<div class="zoom">
					<Slider bind:value={zoom} min={1} max={5} step={1} label="Zoom">
						{#snippet lead()}<Icon name="zoom-out" size={16} />{/snippet}
						{#snippet trail()}<Icon name="zoom-in" size={16} />{/snippet}
					</Slider>
				</div>
			</div>
		</div>

		{#if mode === 'custom'}
			<div class="custom">
				<Field type="date" label="From" bind:value={customFrom} />
				<Field type="date" label="To" bind:value={customTo} />
			</div>
		{/if}
	</Surface>

	{#if error}<span class="err">{error}</span>{/if}

	{#if loading && days.length === 0}
		<Text role="muted">Loading…</Text>
	{:else}
		<div class="grid" style:--grid-cols={gridCols}>
			{#each days as day (day.date)}
				{@const entry = curEntry(day)}
				{@const empty = !entry}
				<!-- A mini polaroid. The weekday accent lives ONLY as a glow behind the
				     card (--day-tint), never as a fill over the photo. -->
				<div
					class="polaroid"
					class:today={isToday(day.date)}
					class:empty
					style:--day-tint={tint(day.weekday)}
					style:--tilt="{tiltFor(day.date)}deg"
				>
					<!-- Photo window -->
					{#if entry}
						{@const imgs = entryImages(entry)}
						<div class="window">
							{#if imgs.length > 0}
								<Carousel
									items={imgs}
									compact
									rounded={false}
									index={imgIdx[day.date] ?? 0}
									onindex={(i) => (imgIdx[day.date] = i)}
									onactivate={() => openView(entry)}
								/>
							{:else}
								<button class="no-photo" onclick={() => openView(entry)}>
									<Icon name="image-off" size={22} />
								</button>
							{/if}
						</div>
					{:else if day.placeholder}
						<button
							class="window ph"
							onclick={() => openCreate(day.date)}
							aria-label="Add entry"
						>
							<img src={day.placeholder.image_url} alt="" loading="lazy" />
							<span class="ph-hint"><Icon name="plus" size={16} /></span>
						</button>
					{:else}
						<button class="window bare" onclick={() => openCreate(day.date)} aria-label="Add entry">
							<Icon name="plus" size={20} />
						</button>
					{/if}

					<!-- Caption mat (the white strip under a polaroid). A div (not a
				     button) so the multi-entry arrows can nest as real buttons. -->
					<div
						class="mat"
						role="button"
						tabindex="0"
						onclick={() => (entry ? openView(entry) : openCreate(day.date))}
						onkeydown={(e) =>
							(e.key === 'Enter' || e.key === ' ') &&
							(entry ? openView(entry) : openCreate(day.date))}
					>
						<span class="date-chip">
							<span class="dow">{WEEKDAYS[day.weekday]}</span>
							<span class="dnum">{Number(day.date.slice(8))}</span>
						</span>
						{#if entry}
							<span class="caption">{entry.title || oneLine(entry.description) || '—'}</span>
						{:else if day.placeholder}
							<span class="caption muted">“{oneLine(day.placeholder.quote)}”</span>
						{:else}
							<span class="caption muted">add a memory</span>
						{/if}

						<span class="badges">
							{#if entry?.remind_at && !entry.notified}
								<span class="remind"><Icon name="bell" size={11} /></span>
							{/if}
							{#if day.entries.length > 1}
								<span class="multi">
									<button
										aria-label="Previous entry"
										onclick={(e) => {
											e.stopPropagation();
											cycleEntry(day, -1);
										}}><Icon name="chevron-left" size={12} /></button
									>
									{(entryIdx[day.date] ?? 0) + 1}/{day.entries.length}
									<button
										aria-label="Next entry"
										onclick={(e) => {
											e.stopPropagation();
											cycleEntry(day, 1);
										}}><Icon name="chevron-right" size={12} /></button
									>
								</span>
							{/if}
						</span>
					</div>
				</div>
			{/each}
		</div>
	{/if}
</Stack>

<!-- Full view -->
{#if viewing}
	{@const imgs = entryImages(viewing)}
	<Modal open title={viewing.title || 'Entry'} size="lg" onclose={() => (viewing = null)}>
		<Stack gap={3}>
			{#if imgs.length > 0}
				<Carousel items={imgs} bind:index={viewIdx} />
			{/if}
			{#if viewing.description}
				<Text>{viewing.description}</Text>
			{/if}
			<Text role="muted">{fmtDate(viewing.date)}</Text>
			{#if viewing.remind_at}
				<Text role="label">
					{viewing.notified ? 'Reminded' : 'Reminder'}:
					{new Date(viewing.remind_at * 1000).toLocaleString()}
				</Text>
			{/if}
			<Stack direction="row" gap={2} justify="end">
				<Button variant="danger" onclick={() => deleteEntry(viewing!)}>
					<Icon name="trash" size={15} /> Delete
				</Button>
				<Button variant="ghost" onclick={() => openEdit(viewing!)}>
					<Icon name="edit" size={15} /> Edit
				</Button>
			</Stack>
		</Stack>
	</Modal>
{/if}

<!-- Editor -->
<Modal
	open={editorOpen}
	title={editing ? 'Edit entry' : 'New entry'}
	onclose={() => (editorOpen = false)}
>
	<Stack gap={3}>
		<Field type="date" label="Date" bind:value={formDate} />
		<Field label="Title" placeholder="A title for this memory…" bind:value={formTitle} />
		<Field
			type="textarea"
			label="Description"
			placeholder="What happened? How did it feel?"
			bind:value={formDesc}
		/>
		<!-- Reminder: a toggle, plus an optional hour. Fires on this entry's date. -->
		<div class="remind-box">
			<label class="toggle">
				<input type="checkbox" bind:checked={formRemindOn} />
				<span class="track"><span class="knob"></span></span>
				<span class="toggle-label">
					Remind me on {new Date(formDate + 'T00:00:00').toLocaleDateString(undefined, {
						month: 'short',
						day: 'numeric'
					})}
				</span>
			</label>

			{#if formRemindOn}
				<div class="hour-row">
					<Field
						type="select"
						label="At (24h)"
						bind:value={formRemindHour}
						options={Array.from({ length: 24 }, (_, h) => ({
							value: String(h),
							label: String(h).padStart(2, '0') + ':00'
						}))}
					/>
					<span class="echo">{hour12(Number(formRemindHour))}</span>
				</div>
			{/if}
		</div>

		{#if editing && editing.images.length > 0}
			<div>
				<Text role="label">Photos</Text>
				<div class="thumbs">
					{#each editing.images.slice().sort((a, b) => a.ord - b.ord) as im (im.id)}
						<div class="thumb">
							<img src={attResourceUrl(ID, im.url, {})} alt="" />
							<button class="rm" aria-label="Remove photo" onclick={() => deleteImage(im)}>
								<Icon name="x" size={13} />
							</button>
						</div>
					{/each}
				</div>
			</div>
		{/if}

		{#if pendingFiles.length > 0}
			<Text role="muted">{pendingFiles.length} photo(s) to upload on save.</Text>
		{/if}

		<input
			bind:this={fileInput}
			type="file"
			accept="image/*"
			multiple
			style="display:none"
			onchange={onPickFiles}
		/>
		<Stack direction="row" gap={2} justify="between" align="center">
			<Button variant="ghost" onclick={() => fileInput?.click()}>
				<Icon name="image" size={16} /> Add photos
			</Button>
			<Stack direction="row" gap={2}>
				<Button variant="ghost" onclick={() => (editorOpen = false)}>Cancel</Button>
				<Button onclick={saveEntry} disabled={uploadBusy}>
					{uploadBusy ? 'Saving…' : 'Save'}
				</Button>
			</Stack>
		</Stack>
	</Stack>
</Modal>

<style>
	.bar {
		display: flex;
		align-items: center;
		justify-content: space-between;
		gap: var(--space-3);
		flex-wrap: wrap;
	}
	.nav {
		display: flex;
		align-items: center;
		gap: var(--space-2);
	}
	.controls {
		display: flex;
		align-items: center;
		gap: var(--space-3);
		flex-wrap: wrap;
	}
	.zoom {
		width: 140px;
	}
	.custom {
		display: flex;
		gap: var(--space-3);
		margin-top: var(--space-3);
		flex-wrap: wrap;
	}
	.err {
		color: var(--danger);
		font-size: 0.9rem;
	}
	.grid {
		display: grid;
		grid-template-columns: var(--grid-cols, repeat(auto-fill, minmax(180px, 1fr)));
		gap: var(--space-4) var(--space-3);
		padding: var(--space-2) 0;
	}

	/* --- Polaroid card ---------------------------------------------------- */
	.polaroid {
		display: flex;
		flex-direction: column;
		/* The classic white polaroid mat: a touch of padding all round, more at the
		   bottom for the caption. Uses --surface-2 so it reads as "the photo paper"
		   against the page, and re-skins with the theme. */
		background: var(--surface-2);
		padding: 6px 6px 0;
		border: var(--border-width) solid var(--border-color);
		border-radius: 3px;
		/* Accent is ONLY a soft glow behind the card — never over the photo. */
		box-shadow:
			var(--shadow-md),
			0 6px 22px -6px color-mix(in srgb, var(--day-tint) 55%, transparent);
		transform: rotate(var(--tilt, 0deg));
		transition:
			transform var(--motion-base) var(--motion-ease),
			box-shadow var(--motion-base) var(--motion-ease);
		will-change: transform;
	}
	.polaroid:hover {
		transform: rotate(0deg) translateY(calc(var(--depth) * -2px)) scale(1.02);
		box-shadow:
			var(--shadow-lg),
			0 12px 34px -6px color-mix(in srgb, var(--day-tint) 70%, transparent);
		z-index: 2;
	}
	.polaroid.today {
		outline: 2px solid var(--accent);
		outline-offset: 2px;
	}

	.window {
		position: relative;
		display: flex;
		align-items: center;
		justify-content: center;
		aspect-ratio: 1 / 1;
		overflow: hidden;
		background: var(--bg);
		/* Photo sits in a slightly inset window, like film behind paper. */
		box-shadow: inset 0 0 0 1px color-mix(in srgb, var(--fg) 8%, transparent);
	}
	.window :global(.carousel) {
		width: 100%;
		height: 100%;
	}
	.window :global(.stage) {
		aspect-ratio: 1 / 1;
		height: 100%;
	}
	.window.ph,
	.window.bare,
	.window .no-photo {
		border: none;
		cursor: pointer;
		color: var(--muted);
		width: 100%;
	}
	.window.ph img {
		width: 100%;
		height: 100%;
		object-fit: cover;
		/* Empty days are gently desaturated so entries with real photos pop. */
		filter: saturate(0.65) brightness(0.92);
	}
	.window.ph .ph-hint {
		position: absolute;
		inset: 0;
		display: flex;
		align-items: center;
		justify-content: center;
		color: #fff;
		background: color-mix(in srgb, var(--bg) 30%, transparent);
		opacity: 0;
		transition: opacity var(--motion-fast) var(--motion-ease);
	}
	.window.ph:hover .ph-hint {
		opacity: 1;
	}
	.window.bare {
		background: color-mix(in srgb, var(--day-tint) 8%, var(--bg));
	}
	.no-photo {
		background: var(--surface);
		height: 100%;
	}

	/* The caption strip under the photo (the wide bottom of a polaroid). */
	.mat {
		display: flex;
		align-items: center;
		gap: var(--space-2);
		width: 100%;
		padding: var(--space-2) 4px var(--space-3);
		background: transparent;
		border: none;
		cursor: pointer;
		text-align: left;
		font: inherit;
		color: var(--fg);
		min-height: 46px;
	}
	.date-chip {
		display: flex;
		flex-direction: column;
		align-items: center;
		line-height: 1;
		flex: none;
		padding-right: var(--space-2);
		border-right: 1px solid color-mix(in srgb, var(--day-tint) 45%, var(--border-color));
	}
	.date-chip .dow {
		font-size: 0.6rem;
		letter-spacing: 0.06em;
		text-transform: uppercase;
		color: var(--day-tint);
		font-weight: var(--font-weight-bold);
	}
	.date-chip .dnum {
		font-size: 1.05rem;
		font-weight: var(--font-weight-bold);
		color: var(--fg);
	}
	.caption {
		flex: 1;
		min-width: 0;
		font-size: 0.82rem;
		line-height: 1.25;
		overflow: hidden;
		text-overflow: ellipsis;
		display: -webkit-box;
		-webkit-line-clamp: 2;
		line-clamp: 2;
		-webkit-box-orient: vertical;
	}
	.caption.muted {
		color: var(--muted);
		font-style: italic;
	}
	.badges {
		display: flex;
		align-items: center;
		gap: 4px;
		flex: none;
	}
	.remind {
		display: inline-flex;
		color: var(--accent);
	}
	.multi {
		display: inline-flex;
		align-items: center;
		gap: 2px;
		font-size: 0.7rem;
		color: var(--muted);
	}
	.multi button {
		display: inline-flex;
		border: none;
		background: transparent;
		color: var(--muted);
		cursor: pointer;
		padding: 0;
	}
	.multi button:hover {
		color: var(--fg);
	}

	/* --- reminder toggle + hour ------------------------------------------- */
	.remind-box {
		display: flex;
		flex-direction: column;
		gap: var(--space-2);
		padding: var(--space-3);
		border: var(--border-width) solid var(--border-color);
		border-radius: var(--radius-md);
		background: color-mix(in srgb, var(--surface-2) calc(var(--surface-alpha) * 100%), transparent);
	}
	.toggle {
		display: flex;
		align-items: center;
		gap: var(--space-2);
		cursor: pointer;
	}
	.toggle input {
		position: absolute;
		opacity: 0;
		pointer-events: none;
	}
	.track {
		position: relative;
		width: 40px;
		height: 22px;
		border-radius: var(--radius-full);
		background: var(--surface);
		border: var(--border-width) solid var(--border-color);
		transition: background var(--motion-fast) var(--motion-ease);
		flex: none;
	}
	.knob {
		position: absolute;
		top: 50%;
		left: 2px;
		transform: translateY(-50%);
		width: 16px;
		height: 16px;
		border-radius: var(--radius-full);
		background: var(--muted);
		transition:
			left var(--motion-fast) var(--motion-ease),
			background var(--motion-fast) var(--motion-ease);
	}
	.toggle input:checked + .track {
		background: var(--accent);
	}
	.toggle input:checked + .track .knob {
		left: 20px;
		background: var(--accent-fg);
	}
	.toggle input:focus-visible + .track {
		outline: 2px solid var(--accent);
		outline-offset: 2px;
	}
	.toggle-label {
		font-size: 0.9rem;
	}
	.hour-row {
		display: flex;
		align-items: flex-end;
		gap: var(--space-3);
	}
	.hour-row .echo {
		color: var(--muted);
		font-size: 0.85rem;
		padding-bottom: var(--space-2);
	}
	.thumbs {
		display: flex;
		gap: var(--space-2);
		flex-wrap: wrap;
		margin-top: var(--space-1);
	}
	.thumb {
		position: relative;
		width: 64px;
		height: 64px;
		border-radius: var(--radius-md);
		overflow: hidden;
		border: var(--border-width) solid var(--border-color);
	}
	.thumb img {
		width: 100%;
		height: 100%;
		object-fit: cover;
	}
	.rm {
		position: absolute;
		top: 2px;
		right: 2px;
		display: inline-flex;
		padding: 2px;
		border: none;
		border-radius: var(--radius-full);
		background: var(--overlay, rgba(0, 0, 0, 0.6));
		color: #fff;
		cursor: pointer;
	}
</style>

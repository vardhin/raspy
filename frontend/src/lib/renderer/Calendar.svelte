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

	const ID = 'calendar';

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

	// Zoom → minimum card width. Bigger zoom ⇒ wider min ⇒ fewer columns.
	let cardMin = $derived(`${120 + zoom * 60}px`);

	// Weekday tint: a rising gradient Mon→Sun, mixing --accent toward --info by the
	// weekday index. Pure token math, so it re-skins with the theme.
	function tint(weekday: number): string {
		const pct = Math.round((weekday / 6) * 100);
		return `color-mix(in srgb, var(--info) ${pct}%, var(--accent))`;
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
	let formRemind = $state(''); // datetime-local string, '' = no reminder
	let pendingFiles = $state<File[]>([]);
	let uploadBusy = $state(false);
	let fileInput = $state<HTMLInputElement>();

	function openCreate(date: string) {
		editing = null;
		formDate = date;
		formTitle = '';
		formDesc = '';
		formRemind = '';
		pendingFiles = [];
		editorOpen = true;
	}
	function openEdit(entry: Entry) {
		editing = entry;
		formDate = entry.date;
		formTitle = entry.title;
		formDesc = entry.description;
		formRemind = entry.remind_at ? toLocalInput(entry.remind_at) : '';
		pendingFiles = [];
		editorOpen = true;
	}
	function toLocalInput(ts: number): string {
		const d = new Date(ts * 1000);
		const pad = (n: number) => String(n).padStart(2, '0');
		return `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())}T${pad(d.getHours())}:${pad(d.getMinutes())}`;
	}

	async function saveEntry() {
		uploadBusy = true;
		error = null;
		try {
			const remind_at = formRemind ? Math.floor(new Date(formRemind).getTime() / 1000) : null;
			let entry: Entry;
			if (editing) {
				entry = await attAction<Entry>(ID, 'PATCH', `entries/${editing.id}`, {
					date: formDate,
					title: formTitle,
					description: formDesc,
					...(formRemind ? { remind_at } : { clear_remind: true })
				});
			} else {
				entry = await attAction<Entry>(ID, 'POST', 'entries', {
					date: formDate,
					title: formTitle,
					description: formDesc,
					...(remind_at ? { remind_at } : {})
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
		<div class="grid" style:--card-min={cardMin}>
			{#each days as day (day.date)}
				{@const entry = curEntry(day)}
				<Surface
					interactive
					padded={false}
					{...{ style: `--day-tint:${tint(day.weekday)}` }}
				>
					<div class="card" class:today={isToday(day.date)}>
						<!-- Day header strip, tinted by weekday -->
						<div class="day-head">
							<span class="dow">{WEEKDAYS[day.weekday]}</span>
							<span class="dnum">{Number(day.date.slice(8))}</span>
							{#if day.entries.length > 1}
								<span class="multi">
									<button
										aria-label="Previous entry"
										onclick={(e) => {
											e.stopPropagation();
											cycleEntry(day, -1);
										}}><Icon name="chevron-left" size={13} /></button
									>
									{(entryIdx[day.date] ?? 0) + 1}/{day.entries.length}
									<button
										aria-label="Next entry"
										onclick={(e) => {
											e.stopPropagation();
											cycleEntry(day, 1);
										}}><Icon name="chevron-right" size={13} /></button
									>
								</span>
							{/if}
						</div>

						{#if entry}
							{@const imgs = entryImages(entry)}
							{#if imgs.length > 0}
								<Carousel
									items={imgs}
									compact
									rounded={false}
									index={imgIdx[day.date] ?? 0}
									onindex={(i) => (imgIdx[day.date] = i)}
									onactivate={() => openView(entry)}
								/>
							{/if}
							<button class="body" onclick={() => openView(entry)}>
								{#if entry.title}<span class="title">{entry.title}</span>{/if}
								{#if entry.description}
									<span class="desc">{oneLine(entry.description)}</span>
								{/if}
								{#if entry.remind_at && !entry.notified}
									<span class="remind"><Icon name="bell" size={12} /> reminder set</span>
								{/if}
							</button>
						{:else if day.placeholder}
							<!-- Empty day: the daily vibe as a gentle placeholder. -->
							<button
								class="placeholder"
								onclick={() => openCreate(day.date)}
								style:--ph-accent={day.placeholder.accent}
							>
								<img src={day.placeholder.image_url} alt="" loading="lazy" />
								<span class="ph-quote">“{oneLine(day.placeholder.quote)}”</span>
								<span class="ph-add"><Icon name="plus" size={14} /> add entry</span>
							</button>
						{:else}
							<button class="placeholder bare" onclick={() => openCreate(day.date)}>
								<span class="ph-add"><Icon name="plus" size={14} /> add entry</span>
							</button>
						{/if}
					</div>
				</Surface>
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
		<Field
			type="datetime-local"
			label="Remind me (optional)"
			bind:value={formRemind}
		/>

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
		grid-template-columns: repeat(auto-fill, minmax(var(--card-min, 220px), 1fr));
		gap: var(--space-3);
	}
	.card {
		display: flex;
		flex-direction: column;
		overflow: hidden;
		border-radius: var(--radius-lg);
	}
	.card.today {
		outline: 2px solid var(--accent);
		outline-offset: -2px;
		border-radius: var(--radius-lg);
	}
	.day-head {
		display: flex;
		align-items: baseline;
		gap: var(--space-2);
		padding: var(--space-2) var(--space-3);
		/* Weekday rising-gradient tint as a soft header background. */
		background: color-mix(in srgb, var(--day-tint) 22%, transparent);
		border-bottom: var(--border-width) solid
			color-mix(in srgb, var(--day-tint) 40%, var(--border-color));
	}
	.dow {
		font-weight: var(--font-weight-bold);
		color: var(--day-tint);
		font-size: 0.8rem;
		letter-spacing: 0.04em;
		text-transform: uppercase;
	}
	.dnum {
		font-weight: var(--font-weight-bold);
		font-size: 1.1rem;
		color: var(--fg);
	}
	.multi {
		margin-left: auto;
		display: inline-flex;
		align-items: center;
		gap: 2px;
		font-size: 0.75rem;
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
	.body {
		display: flex;
		flex-direction: column;
		gap: var(--space-1);
		padding: var(--space-2) var(--space-3) var(--space-3);
		text-align: left;
		background: none;
		border: none;
		color: var(--fg);
		font: inherit;
		cursor: pointer;
	}
	.title {
		font-weight: var(--font-weight-bold);
		overflow: hidden;
		text-overflow: ellipsis;
		white-space: nowrap;
	}
	.desc {
		color: var(--muted);
		font-size: 0.85rem;
		overflow: hidden;
		text-overflow: ellipsis;
		white-space: nowrap;
	}
	.remind {
		display: inline-flex;
		align-items: center;
		gap: 4px;
		color: var(--accent);
		font-size: 0.75rem;
	}
	.placeholder {
		position: relative;
		display: flex;
		flex-direction: column;
		justify-content: flex-end;
		gap: var(--space-1);
		min-height: 130px;
		padding: var(--space-3);
		border: none;
		cursor: pointer;
		color: var(--fg);
		overflow: hidden;
		background: var(--surface);
	}
	.placeholder img {
		position: absolute;
		inset: 0;
		width: 100%;
		height: 100%;
		object-fit: cover;
		opacity: 0.55;
	}
	.placeholder::after {
		content: '';
		position: absolute;
		inset: 0;
		background: linear-gradient(
			to top,
			color-mix(in srgb, var(--ph-accent, var(--bg)) 80%, transparent),
			transparent 70%
		);
	}
	.placeholder.bare {
		justify-content: center;
		align-items: center;
		min-height: 90px;
		background: var(--surface);
	}
	.placeholder.bare::after {
		display: none;
	}
	.ph-quote {
		position: relative;
		z-index: 1;
		font-size: 0.78rem;
		line-height: 1.3;
		color: var(--fg);
		text-shadow: 0 1px 6px rgba(0, 0, 0, 0.5);
	}
	.ph-add {
		position: relative;
		z-index: 1;
		display: inline-flex;
		align-items: center;
		gap: 4px;
		font-size: 0.75rem;
		color: var(--muted);
		opacity: 0;
		transition: opacity var(--motion-fast) var(--motion-ease);
	}
	.placeholder:hover .ph-add,
	.placeholder.bare .ph-add {
		opacity: 1;
		color: var(--accent);
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

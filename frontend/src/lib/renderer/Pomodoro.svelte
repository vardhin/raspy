<script lang="ts">
	// Pomodoro focus timer. The *session* is server-authoritative (phase, end time,
	// pause state, optional linked todo) so it survives reloads and device switches;
	// the backend also fires a notification when a phase ends (even with no client
	// open). This component renders a beautiful animated countdown, picks a todo to
	// focus on (read from the todo attachment), and on Start enters an immersive
	// fullscreen view (real Fullscreen API where allowed, full-viewport overlay
	// otherwise) with an Esc/exit control.
	import { onMount } from 'svelte';
	import { Surface, Stack, Text, Button, Icon, Slider } from '$lib/components';
	import { attGet, attAction } from '$lib/api';
	import { connection } from '$lib/connection.svelte';

	type Phase = 'work' | 'break';
	type State = {
		phase: Phase;
		running: boolean;
		ends_at: number | null;
		remaining: number; // seconds, as of the server snapshot
		duration: number; // seconds for the whole phase
		notified: boolean;
		todo_id: number | null;
		todo_title: string | null;
		work_minutes: number;
		break_minutes: number;
	};
	type Todo = { id: number; title: string; done: boolean };

	const ID = 'pomodoro';

	let session = $state<State | null>(null);
	let loading = $state(true);
	let error = $state<string | null>(null);
	let todos = $state<Todo[]>([]);
	let pickedTodo = $state<Todo | null>(null);
	let showSettings = $state(false);
	let fullscreen = $state(false);
	let containerEl = $state<HTMLDivElement | null>(null);

	// A local clock so the ring animates smoothly between server snapshots. We
	// recompute `remaining` from `ends_at` while running; while paused we hold the
	// server's `remaining`. `nowTick` just forces a re-render each second.
	let nowTick = $state(Date.now());

	let remaining = $derived.by(() => {
		if (!session) return 0;
		if (session.running && session.ends_at != null) {
			return Math.max(0, session.ends_at - nowTick / 1000);
		}
		return Math.max(0, session.remaining);
	});
	let duration = $derived(session?.duration || (session ? phaseSeconds(session) : 1));
	let progress = $derived(duration > 0 ? 1 - remaining / duration : 0);
	let isWork = $derived((session?.phase ?? 'work') === 'work');
	// A finished phase: not running, no remaining, and a duration was set.
	let finished = $derived(
		!!session && !session.running && session.remaining <= 0 && session.notified
	);

	function phaseSeconds(s: State): number {
		return (s.phase === 'work' ? s.work_minutes : s.break_minutes) * 60;
	}

	function fmt(secs: number): string {
		const s = Math.max(0, Math.round(secs));
		const m = Math.floor(s / 60);
		const r = s % 60;
		return `${String(m).padStart(2, '0')}:${String(r).padStart(2, '0')}`;
	}

	async function load() {
		try {
			session = await attGet<State>(ID, 'state');
			error = null;
		} catch (e) {
			error = e instanceof Error ? e.message : 'failed to load the timer';
		} finally {
			loading = false;
		}
	}

	async function loadTodos() {
		try {
			const all = await attGet<Todo[]>('todo', 'items');
			todos = all.filter((t) => !t.done);
			// Keep the picker in sync with what the session is linked to.
			if (session?.todo_id != null) {
				pickedTodo = todos.find((t) => t.id === session!.todo_id) ?? pickedTodo;
			}
		} catch {
			todos = []; // todo app might be disabled for this account — that's fine
		}
	}

	async function start(phase: Phase = session?.phase ?? 'work') {
		session = await attAction<State>(ID, 'POST', 'start', {
			phase,
			todo_id: pickedTodo?.id ?? null,
			todo_title: pickedTodo?.title ?? null
		});
		await enterFullscreen();
	}

	async function pause() {
		session = await attAction<State>(ID, 'POST', 'pause');
	}
	async function resume() {
		session = await attAction<State>(ID, 'POST', 'resume');
		await enterFullscreen();
	}
	async function reset() {
		session = await attAction<State>(ID, 'POST', 'reset');
	}

	// The phase the "next" button should start after a finish.
	function nextPhase(): Phase {
		return isWork ? 'break' : 'work';
	}

	async function saveSettings(work: number, brk: number) {
		session = {
			...(session as State),
			work_minutes: work,
			break_minutes: brk
		};
		await attAction(ID, 'PUT', 'settings', {
			work_minutes: work,
			break_minutes: brk
		});
	}

	// --- fullscreen ----------------------------------------------------------

	async function enterFullscreen() {
		fullscreen = true;
		// Try the real Fullscreen API for a truly immersive view; fall back to the
		// full-viewport overlay (the `fullscreen` flag) when it's unavailable or
		// blocked (e.g. not from a user gesture, or in an iframe without allow).
		try {
			if (containerEl && !document.fullscreenElement) {
				await containerEl.requestFullscreen?.();
			}
		} catch {
			/* overlay fallback already active */
		}
	}

	async function exitFullscreen() {
		fullscreen = false;
		try {
			if (document.fullscreenElement) await document.exitFullscreen();
		} catch {
			/* ignore */
		}
	}

	function onKey(e: KeyboardEvent) {
		if (e.key === 'Escape' && fullscreen) exitFullscreen();
	}

	function onFsChange() {
		// If the user leaves browser-fullscreen (Esc/F11), drop our overlay too —
		// but only when we actually were in real fullscreen (avoid clobbering the
		// overlay-only fallback).
		if (!document.fullscreenElement && fullscreen && wasRealFs) {
			fullscreen = false;
		}
		wasRealFs = !!document.fullscreenElement;
	}
	let wasRealFs = $state(false);

	onMount(() => {
		void load();
		void loadTodos();
		const off = connection.onEvent((topic) => {
			if (topic.startsWith(`${ID}.`)) void load();
			if (topic.startsWith('todo.')) void loadTodos();
		});
		const tick = setInterval(() => (nowTick = Date.now()), 250);
		document.addEventListener('keydown', onKey);
		document.addEventListener('fullscreenchange', onFsChange);
		return () => {
			off();
			clearInterval(tick);
			document.removeEventListener('keydown', onKey);
			document.removeEventListener('fullscreenchange', onFsChange);
		};
	});

	// Ring geometry.
	const R = 130;
	const C = 2 * Math.PI * R;
	let dash = $derived(C * (1 - progress));
</script>

<div
	class="pomodoro"
	class:fullscreen
	class:work={isWork}
	class:break={!isWork}
	bind:this={containerEl}
>
	{#if loading && !session}
		<Text role="muted">Loading the timer…</Text>
	{:else if error && !session}
		<Surface level={2}>
			<Stack gap={2} align="center">
				<Icon name="clock4" size={28} />
				<Text role="heading">Couldn't load the timer</Text>
				<Text role="muted">{error}</Text>
				<Button onclick={load}>Try again</Button>
			</Stack>
		</Surface>
	{:else if session}
		<div class="stage">
			<!-- Phase + linked todo -->
			<div class="meta">
				<span class="phase-pill">{isWork ? 'Focus' : 'Break'}</span>
				{#if session.todo_title}
					<span class="focus-on" title={session.todo_title}>
						<Icon name="check-square" size={15} />
						{session.todo_title}
					</span>
				{/if}
			</div>

			<!-- The ring -->
			<div class="ring-wrap">
				<svg viewBox="0 0 300 300" class="ring">
					<circle class="track" cx="150" cy="150" r={R} />
					<circle
						class="bar"
						cx="150"
						cy="150"
						r={R}
						stroke-dasharray={C}
						stroke-dashoffset={dash}
						transform="rotate(-90 150 150)"
					/>
				</svg>
				<div class="readout">
					<div class="time">{fmt(remaining)}</div>
					{#if finished}
						<div class="done-label">{isWork ? 'Session done' : 'Break over'}</div>
					{:else}
						<div class="sub">{session.running ? 'running' : 'paused'}</div>
					{/if}
				</div>
			</div>

			<!-- Controls -->
			<div class="controls">
				{#if finished}
					<Button onclick={() => start(nextPhase())}>
						<Icon name="play" size={18} />
						Start {nextPhase() === 'work' ? 'focus' : 'break'}
					</Button>
					<Button variant="ghost" onclick={reset}>
						<Icon name="refresh-cw" size={18} /> Reset
					</Button>
				{:else if session.running}
					<Button onclick={pause}>
						<Icon name="pause" size={18} /> Pause
					</Button>
					<Button variant="ghost" onclick={reset}>
						<Icon name="refresh-cw" size={18} /> Reset
					</Button>
				{:else if remaining > 0 && remaining < duration}
					<Button onclick={resume}>
						<Icon name="play" size={18} /> Resume
					</Button>
					<Button variant="ghost" onclick={reset}>
						<Icon name="refresh-cw" size={18} /> Reset
					</Button>
				{:else}
					<Button onclick={() => start('work')}>
						<Icon name="play" size={18} /> Start focus
					</Button>
				{/if}

				{#if fullscreen}
					<Button variant="ghost" onclick={exitFullscreen}>
						<Icon name="minimize" size={18} /> Exit
					</Button>
				{:else}
					<Button variant="ghost" onclick={enterFullscreen}>
						<Icon name="maximize" size={18} /> Fullscreen
					</Button>
				{/if}
			</div>

			{#if !fullscreen}
				<!-- Focus target picker (hidden in the immersive view) -->
				{#if todos.length > 0}
					<div class="picker">
						<Text role="label">Focus on</Text>
						<div class="chips">
							<button
								class="chip"
								class:active={pickedTodo === null}
								onclick={() => (pickedTodo = null)}>Nothing in particular</button
							>
							{#each todos as t (t.id)}
								<button
									class="chip"
									class:active={pickedTodo?.id === t.id}
									onclick={() => (pickedTodo = t)}>{t.title}</button
								>
							{/each}
						</div>
					</div>
				{/if}

				<!-- Settings -->
				<button class="settings-toggle" onclick={() => (showSettings = !showSettings)}>
					<Icon name={showSettings ? 'chevron-up' : 'chevron-down'} size={16} />
					Durations · {session.work_minutes}m focus / {session.break_minutes}m break
				</button>
				{#if showSettings}
					<Surface level={2}>
						<Stack gap={3}>
							<Slider
								label={`Focus: ${session.work_minutes} min`}
								min={1}
								max={120}
								value={session.work_minutes}
								oninput={(v) => saveSettings(v, session!.break_minutes)}
							/>
							<Slider
								label={`Break: ${session.break_minutes} min`}
								min={1}
								max={60}
								value={session.break_minutes}
								oninput={(v) => saveSettings(session!.work_minutes, v)}
							/>
						</Stack>
					</Surface>
				{/if}
			{/if}
		</div>
	{/if}
</div>

<style>
	.pomodoro {
		--accent-phase: var(--accent);
		position: relative;
		display: flex;
		align-items: center;
		justify-content: center;
		min-height: min(80dvh, 760px);
		padding: var(--space-4);
		border-radius: var(--radius-lg);
		background: radial-gradient(
			120% 90% at 50% 0%,
			color-mix(in srgb, var(--accent-phase) 35%, var(--bg)) 0%,
			var(--bg) 72%
		);
		transition: background var(--motion-base) var(--motion-ease);
	}
	/* Break phase tints toward success (calm green), focus toward accent. */
	.pomodoro.work {
		--accent-phase: var(--accent);
	}
	.pomodoro.break {
		--accent-phase: var(--success);
	}
	/* Overlay fallback (and the styling for real fullscreen, which also matches
	   :fullscreen). Fills the viewport, sits above app chrome. */
	.pomodoro.fullscreen {
		position: fixed;
		inset: 0;
		z-index: 1000;
		min-height: 100dvh;
		border-radius: 0;
	}
	.pomodoro:fullscreen {
		min-height: 100dvh;
		border-radius: 0;
	}
	.stage {
		display: flex;
		flex-direction: column;
		align-items: center;
		gap: clamp(var(--space-3), 3vh, var(--space-5));
		width: min(560px, 100%);
	}
	.meta {
		display: flex;
		flex-direction: column;
		align-items: center;
		gap: var(--space-2);
		text-align: center;
	}
	.phase-pill {
		text-transform: uppercase;
		letter-spacing: 0.18em;
		font-size: 0.8rem;
		font-weight: var(--font-weight-bold);
		color: var(--accent-phase);
		padding: var(--space-1) var(--space-3);
		border: var(--border-width) solid var(--accent-phase);
		border-radius: var(--radius-full);
	}
	.focus-on {
		display: inline-flex;
		align-items: center;
		gap: var(--space-1);
		color: var(--muted);
		max-width: 36ch;
		overflow: hidden;
		text-overflow: ellipsis;
		white-space: nowrap;
	}
	.ring-wrap {
		position: relative;
		width: min(70vw, 320px);
		aspect-ratio: 1;
	}
	.ring {
		width: 100%;
		height: 100%;
		display: block;
		/* The bar's drop-shadow glow extends past the viewBox edge; without this
		   the SVG box clips it into a hard border. */
		overflow: visible;
	}
	.ring .track {
		fill: none;
		stroke: color-mix(in srgb, var(--fg) 12%, transparent);
		stroke-width: 14;
	}
	.ring .bar {
		fill: none;
		stroke: var(--accent-phase);
		stroke-width: 14;
		stroke-linecap: round;
		transition: stroke-dashoffset 0.35s linear;
		filter: drop-shadow(0 0 14px color-mix(in srgb, var(--accent-phase) 60%, transparent));
	}
	.readout {
		position: absolute;
		inset: 0;
		display: flex;
		flex-direction: column;
		align-items: center;
		justify-content: center;
		gap: var(--space-1);
	}
	.time {
		font-size: clamp(2.6rem, 11vw, 4.6rem);
		font-weight: var(--font-weight-bold);
		font-variant-numeric: tabular-nums;
		line-height: 1;
		color: var(--fg);
	}
	.sub {
		text-transform: uppercase;
		letter-spacing: 0.16em;
		font-size: 0.75rem;
		color: var(--muted);
	}
	.done-label {
		color: var(--accent-phase);
		font-weight: var(--font-weight-bold);
	}
	.controls {
		display: flex;
		gap: var(--space-2);
		flex-wrap: wrap;
		justify-content: center;
	}
	.picker {
		width: 100%;
		display: flex;
		flex-direction: column;
		gap: var(--space-2);
		align-items: center;
	}
	.chips {
		display: flex;
		flex-wrap: wrap;
		gap: var(--space-2);
		justify-content: center;
		max-height: 7.5rem;
		overflow-y: auto;
	}
	.chip {
		font: inherit;
		cursor: pointer;
		padding: var(--space-1) var(--space-3);
		border-radius: var(--radius-full);
		border: var(--border-width) solid var(--border-color);
		background: color-mix(in srgb, var(--surface) calc(var(--surface-alpha) * 100%), transparent);
		color: var(--fg);
		max-width: 22ch;
		overflow: hidden;
		text-overflow: ellipsis;
		white-space: nowrap;
		transition:
			border-color var(--motion-fast) var(--motion-ease),
			background var(--motion-fast) var(--motion-ease);
	}
	.chip.active {
		border-color: var(--accent-phase);
		background: color-mix(in srgb, var(--accent-phase) 22%, transparent);
	}
	.settings-toggle {
		font: inherit;
		cursor: pointer;
		display: inline-flex;
		align-items: center;
		gap: var(--space-1);
		background: none;
		border: none;
		color: var(--muted);
	}
</style>

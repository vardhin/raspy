<script lang="ts">
	// Notes — markdown notes in a list that open into a code-editor-style editor.
	//
	//   • List view (default) — every note as a card with its title + a short body
	//     preview. A "New note" button and a per-card Edit/Delete.
	//   • Editor view — a full editor for one note: a monospace text pane, a live
	//     markdown preview, and a toolbar of preferences (editable editor font +
	//     size, line-wrap toggle, line-number gutter toggle) plus a live word count.
	//
	// The body is plaintext markdown; rendering is done in-browser (small renderer
	// below — no markdown dependency). Editor preferences persist per-device in the
	// kv store. Text measurement (word/line counts, wrapped height) uses
	// @chenglou/pretext so we never touch the DOM to size things.
	import { onMount, onDestroy } from 'svelte';
	import { prepare, layout } from '@chenglou/pretext';
	import { Surface, Stack, Text, Button, Icon, Field, SegmentedControl, Slider } from '$lib/components';
	import { attGet, attAction } from '$lib/api';
	import { connection } from '$lib/connection.svelte';
	import { kvGet, kvSet } from '$lib/kv';

	const ID = 'notes';
	const PREFS_KEY = 'notes:prefs';

	type Note = {
		id: number;
		title: string;
		body: string;
		created: number;
		updated: number;
	};

	type EditorMode = 'edit' | 'split' | 'preview';

	type Prefs = {
		font: string;
		fontSize: number;
		wrap: boolean;
		lineNumbers: boolean;
		mode: EditorMode;
	};

	// A small set of safe, broadly-available monospace stacks to pick from.
	const FONTS: { value: string; label: string }[] = [
		{ value: 'ui-monospace, SFMono-Regular, Menlo, Consolas, monospace', label: 'System mono' },
		{ value: '"JetBrains Mono", ui-monospace, monospace', label: 'JetBrains Mono' },
		{ value: '"Fira Code", ui-monospace, monospace', label: 'Fira Code' },
		{ value: '"Source Code Pro", ui-monospace, monospace', label: 'Source Code Pro' },
		{ value: 'Georgia, "Times New Roman", serif', label: 'Serif (prose)' },
		{ value: 'system-ui, sans-serif', label: 'Sans (prose)' }
	];

	const DEFAULT_PREFS: Prefs = {
		font: FONTS[0].value,
		fontSize: 15,
		wrap: true,
		lineNumbers: true,
		mode: 'split'
	};

	let prefs = $state<Prefs>({ ...DEFAULT_PREFS });

	let notes = $state<Note[]>([]);
	let loading = $state(true);
	let error = $state<string | null>(null);

	// null = list view. Otherwise we're in the editor: `editing` is the note being
	// edited (or null for a brand-new note), with the working copy in the fields.
	let inEditor = $state(false);
	let editing = $state<Note | null>(null);
	let formTitle = $state('');
	let formBody = $state('');
	let saving = $state(false);
	// Baseline (last saved/loaded) values; `dirty` is the diff against them.
	let baseTitle = $state('');
	let baseBody = $state('');
	const dirty = $derived(formTitle !== baseTitle || formBody !== baseBody);

	// --- data ----------------------------------------------------------------
	async function load() {
		loading = true;
		error = null;
		try {
			notes = await attGet<Note[]>(ID, 'notes');
		} catch (e) {
			error = e instanceof Error ? e.message : 'failed to load notes';
		} finally {
			loading = false;
		}
	}

	function openCreate() {
		editing = null;
		formTitle = baseTitle = '';
		formBody = baseBody = '';
		inEditor = true;
	}

	function openEdit(n: Note) {
		editing = n;
		formTitle = baseTitle = n.title;
		formBody = baseBody = n.body;
		inEditor = true;
	}

	function closeEditor() {
		if (dirty && !confirm('Discard unsaved changes?')) return;
		inEditor = false;
		editing = null;
	}

	async function save() {
		const title = formTitle.trim();
		if (!title) {
			error = 'A title is required.';
			return;
		}
		saving = true;
		error = null;
		try {
			const body = { title, body: formBody };
			if (editing) {
				const updated = await attAction<Note>(ID, 'PATCH', `notes/${editing.id}`, body);
				editing = updated;
			} else {
				const created = await attAction<Note>(ID, 'POST', 'notes', body);
				editing = created;
			}
			// New baseline = what we just persisted (title was trimmed on save).
			baseTitle = formTitle = editing.title;
			baseBody = formBody = editing.body;
			await load();
		} catch (e) {
			error = e instanceof Error ? e.message : 'failed to save note';
		} finally {
			saving = false;
		}
	}

	async function remove(n: Note) {
		if (!confirm(`Delete “${n.title}”? This cannot be undone.`)) return;
		try {
			await attAction(ID, 'DELETE', `notes/${n.id}`);
			if (editing?.id === n.id) {
				inEditor = false;
				editing = null;
			}
			await load();
		} catch (e) {
			error = e instanceof Error ? e.message : 'failed to delete note';
		}
	}

	// --- preferences (persisted) ---------------------------------------------
	let prefsLoaded = false;
	$effect(() => {
		// Snapshot deps so the effect re-runs on any pref change.
		const snap = JSON.stringify(prefs);
		if (!prefsLoaded) return;
		void kvSet(PREFS_KEY, JSON.parse(snap) as Prefs);
	});

	// --- counts & measurement (pretext) --------------------------------------
	// Word/char/line counts of the working body. pretext gives us a DOM-free,
	// reflow-free wrapped-line count for the gutter + a "wrapped lines" readout.
	const charCount = $derived(formBody.length);
	const wordCount = $derived(formBody.trim() ? formBody.trim().split(/\s+/).length : 0);
	const logicalLines = $derived(formBody === '' ? 0 : formBody.split('\n').length);

	// Width (px) the textarea wraps at — measured once via ResizeObserver.
	let editorTextWidth = $state(0);
	let textareaEl: HTMLTextAreaElement | undefined = $state();
	$effect(() => {
		const el = textareaEl;
		if (!el) return;
		const ro = new ResizeObserver((entries) => {
			const cr = entries[0]?.contentRect;
			if (cr && cr.width > 0) editorTextWidth = cr.width;
		});
		ro.observe(el);
		return () => ro.disconnect();
	});

	const lineHeightPx = $derived(Math.round(prefs.fontSize * 1.6));
	const fontSpec = $derived(`${prefs.fontSize}px ${prefs.font}`);

	// Wrapped line count: when wrap is on we lay the body out with pretext to learn
	// how many visual rows it occupies; otherwise it's just the logical line count.
	const wrappedLines = $derived.by(() => {
		if (!prefs.wrap || editorTextWidth <= 0 || formBody === '') return logicalLines;
		try {
			const prepared = prepare(formBody, fontSpec, { whiteSpace: 'pre-wrap' });
			const { lineCount } = layout(prepared, editorTextWidth, lineHeightPx);
			return lineCount;
		} catch {
			return logicalLines;
		}
	});

	// The gutter shows one number per logical line. Each line's pretext-measured
	// wrapped height tells us how tall its gutter cell must be so numbers stay
	// aligned with their line even when a line wraps onto several rows.
	const gutter = $derived.by(() => {
		if (!prefs.lineNumbers) return [];
		const lines = formBody.split('\n');
		return lines.map((line, i) => {
			let rows = 1;
			if (prefs.wrap && editorTextWidth > 0 && line !== '') {
				try {
					const prepared = prepare(line, fontSpec, { whiteSpace: 'pre-wrap' });
					rows = Math.max(1, layout(prepared, editorTextWidth, lineHeightPx).lineCount);
				} catch {
					rows = 1;
				}
			}
			return { n: i + 1, height: rows * lineHeightPx };
		});
	});

	// --- markdown (tiny in-browser renderer) ---------------------------------
	function escapeHtml(s: string): string {
		return s
			.replace(/&/g, '&amp;')
			.replace(/</g, '&lt;')
			.replace(/>/g, '&gt;')
			.replace(/"/g, '&quot;');
	}

	// Inline: code, bold, italic, links. Operates on already-escaped text.
	function inline(s: string): string {
		return s
			.replace(/`([^`]+)`/g, (_m, c) => `<code>${c}</code>`)
			.replace(/\*\*([^*]+)\*\*/g, '<strong>$1</strong>')
			.replace(/(^|[^*])\*([^*\n]+)\*/g, '$1<em>$2</em>')
			.replace(/\[([^\]]+)\]\((https?:[^)\s]+)\)/g, '<a href="$2" target="_blank" rel="noopener noreferrer">$1</a>');
	}

	// Block-level: headings, fenced code, blockquotes, lists, hr, paragraphs.
	function renderMarkdown(src: string): string {
		const lines = src.split('\n');
		const out: string[] = [];
		let i = 0;
		let para: string[] = [];

		const flushPara = () => {
			if (para.length) {
				out.push(`<p>${inline(escapeHtml(para.join(' ')))}</p>`);
				para = [];
			}
		};

		while (i < lines.length) {
			const line = lines[i];

			// Fenced code block.
			if (/^```/.test(line)) {
				flushPara();
				const code: string[] = [];
				i++;
				while (i < lines.length && !/^```/.test(lines[i])) code.push(lines[i++]);
				i++; // closing fence
				out.push(`<pre><code>${escapeHtml(code.join('\n'))}</code></pre>`);
				continue;
			}

			// Horizontal rule.
			if (/^\s*([-*_])(\s*\1){2,}\s*$/.test(line)) {
				flushPara();
				out.push('<hr />');
				i++;
				continue;
			}

			// Heading.
			const h = line.match(/^(#{1,6})\s+(.*)$/);
			if (h) {
				flushPara();
				const level = h[1].length;
				out.push(`<h${level}>${inline(escapeHtml(h[2]))}</h${level}>`);
				i++;
				continue;
			}

			// Blockquote (one level).
			if (/^>\s?/.test(line)) {
				flushPara();
				const quote: string[] = [];
				while (i < lines.length && /^>\s?/.test(lines[i])) quote.push(lines[i++].replace(/^>\s?/, ''));
				out.push(`<blockquote>${inline(escapeHtml(quote.join(' ')))}</blockquote>`);
				continue;
			}

			// Unordered / ordered list.
			if (/^\s*([-*+]|\d+\.)\s+/.test(line)) {
				flushPara();
				const ordered = /^\s*\d+\./.test(line);
				const items: string[] = [];
				while (i < lines.length && /^\s*([-*+]|\d+\.)\s+/.test(lines[i])) {
					items.push(lines[i].replace(/^\s*([-*+]|\d+\.)\s+/, ''));
					i++;
				}
				const tag = ordered ? 'ol' : 'ul';
				out.push(`<${tag}>${items.map((it) => `<li>${inline(escapeHtml(it))}</li>`).join('')}</${tag}>`);
				continue;
			}

			// Blank line ends a paragraph.
			if (line.trim() === '') {
				flushPara();
				i++;
				continue;
			}

			para.push(line);
			i++;
		}
		flushPara();
		return out.join('\n');
	}

	const previewHtml = $derived(renderMarkdown(formBody));

	// --- lifecycle ------------------------------------------------------------
	onMount(() => {
		void kvGet<Prefs>(PREFS_KEY).then((p) => {
			if (p) prefs = { ...DEFAULT_PREFS, ...p };
			prefsLoaded = true;
		});
		void load();
		const off = connection.onEvent((topic) => {
			// Refresh the list on any notes.* event, but don't clobber the editor.
			if (topic.startsWith('notes.') && !inEditor) void load();
		});
		return () => off();
	});
	onDestroy(() => {});

	function preview(body: string): string {
		const text = body.replace(/[#>*`_\-]/g, '').replace(/\s+/g, ' ').trim();
		return text.length > 140 ? text.slice(0, 140) + '…' : text;
	}

	function fmtDate(s: number): string {
		return new Date(s * 1000).toLocaleDateString(undefined, {
			month: 'short',
			day: 'numeric',
			year: 'numeric'
		});
	}
</script>

{#if !inEditor}
	<!-- ============================ LIST VIEW ============================ -->
	<Stack gap={3}>
		<Surface level={2}>
			<div class="bar">
				<Text role="heading">Notes</Text>
				<Button onclick={openCreate}>
					<Icon name="plus" size={16} /> New note
				</Button>
			</div>
		</Surface>

		{#if error}<span class="err">{error}</span>{/if}

		{#if loading && notes.length === 0}
			<Text role="muted">Loading…</Text>
		{:else if notes.length === 0}
			<Surface level={1}>
				<Stack gap={2} align="center">
					<Icon name="file-text" size={28} />
					<Text role="heading">No notes yet</Text>
					<Text role="muted">Capture a thought — markdown is supported.</Text>
					<Button onclick={openCreate}><Icon name="plus" size={15} /> New note</Button>
				</Stack>
			</Surface>
		{:else}
			<div class="grid">
				{#each notes as n (n.id)}
					<Surface interactive onclick={() => openEdit(n)}>
						<Stack gap={2}>
							<Stack direction="row" gap={2} justify="between" align="start">
								<Text role="heading">{n.title}</Text>
								<div class="card-actions">
									<Button variant="ghost" size="sm" onclick={(e) => { e.stopPropagation(); openEdit(n); }}>
										<Icon name="edit" size={14} /> Edit
									</Button>
									<Button variant="danger" size="sm" onclick={(e) => { e.stopPropagation(); remove(n); }}>
										<Icon name="trash" size={14} />
									</Button>
								</div>
							</Stack>
							{#if preview(n.body)}
								<Text role="muted">{preview(n.body)}</Text>
							{/if}
							<Text role="muted"><span class="meta">{fmtDate(n.updated)}</span></Text>
						</Stack>
					</Surface>
				{/each}
			</div>
		{/if}
	</Stack>
{:else}
	<!-- ============================ EDITOR VIEW ============================ -->
	<div class="editor">
		<!-- Topbar: back, title, save -->
		<div class="topbar">
			<Button variant="ghost" onclick={closeEditor}>
				<Icon name="chevron-left" size={16} /> Notes
			</Button>
			<div class="title-field">
				<Field placeholder="Untitled note" bind:value={formTitle} />
			</div>
			<Button onclick={save} disabled={saving || !dirty}>
				{saving ? 'Saving…' : dirty ? 'Save' : 'Saved'}
			</Button>
		</div>

		{#if error}<span class="err">{error}</span>{/if}

		<!-- Toolbar: mode + editor preferences -->
		<div class="toolbar">
			<SegmentedControl
				bind:value={prefs.mode}
				options={[
					{ value: 'edit', label: 'Edit' },
					{ value: 'split', label: 'Split' },
					{ value: 'preview', label: 'Preview' }
				]}
			/>
			<div class="opts">
				<label class="opt">
					<span>Font</span>
					<select class="opt-select" bind:value={prefs.font}>
						{#each FONTS as f (f.value)}
							<option value={f.value}>{f.label}</option>
						{/each}
					</select>
				</label>
				<div class="opt size">
					<span>Size</span>
					<div class="size-slider">
						<Slider bind:value={prefs.fontSize} min={11} max={28} step={1} />
					</div>
					<span class="size-val">{prefs.fontSize}px</span>
				</div>
				<button class="toggle" class:on={prefs.wrap} onclick={() => (prefs.wrap = !prefs.wrap)} title="Toggle line wrap">
					<Icon name="wrap-text" size={15} /> Wrap
				</button>
				<button class="toggle" class:on={prefs.lineNumbers} onclick={() => (prefs.lineNumbers = !prefs.lineNumbers)} title="Toggle line numbers">
					<Icon name="hash" size={15} /> Lines
				</button>
			</div>
		</div>

		<!-- Panes -->
		<div class="panes" class:split={prefs.mode === 'split'}>
			{#if prefs.mode !== 'preview'}
				<div class="pane code-pane" class:full={prefs.mode === 'edit'}>
					{#if prefs.lineNumbers}
						<div class="gutter" style:font={fontSpec} style:line-height={`${lineHeightPx}px`}>
							{#each gutter as g (g.n)}
								<div class="gutter-line" style:height={`${g.height}px`}>{g.n}</div>
							{/each}
						</div>
					{/if}
					<textarea
						bind:this={textareaEl}
						class="code"
						class:nowrap={!prefs.wrap}
						style:font={fontSpec}
						style:line-height={`${lineHeightPx}px`}
						placeholder="# Title&#10;&#10;Write in **markdown**…"
						bind:value={formBody}
						spellcheck="false"
					></textarea>
				</div>
			{/if}
			{#if prefs.mode !== 'edit'}
				<div class="pane preview-pane" class:full={prefs.mode === 'preview'}>
					{#if formBody.trim() === ''}
						<Text role="muted">Nothing to preview yet.</Text>
					{:else}
						<!-- Sanitized: renderMarkdown HTML-escapes all text; only the tags
						     it emits itself reach the DOM. -->
						<div class="markdown">{@html previewHtml}</div>
					{/if}
				</div>
			{/if}
		</div>

		<!-- Status bar -->
		<div class="statusbar">
			<span>{wordCount} {wordCount === 1 ? 'word' : 'words'}</span>
			<span>{charCount} chars</span>
			<span>{logicalLines} {logicalLines === 1 ? 'line' : 'lines'}</span>
			{#if prefs.wrap && wrappedLines !== logicalLines}
				<span>{wrappedLines} wrapped</span>
			{/if}
			{#if editing}
				<span class="status-right">Edited {fmtDate(editing.updated)}</span>
			{:else}
				<span class="status-right">New note</span>
			{/if}
		</div>
	</div>
{/if}

<style>
	.bar {
		display: flex;
		align-items: center;
		justify-content: space-between;
		gap: var(--space-3);
		flex-wrap: wrap;
	}
	.err {
		color: var(--danger);
		font-size: 0.9rem;
	}

	/* --- list --------------------------------------------------------------- */
	.grid {
		display: grid;
		grid-template-columns: repeat(auto-fill, minmax(240px, 1fr));
		gap: var(--space-3);
	}
	.card-actions {
		display: flex;
		gap: var(--space-1);
		flex: none;
	}
	.meta {
		font-size: 0.75rem;
	}

	/* --- editor ------------------------------------------------------------- */
	.editor {
		display: flex;
		flex-direction: column;
		gap: var(--space-3);
		height: calc(100dvh - var(--space-6, 2rem));
		min-height: 0;
	}
	.topbar {
		display: flex;
		align-items: center;
		gap: var(--space-3);
	}
	.title-field {
		flex: 1;
		min-width: 0;
	}
	.toolbar {
		display: flex;
		align-items: center;
		justify-content: space-between;
		gap: var(--space-3);
		flex-wrap: wrap;
	}
	.opts {
		display: flex;
		align-items: center;
		gap: var(--space-3);
		flex-wrap: wrap;
	}
	.opt {
		display: inline-flex;
		align-items: center;
		gap: var(--space-2);
		color: var(--muted);
		font-size: 0.85rem;
	}
	.opt-select {
		border: var(--border-width) solid var(--border-color);
		border-radius: var(--radius-md);
		background: color-mix(in srgb, var(--surface-2) calc(var(--surface-alpha, 1) * 100%), transparent);
		color: var(--fg);
		font: inherit;
		padding: var(--space-1) var(--space-2);
		outline: none;
	}
	.opt.size {
		gap: var(--space-2);
	}
	.size-slider {
		width: 110px;
	}
	.size-val {
		min-width: 2.6rem;
		text-align: right;
		font-variant-numeric: tabular-nums;
	}
	.toggle {
		display: inline-flex;
		align-items: center;
		gap: var(--space-1);
		padding: var(--space-1) var(--space-2);
		border: var(--border-width) solid var(--border-color);
		border-radius: var(--radius-md);
		background: transparent;
		color: var(--muted);
		font: inherit;
		font-size: 0.85rem;
		cursor: pointer;
		transition:
			color var(--motion-fast) var(--motion-ease),
			border-color var(--motion-fast) var(--motion-ease),
			background var(--motion-fast) var(--motion-ease);
	}
	.toggle.on {
		color: var(--on-accent, #fff);
		background: var(--accent);
		border-color: var(--accent);
	}

	.panes {
		display: flex;
		flex: 1;
		min-height: 0;
		gap: var(--space-3);
	}
	.pane {
		flex: 1;
		min-width: 0;
		min-height: 0;
		border: var(--border-width) solid var(--border-color);
		border-radius: var(--radius-lg);
		background: color-mix(in srgb, var(--surface) calc(var(--surface-alpha, 1) * 100%), transparent);
		box-shadow: var(--shadow-sm);
		backdrop-filter: blur(var(--blur));
		-webkit-backdrop-filter: blur(var(--blur));
		overflow: hidden;
	}
	.pane.full {
		flex: 1 1 100%;
	}

	/* code pane: gutter + textarea share metrics so numbers track lines */
	.code-pane {
		display: flex;
		overflow: auto;
	}
	.gutter {
		flex: none;
		padding: var(--space-3) var(--space-2);
		text-align: right;
		color: var(--muted);
		opacity: 0.7;
		user-select: none;
		border-right: var(--border-width) solid var(--border-color);
		background: color-mix(in srgb, var(--surface-2) calc(var(--surface-alpha, 1) * 60%), transparent);
	}
	.gutter-line {
		box-sizing: border-box;
	}
	.code {
		flex: 1;
		min-width: 0;
		border: none;
		outline: none;
		resize: none;
		background: transparent;
		color: var(--fg);
		padding: var(--space-3);
		white-space: pre-wrap;
		overflow-wrap: anywhere;
		tab-size: 4;
	}
	.code.nowrap {
		white-space: pre;
		overflow-wrap: normal;
	}

	.preview-pane {
		padding: var(--space-3);
		overflow: auto;
	}

	/* rendered markdown */
	.markdown {
		color: var(--fg);
		line-height: 1.6;
		word-break: break-word;
	}
	.markdown :global(h1),
	.markdown :global(h2),
	.markdown :global(h3),
	.markdown :global(h4),
	.markdown :global(h5),
	.markdown :global(h6) {
		margin: 1.2em 0 0.5em;
		line-height: 1.25;
	}
	.markdown :global(h1:first-child),
	.markdown :global(h2:first-child) {
		margin-top: 0;
	}
	.markdown :global(p) {
		margin: 0 0 0.8em;
	}
	.markdown :global(ul),
	.markdown :global(ol) {
		margin: 0 0 0.8em;
		padding-left: 1.4em;
	}
	.markdown :global(li) {
		margin: 0.2em 0;
	}
	.markdown :global(blockquote) {
		margin: 0 0 0.8em;
		padding: 0.2em 0 0.2em 1em;
		border-left: 3px solid var(--accent);
		color: var(--muted);
	}
	.markdown :global(code) {
		font-family: ui-monospace, SFMono-Regular, Menlo, Consolas, monospace;
		font-size: 0.9em;
		padding: 0.1em 0.35em;
		border-radius: var(--radius-sm);
		background: color-mix(in srgb, var(--surface-2) calc(var(--surface-alpha, 1) * 100%), transparent);
	}
	.markdown :global(pre) {
		margin: 0 0 0.8em;
		padding: var(--space-3);
		border-radius: var(--radius-md);
		background: color-mix(in srgb, var(--surface-2) calc(var(--surface-alpha, 1) * 100%), transparent);
		overflow-x: auto;
	}
	.markdown :global(pre code) {
		padding: 0;
		background: none;
	}
	.markdown :global(a) {
		color: var(--accent);
	}
	.markdown :global(hr) {
		border: none;
		border-top: var(--border-width) solid var(--border-color);
		margin: 1em 0;
	}

	.statusbar {
		display: flex;
		align-items: center;
		gap: var(--space-4);
		flex: none;
		font-size: 0.8rem;
		color: var(--muted);
		font-variant-numeric: tabular-nums;
	}
	.status-right {
		margin-left: auto;
	}
</style>

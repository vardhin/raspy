<script lang="ts">
	// Zero-knowledge password keeper. The whole list of credentials lives inside
	// ONE opaque encrypted blob (crypto/passwords.ts) decrypted in-browser under
	// the vault master key — the Pi only ever stores ciphertext. Add/edit/delete
	// mutate the decrypted list and re-upload the whole blob.
	//
	//   • List view — a searchable card per entry, each with copy-username /
	//     copy-password / reveal controls and a small note. New + Edit + Delete.
	//   • Editor modal — title, username, password (with a generator), url, note.
	//
	// Like the vault, the app shows a "locked" gate until the user has signed in
	// with their password (which is what derives the master key). Token-only
	// styling; no shipped client code beyond this component.
	import { onMount, onDestroy } from 'svelte';
	import { Surface, Stack, Text, Button, Icon, Field, Modal, Switch, Slider } from '$lib/components';
	import { connection } from '$lib/connection.svelte';
	import { auth } from '$lib/auth.svelte';
	import {
		loadStore,
		saveStore,
		emptyStore,
		generatePassword,
		type PasswordStore,
		type PasswordEntry,
		type GenOptions
	} from '$lib/crypto/passwords';

	let store = $state<PasswordStore>(emptyStore());
	let loading = $state(true);
	let error = $state<string | null>(null);
	let locked = $derived(auth.masterKey === null);

	let query = $state('');
	// Which entry ids currently show their password in clear text (per device,
	// not persisted). A copy or reveal never leaves the device.
	let revealed = $state<Record<string, boolean>>({});
	// Transient "Copied" feedback keyed by `${id}:${field}`.
	let copied = $state<string | null>(null);
	let copyTimer: ReturnType<typeof setTimeout> | undefined;

	const filtered = $derived.by(() => {
		const q = query.trim().toLowerCase();
		const list = [...store.entries].sort((a, b) =>
			a.title.localeCompare(b.title, undefined, { sensitivity: 'base' })
		);
		if (!q) return list;
		return list.filter(
			(e) =>
				e.title.toLowerCase().includes(q) ||
				e.username.toLowerCase().includes(q) ||
				e.url.toLowerCase().includes(q) ||
				e.note.toLowerCase().includes(q)
		);
	});

	// --- data ----------------------------------------------------------------
	async function load() {
		if (locked) {
			loading = false;
			return;
		}
		loading = true;
		error = null;
		try {
			store = await loadStore();
		} catch (e) {
			error = e instanceof Error ? e.message : 'failed to load keeper';
		} finally {
			loading = false;
		}
	}

	// Persist the whole blob after any mutation. Optimistic: state already holds
	// the new list, so on failure we surface an error and reload to resync.
	async function persist() {
		try {
			await saveStore(store);
		} catch (e) {
			error = e instanceof Error ? e.message : 'failed to save keeper';
			await load();
		}
	}

	// --- editor modal --------------------------------------------------------
	let editorOpen = $state(false);
	let editingId = $state<string | null>(null); // null = creating a new entry
	let fTitle = $state('');
	let fUsername = $state('');
	let fPassword = $state('');
	let fUrl = $state('');
	let fNote = $state('');
	let showFormPassword = $state(false);

	// Generator options for the editor's "Generate" control.
	let gen = $state<GenOptions>({ length: 20, lower: true, upper: true, digits: true, symbols: true });
	let genOpen = $state(false);

	function openCreate() {
		editingId = null;
		fTitle = fUsername = fPassword = fUrl = fNote = '';
		showFormPassword = true; // a fresh password has nothing to hide yet
		error = null;
		editorOpen = true;
	}

	function openEdit(e: PasswordEntry) {
		editingId = e.id;
		fTitle = e.title;
		fUsername = e.username;
		fPassword = e.password;
		fUrl = e.url;
		fNote = e.note;
		showFormPassword = false;
		error = null;
		editorOpen = true;
	}

	function closeEditor() {
		editorOpen = false;
		genOpen = false;
	}

	async function saveEntry() {
		const title = fTitle.trim();
		if (!title) {
			error = 'A title is required.';
			return;
		}
		const now = Date.now() / 1000;
		if (editingId) {
			store.entries = store.entries.map((e) =>
				e.id === editingId
					? { ...e, title, username: fUsername, password: fPassword, url: fUrl.trim(), note: fNote, updated: now }
					: e
			);
		} else {
			store.entries = [
				...store.entries,
				{
					id: crypto.randomUUID(),
					title,
					username: fUsername,
					password: fPassword,
					url: fUrl.trim(),
					note: fNote,
					created: now,
					updated: now
				}
			];
		}
		closeEditor();
		await persist();
	}

	async function removeEntry(e: PasswordEntry) {
		if (!confirm(`Delete “${e.title}”? This cannot be undone.`)) return;
		store.entries = store.entries.filter((x) => x.id !== e.id);
		await persist();
	}

	function applyGenerated() {
		fPassword = generatePassword(gen);
		showFormPassword = true;
	}

	// --- clipboard + reveal --------------------------------------------------
	async function copy(value: string, tag: string) {
		try {
			await navigator.clipboard.writeText(value);
			copied = tag;
			clearTimeout(copyTimer);
			copyTimer = setTimeout(() => (copied = null), 1400);
		} catch {
			error = 'Clipboard unavailable (needs a secure context).';
		}
	}

	function toggleReveal(id: string) {
		revealed[id] = !revealed[id];
	}

	function mask(pw: string): string {
		return pw ? '•'.repeat(Math.min(pw.length, 12)) : '—';
	}

	function hostOf(url: string): string {
		if (!url) return '';
		try {
			return new URL(url.includes('://') ? url : `https://${url}`).host;
		} catch {
			return url;
		}
	}

	function hrefOf(url: string): string {
		return url.includes('://') ? url : `https://${url}`;
	}

	// --- lifecycle ------------------------------------------------------------
	onMount(() => {
		void load();
		const off = connection.onEvent((topic) => {
			// Another device changed the keeper — reload (unless mid-edit, so we
			// don't clobber a form). The blob is the source of truth.
			if (topic.startsWith('passwords.') && !editorOpen && !locked) void load();
		});
		return () => off();
	});
	onDestroy(() => clearTimeout(copyTimer));

	// Re-run load once the vault unlocks (masterKey becomes available).
	$effect(() => {
		if (!locked && loading) void load();
	});
</script>

{#if locked}
	<Surface level={2}>
		<Stack gap={2} align="center">
			<Icon name="lock" size={28} />
			<Text role="heading">Keeper locked</Text>
			<Text role="muted">Sign in with your password to unlock your passwords.</Text>
		</Stack>
	</Surface>
{:else}
	<Stack gap={3}>
		<Surface level={2}>
			<div class="bar">
				<Text role="heading">Passwords</Text>
				<Button onclick={openCreate}>
					<Icon name="plus" size={16} /> New
				</Button>
			</div>
		</Surface>

		{#if error}<span class="err">{error}</span>{/if}

		{#if store.entries.length > 0}
			<Field placeholder="Search…" bind:value={query} />
		{/if}

		{#if loading && store.entries.length === 0}
			<Text role="muted">Loading…</Text>
		{:else if store.entries.length === 0}
			<Surface level={1}>
				<Stack gap={2} align="center">
					<Icon name="key" size={28} />
					<Text role="heading">No passwords yet</Text>
					<Text role="muted">Add your first credential — it's encrypted on this device.</Text>
					<Button onclick={openCreate}><Icon name="plus" size={15} /> New password</Button>
				</Stack>
			</Surface>
		{:else if filtered.length === 0}
			<Text role="muted">No matches for “{query}”.</Text>
		{:else}
			<div class="grid">
				{#each filtered as e (e.id)}
					<Surface level={1}>
						<Stack gap={2}>
							<div class="card-head">
								<Stack gap={1}>
									<Text role="heading">{e.title}</Text>
									{#if e.url}
										<a class="host" href={hrefOf(e.url)} target="_blank" rel="noopener noreferrer">
											<Icon name="external-link" size={12} /> {hostOf(e.url)}
										</a>
									{/if}
								</Stack>
								<div class="card-actions">
									<Button variant="ghost" size="sm" onclick={() => openEdit(e)}>
										<Icon name="edit" size={14} />
									</Button>
									<Button variant="danger" size="sm" onclick={() => removeEntry(e)}>
										<Icon name="trash-2" size={14} />
									</Button>
								</div>
							</div>

							{#if e.username}
								<div class="cred">
									<span class="cred-label">User</span>
									<span class="cred-val">{e.username}</span>
									<button class="mini" title="Copy username" onclick={() => copy(e.username, `${e.id}:u`)}>
										<Icon name={copied === `${e.id}:u` ? 'check' : 'copy'} size={14} />
									</button>
								</div>
							{/if}

							<div class="cred">
								<span class="cred-label">Pass</span>
								<span class="cred-val mono">{revealed[e.id] ? (e.password || '—') : mask(e.password)}</span>
								<button class="mini" title={revealed[e.id] ? 'Hide' : 'Reveal'} onclick={() => toggleReveal(e.id)}>
									<Icon name={revealed[e.id] ? 'eye-off' : 'eye'} size={14} />
								</button>
								<button class="mini" title="Copy password" onclick={() => copy(e.password, `${e.id}:p`)}>
									<Icon name={copied === `${e.id}:p` ? 'check' : 'copy'} size={14} />
								</button>
							</div>

							{#if e.note}
								<Text role="muted"><span class="note">{e.note}</span></Text>
							{/if}
						</Stack>
					</Surface>
				{/each}
			</div>
		{/if}
	</Stack>

	<!-- ============================ EDITOR MODAL ============================ -->
	<Modal open={editorOpen} title={editingId ? 'Edit password' : 'New password'} onclose={closeEditor}>
		<Stack gap={3}>
			{#if error}<span class="err">{error}</span>{/if}
			<Field label="Title" placeholder="e.g. GitHub" bind:value={fTitle} />
			<Field label="Username / email" placeholder="you@example.com" bind:value={fUsername} />

			<div class="pw-field">
				<Field
					label="Password"
					type={showFormPassword ? 'text' : 'password'}
					placeholder="••••••••"
					bind:value={fPassword}
				/>
				<div class="pw-tools">
					<button class="mini" type="button" title={showFormPassword ? 'Hide' : 'Show'} onclick={() => (showFormPassword = !showFormPassword)}>
						<Icon name={showFormPassword ? 'eye-off' : 'eye'} size={15} />
					</button>
					<button class="mini" type="button" title="Generator options" onclick={() => (genOpen = !genOpen)}>
						<Icon name="key" size={15} />
					</button>
					<Button size="sm" variant="neutral" onclick={applyGenerated}>Generate</Button>
				</div>
			</div>

			{#if genOpen}
				<Surface level={2}>
					<Stack gap={2}>
						<div class="gen-len">
							<Text role="label">Length</Text>
							<div class="gen-slider"><Slider bind:value={gen.length} min={8} max={64} step={1} /></div>
							<span class="gen-val">{gen.length}</span>
						</div>
						<div class="gen-toggles">
							<Switch bind:checked={gen.lower} label="a-z" />
							<Switch bind:checked={gen.upper} label="A-Z" />
							<Switch bind:checked={gen.digits} label="0-9" />
							<Switch bind:checked={gen.symbols} label="!@#" />
						</div>
					</Stack>
				</Surface>
			{/if}

			<Field label="URL" placeholder="example.com" bind:value={fUrl} />
			<Field label="Note" type="textarea" placeholder="A small note (recovery email, security questions, …)" bind:value={fNote} />

			<div class="modal-actions">
				<Button variant="ghost" onclick={closeEditor}>Cancel</Button>
				<Button onclick={saveEntry}>{editingId ? 'Save' : 'Add'}</Button>
			</div>
		</Stack>
	</Modal>
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
	.grid {
		display: grid;
		grid-template-columns: repeat(auto-fill, minmax(260px, 1fr));
		gap: var(--space-3);
	}
	.card-head {
		display: flex;
		align-items: flex-start;
		justify-content: space-between;
		gap: var(--space-2);
	}
	.card-actions {
		display: flex;
		gap: var(--space-1);
		flex: none;
	}
	.host {
		display: inline-flex;
		align-items: center;
		gap: var(--space-1);
		color: var(--accent);
		font-size: 0.8rem;
		text-decoration: none;
		word-break: break-all;
	}
	.host:hover {
		text-decoration: underline;
	}
	.cred {
		display: flex;
		align-items: center;
		gap: var(--space-2);
	}
	.cred-label {
		flex: none;
		width: 2.6rem;
		font-size: 0.72rem;
		text-transform: uppercase;
		letter-spacing: 0.04em;
		color: var(--muted);
	}
	.cred-val {
		flex: 1;
		min-width: 0;
		overflow: hidden;
		text-overflow: ellipsis;
		white-space: nowrap;
	}
	.cred-val.mono {
		font-family: ui-monospace, SFMono-Regular, Menlo, Consolas, monospace;
		font-size: 0.9rem;
	}
	.note {
		white-space: pre-wrap;
		font-size: 0.85rem;
	}
	.mini {
		flex: none;
		display: inline-flex;
		align-items: center;
		justify-content: center;
		width: 1.8rem;
		height: 1.8rem;
		border: var(--border-width) solid var(--border-color);
		border-radius: var(--radius-sm);
		background: transparent;
		color: var(--muted);
		cursor: pointer;
		transition:
			color var(--motion-fast) var(--motion-ease),
			border-color var(--motion-fast) var(--motion-ease);
	}
	.mini:hover {
		color: var(--fg);
		border-color: var(--accent);
	}
	.pw-field {
		display: flex;
		flex-direction: column;
		gap: var(--space-2);
	}
	.pw-tools {
		display: flex;
		align-items: center;
		gap: var(--space-2);
	}
	.gen-len {
		display: flex;
		align-items: center;
		gap: var(--space-2);
	}
	.gen-slider {
		flex: 1;
	}
	.gen-val {
		min-width: 2rem;
		text-align: right;
		font-variant-numeric: tabular-nums;
	}
	.gen-toggles {
		display: flex;
		flex-wrap: wrap;
		gap: var(--space-3);
	}
	.modal-actions {
		display: flex;
		justify-content: flex-end;
		gap: var(--space-2);
	}
</style>

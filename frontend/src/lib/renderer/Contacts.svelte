<script lang="ts">
	// Contacts — a personal address book + a "keep in touch" reminder list, in one
	// app with a topbar switch:
	//
	//   • Keep in touch (default) — favorites only. An accordion of just the names
	//     you've flagged to keep in touch with. Tap a name to expand a compact panel
	//     (avatar + the quick ways to reach them) so you remember to call, without
	//     the noise of the full directory. Flag a contact from its editor.
	//   • Directory — every contact as a card with photos + all fields, opening a
	//     full detail/edit view.
	//
	// Each contact's text fields are plaintext (so names render even when locked);
	// photos are end-to-end encrypted with the vault master key, exactly like the
	// calendar — decrypted on view here.
	import { onMount, onDestroy } from 'svelte';
	import {
		Surface,
		Stack,
		Text,
		Button,
		Icon,
		Field,
		Modal,
		Carousel,
		SegmentedControl,
		Accordion,
		AccordionItem
	} from '$lib/components';
	import { attGet, attAction, attResourceUrl, attUpload, attDeleteQuery } from '$lib/api';
	import { connection } from '$lib/connection.svelte';
	import { kvGet, kvSet } from '$lib/kv';
	import { auth } from '$lib/auth.svelte';
	import { encryptImage, hashCiphertext } from '$lib/crypto/calendarMedia';
	import * as contactsCache from '$lib/crypto/contactsCache';

	const ID = 'contacts';
	const VIEW_KEY = 'contacts:view';

	// Photos are end-to-end encrypted; they're only viewable once the vault master
	// key is in memory. The text fields (names, phone, …) work regardless.
	let locked = $derived(auth.masterKey === null);

	type Img = {
		id: number;
		hash: string;
		mime: string;
		ord: number;
		url: string;
		cover?: boolean;
		enc?: boolean;
		key_wrapped?: string;
		nonce_wrapped?: string;
		header?: string;
	};
	type Contact = {
		id: number;
		name: string;
		description: string;
		phone: string;
		email: string;
		address: string;
		keep_in_touch: boolean;
		images: Img[];
	};

	type View = 'touch' | 'directory';

	let view = $state<View>('touch');
	let contacts = $state<Contact[]>([]);
	let loading = $state(true);
	let error = $state<string | null>(null);
	let query = $state('');

	// Which accordion row is open (keep-in-touch view); single-open.
	let openId = $state<number | null>(null);

	// hash -> decrypted object URL (or 'pending'/'error'). Drives every avatar +
	// carousel: an image shows a spinner until its blob is decrypted on view.
	let decrypted = $state<Record<string, string>>({});

	function decrypt(img: Img): void {
		if (!img.enc || !img.key_wrapped || !img.nonce_wrapped || !img.header) return;
		if (decrypted[img.hash] && decrypted[img.hash] !== 'error') return;
		decrypted[img.hash] = decrypted[img.hash] ?? 'pending';
		contactsCache
			.get({
				hash: img.hash,
				mime: img.mime,
				key_wrapped: img.key_wrapped,
				nonce_wrapped: img.nonce_wrapped,
				header: img.header
			})
			.then((url) => (decrypted[img.hash] = url))
			.catch(() => (decrypted[img.hash] = 'error'));
	}

	// Decrypt every photo once contacts load (and the vault is unlocked).
	$effect(() => {
		if (locked) return;
		for (const c of contacts) for (const im of c.images) decrypt(im);
	});

	// The contact's chosen cover image (or the lowest-ord one if none is flagged).
	function coverImage(c: Contact): Img | undefined {
		return c.images.find((im) => im.cover) ?? c.images.slice().sort((a, b) => a.ord - b.ord)[0];
	}

	// Cover photo of a contact, as a ready object URL or '' while loading.
	function avatarSrc(c: Contact): string {
		const im = coverImage(c);
		if (!im) return '';
		if (!im.enc) return attResourceUrl(ID, im.url, {});
		const u = decrypted[im.hash];
		return u && u !== 'pending' && u !== 'error' ? u : '';
	}

	// Build carousel items for a set of images: decrypted object URLs when ready,
	// else a loading placeholder. (Legacy plaintext rows fall back to direct URL.)
	function imagesToItems(images: Img[], alt: string) {
		return images
			.slice()
			.sort((a, b) => a.ord - b.ord)
			.map((im) => {
				if (!im.enc) return { src: attResourceUrl(ID, im.url, {}), alt };
				const u = decrypted[im.hash];
				if (u && u !== 'pending' && u !== 'error') return { src: u, alt };
				return { src: '', alt, loading: u !== 'error' };
			});
	}

	function initials(name: string): string {
		const parts = name.trim().split(/\s+/).filter(Boolean);
		if (parts.length === 0) return '?';
		if (parts.length === 1) return parts[0].slice(0, 2).toUpperCase();
		return (parts[0][0] + parts[parts.length - 1][0]).toUpperCase();
	}

	// --- data ----------------------------------------------------------------
	async function load() {
		loading = true;
		error = null;
		try {
			contacts = await attGet<Contact[]>(ID, 'contacts');
		} catch (e) {
			error = e instanceof Error ? e.message : 'failed to load contacts';
		} finally {
			loading = false;
		}
	}

	let filtered = $derived.by(() => {
		// "Keep in touch" shows only favorited contacts; the directory shows all.
		const base = view === 'touch' ? contacts.filter((c) => c.keep_in_touch) : contacts;
		const q = query.trim().toLowerCase();
		if (!q) return base;
		return base.filter((c) =>
			[c.name, c.description, c.phone, c.email, c.address]
				.join(' ')
				.toLowerCase()
				.includes(q)
		);
	});

	// --- editor modal --------------------------------------------------------
	let editorOpen = $state(false);
	let editing = $state<Contact | null>(null);
	let formName = $state('');
	let formDescription = $state('');
	let formPhone = $state('');
	let formEmail = $state('');
	let formAddress = $state('');
	let formKeepInTouch = $state(false);
	let pendingFiles = $state<File[]>([]);
	let uploadBusy = $state(false);
	let fileInput = $state<HTMLInputElement>();

	// Object URLs for the not-yet-uploaded photos; recreated/revoked as the set changes.
	let pendingUrls = $state<string[]>([]);
	$effect(() => {
		const urls = pendingFiles.map((f) => URL.createObjectURL(f));
		pendingUrls = urls;
		return () => urls.forEach((u) => URL.revokeObjectURL(u));
	});

	let previewImages = $derived([
		...(editing ? imagesToItems(editing.images, '') : []),
		...pendingUrls.map((src) => ({ src, alt: '' }))
	]);
	let previewIdx = $state(0);

	function openCreate() {
		editing = null;
		formName = '';
		formDescription = '';
		formPhone = '';
		formEmail = '';
		formAddress = '';
		// Default a new contact to "keep in touch" when adding from that view.
		formKeepInTouch = view === 'touch';
		pendingFiles = [];
		editorOpen = true;
	}
	function openEdit(c: Contact) {
		editing = c;
		formName = c.name;
		formDescription = c.description;
		formPhone = c.phone;
		formEmail = c.email;
		formAddress = c.address;
		formKeepInTouch = c.keep_in_touch;
		pendingFiles = [];
		editorOpen = true;
	}

	// Encrypt a photo in the browser, upload the opaque ciphertext with its wrapped
	// key material as query params (the bytes the Pi stores are unreadable).
	async function uploadEncrypted(contactId: number, file: File): Promise<void> {
		const enc = await encryptImage(file);
		const hash = await hashCiphertext(enc.ciphertext);
		const ctFile = new File([enc.ciphertext as BlobPart], `${hash}.bin`, {
			type: 'application/octet-stream'
		});
		await attUpload(
			ID,
			`contacts/${contactId}/images`,
			{
				mime: enc.mime,
				key_wrapped: enc.keyWrapped,
				nonce_wrapped: enc.nonceWrapped,
				header: enc.header
			},
			ctFile
		);
	}

	async function saveContact() {
		if (!formName.trim()) {
			error = 'A name is required.';
			return;
		}
		uploadBusy = true;
		error = null;
		try {
			const body = {
				name: formName,
				description: formDescription,
				phone: formPhone,
				email: formEmail,
				address: formAddress,
				keep_in_touch: formKeepInTouch
			};
			let contact: Contact;
			if (editing) {
				contact = await attAction<Contact>(ID, 'PATCH', `contacts/${editing.id}`, body);
			} else {
				contact = await attAction<Contact>(ID, 'POST', 'contacts', body);
			}
			for (const file of pendingFiles) await uploadEncrypted(contact.id, file);
			editorOpen = false;
			await load();
			// Keep the detail view in sync if it's open.
			if (viewing) viewing = contacts.find((c) => c.id === viewing!.id) ?? null;
		} catch (e) {
			error = e instanceof Error ? e.message : 'failed to save contact';
		} finally {
			uploadBusy = false;
		}
	}

	// Flip a contact's "keep in touch" flag straight from the detail view.
	async function toggleKeepInTouch(c: Contact) {
		try {
			await attAction(ID, 'PATCH', `contacts/${c.id}`, { keep_in_touch: !c.keep_in_touch });
			await load();
			if (viewing?.id === c.id) viewing = contacts.find((x) => x.id === c.id) ?? null;
		} catch (e) {
			error = e instanceof Error ? e.message : 'failed to update';
		}
	}

	async function deleteContact(c: Contact) {
		if (!confirm(`Delete ${c.name} and their photos? This cannot be undone.`)) return;
		try {
			await attAction(ID, 'DELETE', `contacts/${c.id}`);
			if (viewing?.id === c.id) viewing = null;
			if (openId === c.id) openId = null;
			await load();
		} catch (e) {
			error = e instanceof Error ? e.message : 'failed to delete';
		}
	}

	async function deleteImage(im: Img) {
		try {
			await attDeleteQuery(ID, `images/${im.id}`, {});
			await load();
			if (editing) editing = contacts.find((c) => c.id === editing!.id) ?? null;
			if (viewing) viewing = contacts.find((c) => c.id === viewing!.id) ?? null;
		} catch (e) {
			error = e instanceof Error ? e.message : 'failed to remove photo';
		}
	}

	// Make this image the contact's cover (the one shown in minimized/card views).
	async function setCover(im: Img) {
		if (im.cover) return;
		try {
			await attAction(ID, 'PATCH', `images/${im.id}/cover`);
			await load();
			if (editing) editing = contacts.find((c) => c.id === editing!.id) ?? null;
			if (viewing) viewing = contacts.find((c) => c.id === viewing!.id) ?? null;
		} catch (e) {
			error = e instanceof Error ? e.message : 'failed to set cover';
		}
	}

	function onPickFiles(e: Event) {
		const files = (e.target as HTMLInputElement).files;
		if (files) pendingFiles = [...pendingFiles, ...Array.from(files)];
		if (fileInput) fileInput.value = '';
	}

	// --- detail view modal ---------------------------------------------------
	let viewing = $state<Contact | null>(null);
	let viewIdx = $state(0);
	// Index of a contact's cover within its ord-sorted images (what the carousels use).
	function coverIndex(c: Contact): number {
		const sorted = c.images.slice().sort((a, b) => a.ord - b.ord);
		const i = sorted.findIndex((im) => im.cover);
		return i >= 0 ? i : 0;
	}
	function openView(c: Contact) {
		viewing = c;
		viewIdx = coverIndex(c);
	}

	onMount(() => {
		void kvGet<View>(VIEW_KEY).then((v) => {
			if (v === 'touch' || v === 'directory') view = v;
		});
		void load();
		const off = connection.onEvent((topic) => {
			if (topic === 'contacts.changed') void load();
		});
		return () => off();
	});
	onDestroy(() => contactsCache.clear());

	$effect(() => {
		void kvSet(VIEW_KEY, view);
	});

	// Drop decrypted photos when the vault locks (keys gone).
	$effect(() => {
		if (locked) {
			decrypted = {};
			contactsCache.clear();
		}
	});
</script>

<Stack gap={3}>
	<!-- Top bar: view switch + search + add -->
	<Surface level={2}>
		<div class="bar">
			<SegmentedControl
				bind:value={view}
				options={[
					{ value: 'touch', label: 'Keep in touch' },
					{ value: 'directory', label: 'Directory' }
				]}
			/>
			<div class="bar-right">
				<div class="search">
					<Icon name="search" size={16} />
					<input class="search-input" placeholder="Search contacts…" bind:value={query} />
				</div>
				<Button onclick={openCreate}>
					<Icon name="plus" size={16} /> Add
				</Button>
			</div>
		</div>
	</Surface>

	{#if error}<span class="err">{error}</span>{/if}

	{#if loading && contacts.length === 0}
		<Text role="muted">Loading…</Text>
	{:else if filtered.length === 0}
		{@const noFavorites = view === 'touch' && !query && contacts.length > 0}
		<Surface level={1}>
			<Stack gap={2} align="center">
				<Icon name={noFavorites ? 'star' : 'contact'} size={28} />
				<Text role="heading">
					{query ? 'No matches' : noFavorites ? 'No favorites yet' : 'No contacts yet'}
				</Text>
				<Text role="muted">
					{#if query}
						Try a different search.
					{:else if noFavorites}
						Flag a contact as “Keep in touch” to see them here. Find them in the directory.
					{:else}
						Add someone to start keeping in touch.
					{/if}
				</Text>
				{#if query}
					<!-- search has results elsewhere; nothing to add here -->
				{:else if noFavorites}
					<Button onclick={() => (view = 'directory')}>
						<Icon name="grid" size={15} /> Go to directory
					</Button>
				{:else}
					<Button onclick={openCreate}><Icon name="plus" size={15} /> Add a contact</Button>
				{/if}
			</Stack>
		</Surface>
	{:else if view === 'touch'}
		<!-- Keep in touch: just names, in an accordion. Open one to see the quick
		     ways to reach them — a nudge to actually call. -->
		<Accordion>
			{#each filtered as c (c.id)}
				{@const av = avatarSrc(c)}
				<AccordionItem
					open={openId === c.id}
					ontoggle={() => (openId = openId === c.id ? null : c.id)}
				>
					{#snippet header()}
						<div class="touch-head">
							<span class="avatar sm" class:has-photo={!!av}>
								{#if av}<img src={av} alt="" />{:else}<span class="ini">{initials(c.name)}</span>{/if}
							</span>
							<span class="touch-name">{c.name}</span>
							<Icon name={openId === c.id ? 'chevron-up' : 'chevron-down'} size={16} />
						</div>
					{/snippet}

					<div class="touch-body">
						{#if c.description}<Text role="muted">{c.description}</Text>{/if}
						<div class="reach">
							{#if c.phone}
								<a class="reach-row" href={`tel:${c.phone}`}>
									<Icon name="phone" size={15} /><span>{c.phone}</span>
								</a>
							{/if}
							{#if c.email}
								<a class="reach-row" href={`mailto:${c.email}`}>
									<Icon name="mail" size={15} /><span>{c.email}</span>
								</a>
							{/if}
							{#if c.address}
								<div class="reach-row">
									<Icon name="map-pin" size={15} /><span>{c.address}</span>
								</div>
							{/if}
							{#if !c.phone && !c.email && !c.address}
								<Text role="muted">No contact details yet.</Text>
							{/if}
						</div>
						<div class="touch-actions">
							<Button variant="ghost" size="sm" onclick={() => openView(c)}>
								<Icon name="user" size={14} /> Open
							</Button>
							<Button variant="ghost" size="sm" onclick={() => openEdit(c)}>
								<Icon name="edit" size={14} /> Edit
							</Button>
						</div>
					</div>
				</AccordionItem>
			{/each}
		</Accordion>
	{:else}
		<!-- Directory: cards with the cover photo + fields. -->
		<div class="grid">
			{#each filtered as c (c.id)}
				{@const av = avatarSrc(c)}
				<button class="card" onclick={() => openView(c)}>
					<span class="avatar lg" class:has-photo={!!av}>
						{#if av}<img src={av} alt="" />{:else}<span class="ini">{initials(c.name)}</span>{/if}
						{#if c.images.length > 1}<span class="count">{c.images.length}</span>{/if}
					</span>
					<span class="card-name">
						{#if c.keep_in_touch}<Icon name="star" size={12} />{/if}{c.name}
					</span>
					{#if c.description}<span class="card-desc">{c.description}</span>{/if}
					<span class="card-meta">
						{#if c.phone}<span class="chip"><Icon name="phone" size={12} />{c.phone}</span>{/if}
						{#if c.email}<span class="chip"><Icon name="mail" size={12} />{c.email}</span>{/if}
					</span>
				</button>
			{/each}
		</div>
	{/if}
</Stack>

<!-- Detail view -->
{#if viewing}
	{@const imgs = imagesToItems(viewing.images, viewing.name)}
	<Modal open title={viewing.name} size="lg" onclose={() => (viewing = null)}>
		<Stack gap={3}>
			{#if imgs.length > 0}
				<Carousel items={imgs} bind:index={viewIdx} fit="contain" allowFullscreen allowLightsOff />
			{/if}
			{#if viewing.description}<Text>{viewing.description}</Text>{/if}
			<div class="reach detail">
				{#if viewing.phone}
					<a class="reach-row" href={`tel:${viewing.phone}`}>
						<Icon name="phone" size={16} /><span>{viewing.phone}</span>
					</a>
				{/if}
				{#if viewing.email}
					<a class="reach-row" href={`mailto:${viewing.email}`}>
						<Icon name="mail" size={16} /><span>{viewing.email}</span>
					</a>
				{/if}
				{#if viewing.address}
					<div class="reach-row"><Icon name="map-pin" size={16} /><span>{viewing.address}</span></div>
				{/if}
			</div>
			<Stack direction="row" gap={2} justify="between" align="center">
				<Button variant="ghost" onclick={() => toggleKeepInTouch(viewing!)}>
					<Icon name="star" size={15} />
					{viewing.keep_in_touch ? 'In keep in touch' : 'Keep in touch'}
				</Button>
				<Stack direction="row" gap={2}>
					<Button variant="danger" onclick={() => deleteContact(viewing!)}>
						<Icon name="trash" size={15} /> Delete
					</Button>
					<Button variant="ghost" onclick={() => openEdit(viewing!)}>
						<Icon name="edit" size={15} /> Edit
					</Button>
				</Stack>
			</Stack>
		</Stack>
	</Modal>
{/if}

<!-- Editor -->
<Modal
	open={editorOpen}
	title={editing ? 'Edit contact' : 'New contact'}
	onclose={() => (editorOpen = false)}
>
	<Stack gap={3}>
		{#if previewImages.length > 0}
			<Carousel items={previewImages} bind:index={previewIdx} fit="contain" />
		{/if}

		<Field label="Name" placeholder="Full name" bind:value={formName} />
		<Field
			type="textarea"
			label="Description"
			placeholder="How you know them, notes, anything…"
			bind:value={formDescription}
		/>
		<Field type="text" label="Phone" placeholder="+1 555 0100" bind:value={formPhone} />
		<Field type="email" label="Email" placeholder="name@example.com" bind:value={formEmail} />
		<Field type="textarea" label="Address" placeholder="Street, city, country" bind:value={formAddress} />

		<Field type="checkbox" label="Keep in touch" bind:value={formKeepInTouch} />

		{#if editing && editing.images.length > 0}
			<div>
				<Text role="label">Photos</Text>
				<Text role="muted">Tap a photo to make it the cover.</Text>
				<div class="thumbs">
					{#each editing.images.slice().sort((a, b) => a.ord - b.ord) as im (im.id)}
						{@const src = im.enc
							? decrypted[im.hash] && decrypted[im.hash] !== 'pending' && decrypted[im.hash] !== 'error'
								? decrypted[im.hash]
								: ''
							: attResourceUrl(ID, im.url, {})}
						<div class="thumb" class:is-cover={im.cover}>
							<button
								class="thumb-pick"
								aria-label={im.cover ? 'Cover photo' : 'Set as cover'}
								onclick={() => setCover(im)}
							>
								{#if src}<img {src} alt="" />{:else}<div class="thumb-loading"><Icon name="refresh-cw" size={16} /></div>{/if}
							</button>
							{#if im.cover}<span class="cover-badge"><Icon name="star" size={11} /> Cover</span>{/if}
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
		{#if locked}
			<Text role="muted">Sign in with your password to add encrypted photos.</Text>
		{/if}

		<input
			bind:this={fileInput}
			type="file"
			accept="image/*,.heic,.heif,.avif,.bmp,.tif,.tiff"
			multiple
			style="display:none"
			onchange={onPickFiles}
		/>
		<Stack direction="row" gap={2} justify="between" align="center">
			<Button variant="ghost" disabled={locked} onclick={() => fileInput?.click()}>
				<Icon name="image" size={16} /> Add photos
			</Button>
			<Stack direction="row" gap={2}>
				<Button variant="ghost" onclick={() => (editorOpen = false)}>Cancel</Button>
				<Button onclick={saveContact} disabled={uploadBusy}>
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
	.bar-right {
		display: flex;
		align-items: center;
		gap: var(--space-2);
		flex-wrap: wrap;
	}
	.search {
		display: flex;
		align-items: center;
		gap: var(--space-2);
		padding: var(--space-1) var(--space-3);
		border: var(--border-width) solid var(--border-color);
		border-radius: var(--radius-full);
		background: color-mix(in srgb, var(--surface-2) calc(var(--surface-alpha) * 100%), transparent);
		color: var(--muted);
	}
	.search-input {
		border: none;
		background: transparent;
		color: var(--fg);
		font: inherit;
		outline: none;
		min-width: 0;
		width: 11rem;
		max-width: 40vw;
	}
	.err {
		color: var(--danger);
		font-size: 0.9rem;
	}

	/* --- avatar ------------------------------------------------------------- */
	.avatar {
		position: relative;
		display: inline-flex;
		align-items: center;
		justify-content: center;
		flex: none;
		border-radius: var(--radius-full);
		overflow: hidden;
		background: color-mix(in srgb, var(--accent) 18%, var(--surface-2));
		color: var(--accent);
		font-weight: var(--font-weight-bold);
	}
	.avatar.has-photo {
		background: var(--surface-2);
	}
	.avatar img {
		width: 100%;
		height: 100%;
		object-fit: cover;
	}
	.avatar.sm {
		width: 36px;
		height: 36px;
		font-size: 0.85rem;
	}
	.avatar.lg {
		width: 64px;
		height: 64px;
		font-size: 1.25rem;
	}
	.avatar .ini {
		line-height: 1;
	}
	.avatar .count {
		position: absolute;
		bottom: 2px;
		right: 2px;
		font-size: 0.6rem;
		padding: 1px 5px;
		border-radius: var(--radius-full);
		background: var(--overlay, rgba(0, 0, 0, 0.6));
		color: #fff;
	}

	/* --- keep in touch (accordion) ----------------------------------------- */
	.touch-head {
		display: flex;
		align-items: center;
		gap: var(--space-3);
		width: 100%;
		padding: var(--space-3);
	}
	.touch-name {
		flex: 1;
		min-width: 0;
		font-weight: var(--font-weight-bold);
		text-align: left;
		overflow: hidden;
		text-overflow: ellipsis;
		white-space: nowrap;
	}
	.touch-body {
		display: flex;
		flex-direction: column;
		gap: var(--space-3);
		padding: 0 var(--space-3) var(--space-3);
	}
	.touch-actions {
		display: flex;
		gap: var(--space-2);
	}
	.reach {
		display: flex;
		flex-direction: column;
		gap: var(--space-2);
	}
	.reach-row {
		display: flex;
		align-items: center;
		gap: var(--space-2);
		color: var(--fg);
		text-decoration: none;
		font-size: 0.9rem;
		word-break: break-word;
	}
	a.reach-row:hover {
		color: var(--accent);
	}
	.reach-row :global(svg) {
		color: var(--muted);
		flex: none;
	}
	a.reach-row:hover :global(svg) {
		color: var(--accent);
	}

	/* --- directory (cards) -------------------------------------------------- */
	.grid {
		display: grid;
		grid-template-columns: repeat(auto-fill, minmax(160px, 1fr));
		gap: var(--space-3);
	}
	.card {
		display: flex;
		flex-direction: column;
		align-items: center;
		gap: var(--space-2);
		text-align: center;
		padding: var(--space-4) var(--space-3);
		border: var(--border-width) solid var(--border-color);
		border-radius: var(--radius-lg);
		background: color-mix(in srgb, var(--surface) calc(var(--surface-alpha, 1) * 100%), transparent);
		color: var(--fg);
		cursor: pointer;
		font: inherit;
		transition:
			transform var(--motion-fast) var(--motion-ease),
			box-shadow var(--motion-fast) var(--motion-ease),
			border-color var(--motion-fast) var(--motion-ease);
	}
	.card:hover {
		transform: translateY(-2px);
		box-shadow: var(--shadow-md);
		border-color: var(--accent);
	}
	.card-name {
		display: inline-flex;
		align-items: center;
		gap: 4px;
		font-weight: var(--font-weight-bold);
		line-height: 1.2;
	}
	.card-name :global(svg) {
		color: var(--accent);
		flex: none;
	}
	.card-desc {
		font-size: 0.8rem;
		color: var(--muted);
		display: -webkit-box;
		-webkit-line-clamp: 2;
		line-clamp: 2;
		-webkit-box-orient: vertical;
		overflow: hidden;
	}
	.card-meta {
		display: flex;
		flex-direction: column;
		gap: 4px;
		width: 100%;
		margin-top: auto;
	}
	.chip {
		display: inline-flex;
		align-items: center;
		gap: 4px;
		justify-content: center;
		font-size: 0.72rem;
		color: var(--muted);
		max-width: 100%;
		overflow: hidden;
		text-overflow: ellipsis;
		white-space: nowrap;
	}

	.detail.reach {
		gap: var(--space-3);
	}

	/* --- editor thumbs ------------------------------------------------------ */
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
	.thumb.is-cover {
		border-color: var(--accent);
		box-shadow: 0 0 0 1px var(--accent);
	}
	.thumb-pick {
		display: block;
		width: 100%;
		height: 100%;
		padding: 0;
		border: none;
		background: none;
		cursor: pointer;
	}
	.thumb img {
		width: 100%;
		height: 100%;
		object-fit: cover;
		display: block;
	}
	.cover-badge {
		position: absolute;
		left: 2px;
		bottom: 2px;
		display: inline-flex;
		align-items: center;
		gap: 2px;
		padding: 1px 5px;
		font-size: 0.6rem;
		border-radius: var(--radius-full);
		background: var(--accent);
		color: var(--on-accent, #fff);
		pointer-events: none;
	}
	.cover-badge :global(svg) {
		color: inherit;
	}
	.thumb-loading {
		display: flex;
		align-items: center;
		justify-content: center;
		width: 100%;
		height: 100%;
		color: var(--muted);
		background: var(--surface);
	}
	.thumb-loading :global(svg) {
		animation: thumb-spin 1s linear infinite;
	}
	@keyframes thumb-spin {
		to {
			transform: rotate(360deg);
		}
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

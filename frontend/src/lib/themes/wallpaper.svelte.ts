// Wallpaper runtime — a frontend-only background image for the app shell, sitting
// alongside the theme (color × concept) system. Like the theme choice, it's a
// purely client-side preference: nothing here touches the backend except reading
// already-cached Vibe images by date through the normal authed image endpoint.
//
// Storage model:
//   - The *selection* (which wallpaper + dim/blur knobs) is small JSON in
//     localStorage, applied to :root before paint (see app.html seed).
//   - Uploaded image *blobs* live in IndexedDB (via the shared kv store): one
//     entry per upload keyed `wp:blob:<id>`, plus an index array under `wp:index`
//     listing the user's saved wallpapers (for the "previously used" gallery).
//   - Vibe wallpapers store no blob — just the date; the image is fetched live
//     from /api/att/vibe/image/<date> (already cached on the Pi).
import { browser } from '$app/environment';
import { kvGet, kvSet } from '$lib/kv';
import { attResourceUrl } from '$lib/api';

export const WP_STORAGE_KEY = 'raspy.wallpaper';
const WP_INDEX_KEY = 'wp:index';
const WP_BLOB_PREFIX = 'wp:blob:';

/** A saved, user-uploaded wallpaper (blob lives under `wp:blob:<id>`). */
export interface SavedWallpaper {
	id: string;
	name: string;
	added: number; // epoch ms
}

/** The persisted selection. `none` = no wallpaper; `upload` = a saved blob by id;
 *  `vibe` = a Vibe image by date (fetched live). */
export interface WallpaperChoice {
	kind: 'none' | 'upload' | 'vibe';
	ref: string; // upload id, or vibe date (YYYY-MM-DD); '' for none
	dim: number; // 0..1 scrim over the image so UI stays readable
	blur: number; // px backdrop blur on the image
}

const DEFAULT_CHOICE: WallpaperChoice = { kind: 'none', ref: '', dim: 0.35, blur: 0 };

function readChoice(): WallpaperChoice {
	if (browser) {
		try {
			const raw = localStorage.getItem(WP_STORAGE_KEY);
			if (raw) return { ...DEFAULT_CHOICE, ...(JSON.parse(raw) as Partial<WallpaperChoice>) };
		} catch {
			/* fall through */
		}
	}
	return { ...DEFAULT_CHOICE };
}

function vibeUrl(date: string): string {
	return attResourceUrl('vibe', `image/${date}`, {});
}

class WallpaperState {
	#choice = $state<WallpaperChoice>(readChoice());
	#saved = $state<SavedWallpaper[]>([]);
	// Object URL for the currently-applied uploaded blob (revoked on change).
	#objectUrl: string | null = null;
	#initialized = false;

	get kind() {
		return this.#choice.kind;
	}
	get ref() {
		return this.#choice.ref;
	}
	get dim() {
		return this.#choice.dim;
	}
	get blur() {
		return this.#choice.blur;
	}
	get saved() {
		return this.#saved;
	}

	/** Apply on mount and load the saved-wallpaper index. Idempotent: safe to call
	 *  from both the layout and the picker. */
	async init() {
		if (this.#initialized) return;
		this.#initialized = true;
		this.#saved = (await kvGet<SavedWallpaper[]>(WP_INDEX_KEY)) ?? [];
		await this.#apply();
	}

	/** Resolve a choice to a CSS `url(...)` (or '' for none). */
	async #resolveUrl(c: WallpaperChoice): Promise<string> {
		if (c.kind === 'none') return '';
		if (c.kind === 'vibe') return vibeUrl(c.ref);
		// upload: pull the blob from IndexedDB and make an object URL
		const blob = await kvGet<Blob>(WP_BLOB_PREFIX + c.ref);
		if (!blob) return '';
		return URL.createObjectURL(blob);
	}

	async #apply() {
		if (!browser) return;
		const root = document.documentElement;
		if (this.#objectUrl) {
			URL.revokeObjectURL(this.#objectUrl);
			this.#objectUrl = null;
		}
		const url = await this.#resolveUrl(this.#choice);
		if (this.#choice.kind === 'upload' && url.startsWith('blob:')) this.#objectUrl = url;
		root.style.setProperty('--wallpaper', url ? `url("${url}")` : 'none');
		root.style.setProperty('--wallpaper-dim', String(this.#choice.dim));
		root.style.setProperty('--wallpaper-blur', `${this.#choice.blur}px`);
		root.dataset.wallpaper = this.#choice.kind === 'none' ? 'off' : 'on';
	}

	#commit() {
		if (browser) localStorage.setItem(WP_STORAGE_KEY, JSON.stringify(this.#choice));
		void this.#apply();
	}

	/** Live preview URL for any choice without committing (for the picker grid). */
	previewUrl(c: Pick<WallpaperChoice, 'kind' | 'ref'>): string {
		if (c.kind === 'vibe') return vibeUrl(c.ref);
		return '';
	}

	clear() {
		this.#choice = { ...this.#choice, kind: 'none', ref: '' };
		this.#commit();
	}

	useUpload(id: string) {
		this.#choice = { ...this.#choice, kind: 'upload', ref: id };
		this.#commit();
	}

	useVibe(date: string) {
		this.#choice = { ...this.#choice, kind: 'vibe', ref: date };
		this.#commit();
	}

	setDim(v: number) {
		this.#choice = { ...this.#choice, dim: Math.min(1, Math.max(0, v)) };
		this.#commit();
	}

	setBlur(v: number) {
		this.#choice = { ...this.#choice, blur: Math.max(0, v) };
		this.#commit();
	}

	/** Store an uploaded file as a new saved wallpaper and select it. */
	async addUpload(file: File): Promise<void> {
		const id = `${Date.now()}-${Math.random().toString(36).slice(2, 8)}`;
		await kvSet(WP_BLOB_PREFIX + id, file);
		const entry: SavedWallpaper = { id, name: file.name || 'Wallpaper', added: Date.now() };
		this.#saved = [entry, ...this.#saved];
		await kvSet(WP_INDEX_KEY, this.#saved);
		this.useUpload(id);
	}

	/** Object URL for a saved wallpaper thumbnail (caller revokes via revoke()). */
	async thumbUrl(id: string): Promise<string> {
		const blob = await kvGet<Blob>(WP_BLOB_PREFIX + id);
		return blob ? URL.createObjectURL(blob) : '';
	}

	revoke(url: string) {
		if (url.startsWith('blob:')) URL.revokeObjectURL(url);
	}

	/** Remove a saved wallpaper; if it was active, fall back to none. */
	async remove(id: string): Promise<void> {
		this.#saved = this.#saved.filter((w) => w.id !== id);
		await kvSet(WP_INDEX_KEY, this.#saved);
		await kvSet(WP_BLOB_PREFIX + id, null);
		if (this.#choice.kind === 'upload' && this.#choice.ref === id) this.clear();
	}
}

export const wallpaper = new WallpaperState();

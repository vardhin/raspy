// Theme runtime: apply tokens to :root, switch live, persist to localStorage.
// See plan/45-theming.md §5. Color tokens are applied first, then concept tokens,
// so a concept may legitimately override a color token (e.g. neobrutalism's
// --border-color: var(--fg)). The resolved font and the animations flag are applied
// last, as a third client-side preference axis (cf. wallpaper.svelte.ts).
import { browser } from '$app/environment';
import type { ColorTheme, ConceptTheme, ThemeChoice } from './types';
import {
	colorThemeMap,
	conceptThemeMap,
	DEFAULT_COLOR_ID,
	DEFAULT_CONCEPT_ID
} from './registry';
import { fontMap, DEFAULT_FONT_ID } from './fonts/registry';

export const STORAGE_KEY = 'raspy.theme';

function readChoice(): ThemeChoice {
	if (browser) {
		try {
			const raw = localStorage.getItem(STORAGE_KEY);
			if (raw) {
				const c = JSON.parse(raw) as Partial<ThemeChoice>;
				return {
					color: c.color && colorThemeMap.has(c.color) ? c.color : DEFAULT_COLOR_ID,
					concept:
						c.concept && conceptThemeMap.has(c.concept)
							? c.concept
							: DEFAULT_CONCEPT_ID,
					// null is meaningful (= follow concept default), so keep it as-is;
					// drop ids that no longer exist back to null.
					font: c.font && fontMap.has(c.font) ? c.font : null,
					animations: c.animations !== false
				};
			}
		} catch {
			/* fall through to defaults */
		}
	}
	return {
		color: DEFAULT_COLOR_ID,
		concept: DEFAULT_CONCEPT_ID,
		font: null,
		animations: true
	};
}

/** The font id actually in effect: pinned override, else concept default, else global. */
function resolveFontId(concept: ConceptTheme, font: string | null): string {
	if (font && fontMap.has(font)) return font;
	if (concept.defaultFont && fontMap.has(concept.defaultFont)) return concept.defaultFont;
	return DEFAULT_FONT_ID;
}

function apply(color: ColorTheme, concept: ConceptTheme, font: string | null, animations: boolean) {
	if (!browser) return;
	const root = document.documentElement;
	for (const [k, v] of Object.entries(color.tokens)) root.style.setProperty(k, v);
	for (const [k, v] of Object.entries(concept.tokens)) root.style.setProperty(k, v);

	const fontId = resolveFontId(concept, font);
	const fontDef = fontMap.get(fontId);
	if (fontDef) root.style.setProperty('--font-sans', fontDef.stack);

	root.dataset.color = color.id;
	root.dataset.concept = concept.id;
	root.dataset.mode = color.mode;
	root.dataset.font = fontId;
	root.dataset.animations = animations ? 'on' : 'off';
}

class ThemeState {
	#choice = $state<ThemeChoice>(readChoice());

	get colorId() {
		return this.#choice.color;
	}
	get conceptId() {
		return this.#choice.concept;
	}
	get color(): ColorTheme {
		return colorThemeMap.get(this.#choice.color)!;
	}
	get concept(): ConceptTheme {
		return conceptThemeMap.get(this.#choice.concept)!;
	}
	/** The user's font choice: a pinned id, or null when following the concept default. */
	get fontChoice(): string | null {
		return this.#choice.font;
	}
	/** The font id actually applied (resolves null → concept default → global). */
	get fontId(): string {
		return resolveFontId(this.concept, this.#choice.font);
	}
	get animations(): boolean {
		return this.#choice.animations;
	}

	/** Call once on mount to apply the persisted/initial selection. */
	init() {
		apply(this.color, this.concept, this.#choice.font, this.#choice.animations);
	}

	setColor(id: string) {
		if (!colorThemeMap.has(id)) return;
		this.#choice = { ...this.#choice, color: id };
		this.#commit();
	}

	setConcept(id: string) {
		if (!conceptThemeMap.has(id)) return;
		this.#choice = { ...this.#choice, concept: id };
		this.#commit();
	}

	/** Pin a font (id) or reset to the concept default (null). */
	setFont(id: string | null) {
		if (id !== null && !fontMap.has(id)) return;
		this.#choice = { ...this.#choice, font: id };
		this.#commit();
	}

	setAnimations(on: boolean) {
		this.#choice = { ...this.#choice, animations: on };
		this.#commit();
	}

	#commit() {
		apply(this.color, this.concept, this.#choice.font, this.#choice.animations);
		if (browser) localStorage.setItem(STORAGE_KEY, JSON.stringify(this.#choice));
	}
}

export const theme = new ThemeState();

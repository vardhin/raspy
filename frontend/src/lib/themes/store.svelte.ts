// Theme runtime: apply tokens to :root, switch live, persist to localStorage.
// See plan/45-theming.md §5. Color tokens are applied first, then concept tokens,
// so a concept may legitimately override a color token (e.g. neobrutalism's
// --border-color: var(--fg)).
import { browser } from '$app/environment';
import type { ColorTheme, ConceptTheme, ThemeChoice } from './types';
import {
	colorThemeMap,
	conceptThemeMap,
	DEFAULT_COLOR_ID,
	DEFAULT_CONCEPT_ID
} from './registry';

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
							: DEFAULT_CONCEPT_ID
				};
			}
		} catch {
			/* fall through to defaults */
		}
	}
	return { color: DEFAULT_COLOR_ID, concept: DEFAULT_CONCEPT_ID };
}

function apply(color: ColorTheme, concept: ConceptTheme) {
	if (!browser) return;
	const root = document.documentElement;
	for (const [k, v] of Object.entries(color.tokens)) root.style.setProperty(k, v);
	for (const [k, v] of Object.entries(concept.tokens)) root.style.setProperty(k, v);
	root.dataset.color = color.id;
	root.dataset.concept = concept.id;
	root.dataset.mode = color.mode;
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

	/** Call once on mount to apply the persisted/initial selection. */
	init() {
		apply(this.color, this.concept);
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

	#commit() {
		apply(this.color, this.concept);
		if (browser) localStorage.setItem(STORAGE_KEY, JSON.stringify(this.#choice));
	}
}

export const theme = new ThemeState();

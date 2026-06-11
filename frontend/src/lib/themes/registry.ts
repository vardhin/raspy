// Auto-discovery of themes. Drop a file in colors/ or concepts/ and it appears
// here — and thus in the picker — with no other code changes. See plan/45-theming.md §4.
import type { ColorTheme, ConceptTheme } from './types';

const colorMods = import.meta.glob<{ default: ColorTheme }>('./colors/*.ts', {
	eager: true
});
const conceptMods = import.meta.glob<{ default: ConceptTheme }>('./concepts/*.ts', {
	eager: true
});

function byName<T extends { name: string }>(a: T, b: T) {
	return a.name.localeCompare(b.name);
}

export const colorThemes: ColorTheme[] = Object.values(colorMods)
	.map((m) => m.default)
	.sort(byName);

export const conceptThemes: ConceptTheme[] = Object.values(conceptMods)
	.map((m) => m.default)
	.sort(byName);

export const colorThemeMap = new Map(colorThemes.map((t) => [t.id, t]));
export const conceptThemeMap = new Map(conceptThemes.map((t) => [t.id, t]));

/** Defaults used on first load / when a persisted id no longer exists. */
export const DEFAULT_COLOR_ID = colorThemeMap.has('dracula')
	? 'dracula'
	: (colorThemes[0]?.id ?? 'dracula');
export const DEFAULT_CONCEPT_ID = conceptThemeMap.has('soft')
	? 'soft'
	: (conceptThemes[0]?.id ?? 'soft');

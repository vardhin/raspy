// Font registry contract. One file per bundled family in this folder, auto-discovered
// by registry.ts (cf. ../registry.ts for color/concept themes). The actual .woff2 files
// live in static/fonts/<id>/ — run scripts/fetch-fonts.mjs to (re)download them.

export type FontCategory = 'sans' | 'serif' | 'mono' | 'display' | 'handwriting';

export interface FontFace {
	weight: number;
	/** Absolute path under static/, e.g. /fonts/inter/400.woff2 */
	file: string;
}

export interface FontDef {
	id: string;
	name: string;
	category: FontCategory;
	/** CSS font-family stack, e.g. '"Inter", sans-serif'. */
	stack: string;
	faces: FontFace[];
}

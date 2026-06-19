// Auto-discovery of bundled fonts. Drop a file in this folder and it appears here —
// and thus in the picker — with no other code changes (cf. ../registry.ts). The font
// files themselves live in static/fonts/<id>/ (run scripts/fetch-fonts.mjs).
import { browser } from '$app/environment';
import type { FontDef } from './types';

const fontMods = import.meta.glob<{ default: FontDef }>('./*.ts', { eager: true });

export const fontList: FontDef[] = Object.entries(fontMods)
	// types.ts has no default export — skip it.
	.filter(([path]) => !path.endsWith('/types.ts') && !path.endsWith('/registry.ts'))
	.map(([, m]) => m.default)
	.filter(Boolean)
	.sort((a, b) => a.name.localeCompare(b.name));

export const fontMap = new Map(fontList.map((f) => [f.id, f]));

/** Global fallback font when neither a pinned font nor a concept default resolves. */
export const DEFAULT_FONT_ID = fontMap.has('inter')
	? 'inter'
	: (fontList[0]?.id ?? 'inter');

/** Build the @font-face CSS for every bundled font. */
function faceCss(): string {
	return fontList
		.flatMap((f) =>
			f.faces.map(
				(face) => `@font-face{
  font-family:${JSON.stringify(f.name)};
  font-style:normal;
  font-weight:${face.weight};
  font-display:swap;
  src:url(${face.file}) format("woff2");
}`
			)
		)
		.join('\n');
}

let injected = false;
/** Inject all @font-face rules once (idempotent). Call on app mount. */
export function ensureFontFaces() {
	if (!browser || injected) return;
	injected = true;
	const style = document.createElement('style');
	style.id = 'raspy-font-faces';
	style.textContent = faceCss();
	document.head.appendChild(style);
}

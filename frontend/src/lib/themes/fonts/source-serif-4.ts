import type { FontDef } from './types';

// Source Serif 4 — serif. Faces served from /fonts/source-serif-4/<weight>.woff2
// (run scripts/fetch-fonts.mjs to populate). Auto-discovered by the registry.
export default {
	id: 'source-serif-4',
	name: 'Source Serif 4',
	category: 'serif',
	stack: '"Source Serif 4", serif',
	faces: [
		{ weight: 400, file: '/fonts/source-serif-4/400.woff2' },
		{ weight: 700, file: '/fonts/source-serif-4/700.woff2' }
	]
} satisfies FontDef;

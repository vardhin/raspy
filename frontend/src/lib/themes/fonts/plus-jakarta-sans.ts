import type { FontDef } from './types';

// Plus Jakarta Sans — sans. Faces served from /fonts/plus-jakarta-sans/<weight>.woff2
// (run scripts/fetch-fonts.mjs to populate). Auto-discovered by the registry.
export default {
	id: 'plus-jakarta-sans',
	name: 'Plus Jakarta Sans',
	category: 'sans',
	stack: '"Plus Jakarta Sans", sans-serif',
	faces: [
		{ weight: 400, file: '/fonts/plus-jakarta-sans/400.woff2' },
		{ weight: 700, file: '/fonts/plus-jakarta-sans/700.woff2' }
	]
} satisfies FontDef;

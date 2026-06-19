import type { FontDef } from './types';

// DM Sans — sans. Faces served from /fonts/dm-sans/<weight>.woff2
// (run scripts/fetch-fonts.mjs to populate). Auto-discovered by the registry.
export default {
	id: 'dm-sans',
	name: 'DM Sans',
	category: 'sans',
	stack: '"DM Sans", sans-serif',
	faces: [
		{ weight: 400, file: '/fonts/dm-sans/400.woff2' },
		{ weight: 700, file: '/fonts/dm-sans/700.woff2' }
	]
} satisfies FontDef;

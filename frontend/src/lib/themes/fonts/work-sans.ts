import type { FontDef } from './types';

// Work Sans — sans. Faces served from /fonts/work-sans/<weight>.woff2
// (run scripts/fetch-fonts.mjs to populate). Auto-discovered by the registry.
export default {
	id: 'work-sans',
	name: 'Work Sans',
	category: 'sans',
	stack: '"Work Sans", sans-serif',
	faces: [
		{ weight: 400, file: '/fonts/work-sans/400.woff2' },
		{ weight: 700, file: '/fonts/work-sans/700.woff2' }
	]
} satisfies FontDef;

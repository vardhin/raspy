import type { FontDef } from './types';

// Rubik — sans. Faces served from /fonts/rubik/<weight>.woff2
// (run scripts/fetch-fonts.mjs to populate). Auto-discovered by the registry.
export default {
	id: 'rubik',
	name: 'Rubik',
	category: 'sans',
	stack: '"Rubik", sans-serif',
	faces: [
		{ weight: 400, file: '/fonts/rubik/400.woff2' },
		{ weight: 700, file: '/fonts/rubik/700.woff2' }
	]
} satisfies FontDef;

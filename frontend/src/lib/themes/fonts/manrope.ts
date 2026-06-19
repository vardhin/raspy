import type { FontDef } from './types';

// Manrope — sans. Faces served from /fonts/manrope/<weight>.woff2
// (run scripts/fetch-fonts.mjs to populate). Auto-discovered by the registry.
export default {
	id: 'manrope',
	name: 'Manrope',
	category: 'sans',
	stack: '"Manrope", sans-serif',
	faces: [
		{ weight: 400, file: '/fonts/manrope/400.woff2' },
		{ weight: 700, file: '/fonts/manrope/700.woff2' }
	]
} satisfies FontDef;

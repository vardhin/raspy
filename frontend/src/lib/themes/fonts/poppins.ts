import type { FontDef } from './types';

// Poppins — sans. Faces served from /fonts/poppins/<weight>.woff2
// (run scripts/fetch-fonts.mjs to populate). Auto-discovered by the registry.
export default {
	id: 'poppins',
	name: 'Poppins',
	category: 'sans',
	stack: '"Poppins", sans-serif',
	faces: [
		{ weight: 400, file: '/fonts/poppins/400.woff2' },
		{ weight: 700, file: '/fonts/poppins/700.woff2' }
	]
} satisfies FontDef;

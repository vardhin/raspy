import type { FontDef } from './types';

// Fraunces — serif. Faces served from /fonts/fraunces/<weight>.woff2
// (run scripts/fetch-fonts.mjs to populate). Auto-discovered by the registry.
export default {
	id: 'fraunces',
	name: 'Fraunces',
	category: 'serif',
	stack: '"Fraunces", serif',
	faces: [
		{ weight: 400, file: '/fonts/fraunces/400.woff2' },
		{ weight: 700, file: '/fonts/fraunces/700.woff2' }
	]
} satisfies FontDef;

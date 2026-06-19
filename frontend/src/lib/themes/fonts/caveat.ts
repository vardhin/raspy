import type { FontDef } from './types';

// Caveat — handwriting. Faces served from /fonts/caveat/<weight>.woff2
// (run scripts/fetch-fonts.mjs to populate). Auto-discovered by the registry.
export default {
	id: 'caveat',
	name: 'Caveat',
	category: 'handwriting',
	stack: '"Caveat", cursive',
	faces: [
		{ weight: 400, file: '/fonts/caveat/400.woff2' },
		{ weight: 700, file: '/fonts/caveat/700.woff2' }
	]
} satisfies FontDef;

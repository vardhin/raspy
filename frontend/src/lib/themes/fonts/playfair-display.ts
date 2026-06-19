import type { FontDef } from './types';

// Playfair Display — serif. Faces served from /fonts/playfair-display/<weight>.woff2
// (run scripts/fetch-fonts.mjs to populate). Auto-discovered by the registry.
export default {
	id: 'playfair-display',
	name: 'Playfair Display',
	category: 'serif',
	stack: '"Playfair Display", serif',
	faces: [
		{ weight: 400, file: '/fonts/playfair-display/400.woff2' },
		{ weight: 700, file: '/fonts/playfair-display/700.woff2' }
	]
} satisfies FontDef;

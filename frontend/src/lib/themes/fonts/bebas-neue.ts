import type { FontDef } from './types';

// Bebas Neue — display. Faces served from /fonts/bebas-neue/<weight>.woff2
// (run scripts/fetch-fonts.mjs to populate). Auto-discovered by the registry.
export default {
	id: 'bebas-neue',
	name: 'Bebas Neue',
	category: 'display',
	stack: '"Bebas Neue", sans-serif',
	faces: [{ weight: 400, file: '/fonts/bebas-neue/400.woff2' }]
} satisfies FontDef;

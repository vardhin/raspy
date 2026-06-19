import type { FontDef } from './types';

// Outfit — sans. Faces served from /fonts/outfit/<weight>.woff2
// (run scripts/fetch-fonts.mjs to populate). Auto-discovered by the registry.
export default {
	id: 'outfit',
	name: 'Outfit',
	category: 'sans',
	stack: '"Outfit", sans-serif',
	faces: [
		{ weight: 400, file: '/fonts/outfit/400.woff2' },
		{ weight: 700, file: '/fonts/outfit/700.woff2' }
	]
} satisfies FontDef;

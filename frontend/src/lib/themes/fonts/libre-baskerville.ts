import type { FontDef } from './types';

// Libre Baskerville — serif. Faces served from /fonts/libre-baskerville/<weight>.woff2
// (run scripts/fetch-fonts.mjs to populate). Auto-discovered by the registry.
export default {
	id: 'libre-baskerville',
	name: 'Libre Baskerville',
	category: 'serif',
	stack: '"Libre Baskerville", serif',
	faces: [
		{ weight: 400, file: '/fonts/libre-baskerville/400.woff2' },
		{ weight: 700, file: '/fonts/libre-baskerville/700.woff2' }
	]
} satisfies FontDef;

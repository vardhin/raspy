import type { FontDef } from './types';

// Merriweather — serif. Faces served from /fonts/merriweather/<weight>.woff2
// (run scripts/fetch-fonts.mjs to populate). Auto-discovered by the registry.
export default {
	id: 'merriweather',
	name: 'Merriweather',
	category: 'serif',
	stack: '"Merriweather", serif',
	faces: [
		{ weight: 400, file: '/fonts/merriweather/400.woff2' },
		{ weight: 700, file: '/fonts/merriweather/700.woff2' }
	]
} satisfies FontDef;

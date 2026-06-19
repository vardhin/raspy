import type { FontDef } from './types';

// Nunito — sans. Faces served from /fonts/nunito/<weight>.woff2
// (run scripts/fetch-fonts.mjs to populate). Auto-discovered by the registry.
export default {
	id: 'nunito',
	name: 'Nunito',
	category: 'sans',
	stack: '"Nunito", sans-serif',
	faces: [
		{ weight: 400, file: '/fonts/nunito/400.woff2' },
		{ weight: 700, file: '/fonts/nunito/700.woff2' }
	]
} satisfies FontDef;

import type { FontDef } from './types';

// Inter — sans. Faces served from /fonts/inter/<weight>.woff2
// (run scripts/fetch-fonts.mjs to populate). Auto-discovered by the registry.
export default {
	id: 'inter',
	name: 'Inter',
	category: 'sans',
	stack: '"Inter", sans-serif',
	faces: [
		{ weight: 400, file: '/fonts/inter/400.woff2' },
		{ weight: 700, file: '/fonts/inter/700.woff2' }
	]
} satisfies FontDef;

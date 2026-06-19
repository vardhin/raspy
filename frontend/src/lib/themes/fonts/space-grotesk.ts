import type { FontDef } from './types';

// Space Grotesk — sans. Faces served from /fonts/space-grotesk/<weight>.woff2
// (run scripts/fetch-fonts.mjs to populate). Auto-discovered by the registry.
export default {
	id: 'space-grotesk',
	name: 'Space Grotesk',
	category: 'sans',
	stack: '"Space Grotesk", sans-serif',
	faces: [
		{ weight: 400, file: '/fonts/space-grotesk/400.woff2' },
		{ weight: 700, file: '/fonts/space-grotesk/700.woff2' }
	]
} satisfies FontDef;

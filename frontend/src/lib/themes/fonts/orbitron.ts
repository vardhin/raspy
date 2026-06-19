import type { FontDef } from './types';

// Orbitron — display. Faces served from /fonts/orbitron/<weight>.woff2
// (run scripts/fetch-fonts.mjs to populate). Auto-discovered by the registry.
export default {
	id: 'orbitron',
	name: 'Orbitron',
	category: 'display',
	stack: '"Orbitron", sans-serif',
	faces: [
		{ weight: 400, file: '/fonts/orbitron/400.woff2' },
		{ weight: 700, file: '/fonts/orbitron/700.woff2' }
	]
} satisfies FontDef;

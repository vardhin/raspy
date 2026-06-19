import type { FontDef } from './types';

// Righteous — display. Faces served from /fonts/righteous/<weight>.woff2
// (run scripts/fetch-fonts.mjs to populate). Auto-discovered by the registry.
export default {
	id: 'righteous',
	name: 'Righteous',
	category: 'display',
	stack: '"Righteous", sans-serif',
	faces: [{ weight: 400, file: '/fonts/righteous/400.woff2' }]
} satisfies FontDef;

import type { FontDef } from './types';

// Lora — serif. Faces served from /fonts/lora/<weight>.woff2
// (run scripts/fetch-fonts.mjs to populate). Auto-discovered by the registry.
export default {
	id: 'lora',
	name: 'Lora',
	category: 'serif',
	stack: '"Lora", serif',
	faces: [
		{ weight: 400, file: '/fonts/lora/400.woff2' },
		{ weight: 700, file: '/fonts/lora/700.woff2' }
	]
} satisfies FontDef;

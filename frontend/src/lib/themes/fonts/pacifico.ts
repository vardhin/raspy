import type { FontDef } from './types';

// Pacifico — handwriting. Faces served from /fonts/pacifico/<weight>.woff2
// (run scripts/fetch-fonts.mjs to populate). Auto-discovered by the registry.
export default {
	id: 'pacifico',
	name: 'Pacifico',
	category: 'handwriting',
	stack: '"Pacifico", cursive',
	faces: [{ weight: 400, file: '/fonts/pacifico/400.woff2' }]
} satisfies FontDef;

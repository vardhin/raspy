import type { FontDef } from './types';

// Fira Code — mono. Faces served from /fonts/fira-code/<weight>.woff2
// (run scripts/fetch-fonts.mjs to populate). Auto-discovered by the registry.
export default {
	id: 'fira-code',
	name: 'Fira Code',
	category: 'mono',
	stack: '"Fira Code", monospace',
	faces: [
		{ weight: 400, file: '/fonts/fira-code/400.woff2' },
		{ weight: 700, file: '/fonts/fira-code/700.woff2' }
	]
} satisfies FontDef;

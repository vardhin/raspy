import type { FontDef } from './types';

// Space Mono — mono. Faces served from /fonts/space-mono/<weight>.woff2
// (run scripts/fetch-fonts.mjs to populate). Auto-discovered by the registry.
export default {
	id: 'space-mono',
	name: 'Space Mono',
	category: 'mono',
	stack: '"Space Mono", monospace',
	faces: [
		{ weight: 400, file: '/fonts/space-mono/400.woff2' },
		{ weight: 700, file: '/fonts/space-mono/700.woff2' }
	]
} satisfies FontDef;

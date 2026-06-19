import type { FontDef } from './types';

// IBM Plex Mono — mono. Faces served from /fonts/ibm-plex-mono/<weight>.woff2
// (run scripts/fetch-fonts.mjs to populate). Auto-discovered by the registry.
export default {
	id: 'ibm-plex-mono',
	name: 'IBM Plex Mono',
	category: 'mono',
	stack: '"IBM Plex Mono", monospace',
	faces: [
		{ weight: 400, file: '/fonts/ibm-plex-mono/400.woff2' },
		{ weight: 700, file: '/fonts/ibm-plex-mono/700.woff2' }
	]
} satisfies FontDef;

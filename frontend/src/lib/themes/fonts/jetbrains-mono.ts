import type { FontDef } from './types';

// JetBrains Mono — mono. Faces served from /fonts/jetbrains-mono/<weight>.woff2
// (run scripts/fetch-fonts.mjs to populate). Auto-discovered by the registry.
export default {
	id: 'jetbrains-mono',
	name: 'JetBrains Mono',
	category: 'mono',
	stack: '"JetBrains Mono", monospace',
	faces: [
		{ weight: 400, file: '/fonts/jetbrains-mono/400.woff2' },
		{ weight: 700, file: '/fonts/jetbrains-mono/700.woff2' }
	]
} satisfies FontDef;

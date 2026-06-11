import type { ColorTheme } from '../types';

// Palette: Ayu by dempfi (official spec) — dark (mirage-ish) variant.
export default {
	id: 'ayu-dark',
	name: 'Ayu Dark',
	mode: 'dark',
	tokens: {
		'--bg': '#0b0e14',
		'--surface': '#11151c',
		'--surface-2': '#0d1017',
		'--fg': '#bfbdb6',
		'--muted': '#565b66',
		'--border-color': '#1d232b',
		'--accent': '#ffb454',
		'--accent-fg': '#0b0e14',
		'--success': '#aad94c',
		'--success-fg': '#0b0e14',
		'--warn': '#ffb454',
		'--warn-fg': '#0b0e14',
		'--danger': '#f07178',
		'--danger-fg': '#0b0e14',
		'--info': '#59c2ff',
		'--info-fg': '#0b0e14',
		'--overlay': 'rgba(13, 16, 23, 0.8)'
	}
} satisfies ColorTheme;

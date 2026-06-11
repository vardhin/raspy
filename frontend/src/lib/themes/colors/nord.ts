import type { ColorTheme } from '../types';

// Palette: Nord by Arctic Ice Studio (official spec). Polar Night → Snow Storm.
export default {
	id: 'nord',
	name: 'Nord',
	mode: 'dark',
	tokens: {
		'--bg': '#2e3440',
		'--surface': '#3b4252',
		'--surface-2': '#272c36',
		'--fg': '#eceff4',
		'--muted': '#81a1c1',
		'--border-color': '#4c566a',
		'--accent': '#88c0d0',
		'--accent-fg': '#2e3440',
		'--success': '#a3be8c',
		'--success-fg': '#2e3440',
		'--warn': '#ebcb8b',
		'--warn-fg': '#2e3440',
		'--danger': '#bf616a',
		'--danger-fg': '#eceff4',
		'--info': '#5e81ac',
		'--info-fg': '#eceff4',
		'--overlay': 'rgba(39, 44, 54, 0.8)'
	}
} satisfies ColorTheme;

import type { ColorTheme } from '../types';

// Palette: Solarized by Ethan Schoonover (official spec) — dark.
export default {
	id: 'solarized-dark',
	name: 'Solarized Dark',
	mode: 'dark',
	tokens: {
		'--bg': '#002b36',
		'--surface': '#073642',
		'--surface-2': '#00212b',
		'--fg': '#93a1a1',
		'--muted': '#586e75',
		'--border-color': '#0a4b5a',
		'--accent': '#268bd2',
		'--accent-fg': '#fdf6e3',
		'--success': '#859900',
		'--success-fg': '#002b36',
		'--warn': '#b58900',
		'--warn-fg': '#002b36',
		'--danger': '#dc322f',
		'--danger-fg': '#fdf6e3',
		'--info': '#2aa198',
		'--info-fg': '#002b36',
		'--overlay': 'rgba(0, 33, 43, 0.8)'
	}
} satisfies ColorTheme;

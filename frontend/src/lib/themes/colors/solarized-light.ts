import type { ColorTheme } from '../types';

// Palette: Solarized by Ethan Schoonover (official spec) — light.
export default {
	id: 'solarized-light',
	name: 'Solarized Light',
	mode: 'light',
	tokens: {
		'--bg': '#fdf6e3',
		'--surface': '#eee8d5',
		'--surface-2': '#f7f0dd',
		'--fg': '#586e75',
		'--muted': '#93a1a1',
		'--border-color': '#d9d2bf',
		'--accent': '#268bd2',
		'--accent-fg': '#fdf6e3',
		'--success': '#859900',
		'--success-fg': '#fdf6e3',
		'--warn': '#b58900',
		'--warn-fg': '#fdf6e3',
		'--danger': '#dc322f',
		'--danger-fg': '#fdf6e3',
		'--info': '#2aa198',
		'--info-fg': '#fdf6e3',
		'--overlay': 'rgba(88, 110, 117, 0.4)'
	}
} satisfies ColorTheme;

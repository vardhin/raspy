import type { ColorTheme } from '../types';

// Palette: Everforest by sainnhe (official spec) — dark, medium.
export default {
	id: 'everforest',
	name: 'Everforest',
	mode: 'dark',
	tokens: {
		'--bg': '#2d353b',
		'--surface': '#343f44',
		'--surface-2': '#272e33',
		'--fg': '#d3c6aa',
		'--muted': '#859289',
		'--border-color': '#475258',
		'--accent': '#a7c080',
		'--accent-fg': '#2d353b',
		'--success': '#a7c080',
		'--success-fg': '#2d353b',
		'--warn': '#dbbc7f',
		'--warn-fg': '#2d353b',
		'--danger': '#e67e80',
		'--danger-fg': '#2d353b',
		'--info': '#7fbbb3',
		'--info-fg': '#2d353b',
		'--overlay': 'rgba(39, 46, 51, 0.8)'
	}
} satisfies ColorTheme;

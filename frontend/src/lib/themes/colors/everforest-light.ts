import type { ColorTheme } from '../types';

// Everforest Light (medium) — warm green-tinted paper, soft earthy accents.
// https://github.com/sainnhe/everforest
export default {
	id: 'everforest-light',
	name: 'Everforest (Light)',
	mode: 'light',
	tokens: {
		'--bg': '#fdf6e3', // bg0
		'--surface': '#f4f0d9', // bg1
		'--surface-2': '#efebd4', // bg2
		'--fg': '#5c6a72', // fg
		'--fg-accent': 'color-mix(in srgb, var(--fg) 86%, var(--accent))',
		'--muted': '#829181', // grey1
		'--border-color': '#ddd8be', // bg4
		'--accent': '#8da101', // green
		'--accent-fg': '#fdf6e3',
		'--success': '#35a77c', // aqua
		'--success-fg': '#fdf6e3',
		'--warn': '#dfa000', // yellow
		'--warn-fg': '#fdf6e3',
		'--danger': '#f85552', // red
		'--danger-fg': '#fdf6e3',
		'--info': '#3a94c5', // blue
		'--info-fg': '#fdf6e3',
		'--overlay': 'rgba(92, 106, 114, 0.28)'
	}
} satisfies ColorTheme;
